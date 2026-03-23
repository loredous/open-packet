from __future__ import annotations
import logging
import time
from enum import Enum
from typing import Optional

from open_packet.ax25.frame import (
    FrameType,
    encode_sabm, encode_ua, encode_dm, encode_disc,
    encode_i_frame, encode_rr, encode_rnr, encode_rej,
    decode_frame,
    PID_NO_LAYER3,
)
from open_packet.ax25.timer import Timer
from open_packet.link.base import ConnectionBase, ConnectionError

logger = logging.getLogger(__name__)

# AX.25 v2.2 defaults (§6.7)
T1_DEFAULT = 3.0    # Acknowledgment timer (seconds)
T3_DEFAULT = 30.0   # Inactive-link timer (seconds)
N2_DEFAULT = 10     # Maximum retries
K_DEFAULT  = 7      # Window size (mod-8)


class LinkState(Enum):
    DISCONNECTED        = 0
    AWAITING_CONNECTION = 1
    AWAITING_RELEASE    = 2
    CONNECTED           = 3
    TIMER_RECOVERY      = 4


class AX25Connection(ConnectionBase):
    """
    AX.25 v2.2 data link connection over a KISSLink.

    connect(dest, ssid)    — open transport + SABM/UA exchange
    disconnect()           — DISC/UA exchange + close transport
    send_frame(payload)    — send payload as I-frame
    receive_frame(timeout) — return payload from next received I-frame
                             (also processes supervisory frames in-band)
    """

    def __init__(
        self,
        kiss: ConnectionBase,
        my_callsign: str,
        my_ssid: int,
        t1: float = T1_DEFAULT,
        t3: float = T3_DEFAULT,
        n2: int   = N2_DEFAULT,
        k: int    = K_DEFAULT,
    ) -> None:
        self._kiss         = kiss
        self._my_call      = my_callsign
        self._my_ssid      = my_ssid
        self._dest_call: Optional[str] = None
        self._dest_ssid: int = 0

        self._t1_timeout = t1
        self._t3_timeout = t3
        self._n2         = n2
        self._k          = k

        self.state = LinkState.DISCONNECTED

        # State variables (§4.2.2)
        self.V_S: int = 0
        self.V_R: int = 0
        self.V_A: int = 0
        self.RC:  int = 0

        self._peer_receiver_busy: bool = False
        self._own_receiver_busy:  bool = False
        self._reject_exception:   bool = False
        self._ack_pending:        bool = False

        self._t1 = Timer()
        self._t3 = Timer()

        # Unacknowledged I-frames for retransmission: seq_num → payload
        self._unacked: dict[int, bytes] = {}

    # ------------------------------------------------------------------ #
    # ConnectionBase interface                                             #
    # ------------------------------------------------------------------ #

    def connect(self, callsign: str, ssid: int) -> None:
        self._dest_call = callsign
        self._dest_ssid = ssid
        self._kiss.connect(callsign, ssid)
        self._establish_data_link()

    def disconnect(self) -> None:
        if self.state not in (LinkState.CONNECTED, LinkState.TIMER_RECOVERY):
            self._kiss.disconnect()
            return
        self._send_disc(poll=True)
        self.state = LinkState.AWAITING_RELEASE
        self.RC = 0
        self._t3.stop()
        self._t1.start(self._t1_timeout)
        self._wait_for_release()
        self._kiss.disconnect()

    def send_frame(self, data: bytes) -> None:
        if self.state not in (LinkState.CONNECTED, LinkState.TIMER_RECOVERY):
            raise ConnectionError("Cannot send: not connected")
        if ((self.V_S - self.V_A) % 8) >= self._k:
            raise ConnectionError("Send window full — cannot send I-frame")
        self._send_i_frame(data)

    def receive_frame(self, timeout: float = 5.0) -> bytes:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            raw = self._kiss.receive_frame(timeout=min(remaining, 0.5))
            if raw:
                result = self._process_frame(raw)
                if result is not None:
                    return result
            self._check_timers()
        return b""

    # ------------------------------------------------------------------ #
    # Internal: connection setup                                           #
    # ------------------------------------------------------------------ #

    def _establish_data_link(self) -> None:
        self.state = LinkState.AWAITING_CONNECTION
        self.RC = 0
        self._clear_exception_conditions()
        self._send_sabm(poll=True)
        self._t1.start(self._t1_timeout)

        deadline = time.monotonic() + self._t1_timeout * (self._n2 + 1)
        while time.monotonic() < deadline:
            raw = self._kiss.receive_frame(timeout=1.0)
            if not raw:
                if self._t1.expired:
                    if self.RC >= self._n2:
                        self.state = LinkState.DISCONNECTED
                        raise ConnectionError(
                            f"No UA after {self._n2} SABM attempts"
                        )
                    self.RC += 1
                    self._send_sabm(poll=True)
                    self._t1.start(self._t1_timeout)
                continue

            f = decode_frame(raw)

            if f.frame_type == FrameType.UA and f.poll_final:
                self._t1.stop()
                self._t3.stop()
                self.V_S = 0
                self.V_A = 0
                self.V_R = 0
                self.state = LinkState.CONNECTED
                self._t3.start(self._t3_timeout)
                logger.info("AX.25 connected to %s-%d", self._dest_call, self._dest_ssid)
                return

            if f.frame_type == FrameType.DM and f.poll_final:
                self.state = LinkState.DISCONNECTED
                raise ConnectionError(
                    f"Connection refused by {self._dest_call} (DM received)"
                )

        self.state = LinkState.DISCONNECTED
        raise ConnectionError("Connection timed out")

    def _wait_for_release(self) -> None:
        deadline = time.monotonic() + self._t1_timeout * (self._n2 + 1)
        while time.monotonic() < deadline:
            raw = self._kiss.receive_frame(timeout=1.0)
            if not raw:
                if self._t1.expired:
                    if self.RC >= self._n2:
                        break
                    self.RC += 1
                    self._send_disc(poll=True)
                    self._t1.start(self._t1_timeout)
                continue
            f = decode_frame(raw)
            if f.frame_type in (FrameType.UA, FrameType.DM):
                self._t1.stop()
                break
        self.state = LinkState.DISCONNECTED

    # ------------------------------------------------------------------ #
    # Internal: frame processing                                           #
    # ------------------------------------------------------------------ #

    def _process_frame(self, raw: bytes) -> Optional[bytes]:
        try:
            f = decode_frame(raw)
        except ValueError:
            return None

        if f.frame_type == FrameType.I:
            return self._handle_i_frame(f)
        elif f.frame_type == FrameType.RR:
            self._handle_rr(f)
        elif f.frame_type == FrameType.RNR:
            self._handle_rnr(f)
        elif f.frame_type == FrameType.REJ:
            self._handle_rej(f)
        elif f.frame_type == FrameType.SABM:
            self._handle_sabm_reset(f)
        elif f.frame_type == FrameType.DISC:
            self._send_ua(final=bool(f.poll_final))
            self.state = LinkState.DISCONNECTED
            raise ConnectionError("Remote station disconnected")
        elif f.frame_type == FrameType.DM:
            self.state = LinkState.DISCONNECTED
            raise ConnectionError("Remote station sent DM (disconnected mode)")
        return None

    def _handle_i_frame(self, f) -> Optional[bytes]:
        if self._own_receiver_busy:
            if f.poll_final:
                self._send_rnr(final=True)
            return None

        if f.ns != self.V_R:
            if not self._reject_exception:
                self._reject_exception = True
                self._send_rej(poll=False)
            return None

        self.V_R = (self.V_R + 1) % 8
        self._reject_exception = False
        payload = f.info

        self._send_rr(nr=self.V_R, poll=bool(f.poll_final))
        self._ack_pending = False
        self._check_i_frame_ack(f.nr)

        return payload

    def _handle_rr(self, f) -> None:
        self._peer_receiver_busy = False
        self._check_i_frame_ack(f.nr)
        if f.poll_final and self.state == LinkState.TIMER_RECOVERY:
            self._t1.stop()
            self.state = LinkState.CONNECTED
            self._t3.start(self._t3_timeout)
            self._invoke_retransmission()

    def _handle_rnr(self, f) -> None:
        self._peer_receiver_busy = True
        self._check_i_frame_ack(f.nr)

    def _handle_rej(self, f) -> None:
        self._peer_receiver_busy = False
        self._check_i_frame_ack(f.nr)
        self._t1.stop()
        self.V_S = f.nr
        self._t3.start(self._t3_timeout)
        self._invoke_retransmission()

    def _handle_sabm_reset(self, f) -> None:
        self._send_ua(final=bool(f.poll_final))
        self._clear_exception_conditions()
        self.V_S = 0
        self.V_R = 0
        self.V_A = 0
        self.state = LinkState.CONNECTED

    def _check_i_frame_ack(self, nr: int) -> None:
        if self._va_leq_nr_leq_vs(nr):
            self.V_A = nr
            if self.V_A == self.V_S:
                self._t1.stop()
                self._t3.start(self._t3_timeout)
            else:
                self._t1.start(self._t1_timeout)

    def _va_leq_nr_leq_vs(self, nr: int) -> bool:
        va, vs = self.V_A, self.V_S
        if va <= vs:
            return va <= nr <= vs
        return nr >= va or nr <= vs

    # ------------------------------------------------------------------ #
    # Internal: timer management                                           #
    # ------------------------------------------------------------------ #

    def _check_timers(self) -> None:
        if self._t1.expired:
            self._on_t1_expiry()
        elif self._t3.expired:
            self._on_t3_expiry()

    def _on_t1_expiry(self) -> None:
        if self.RC >= self._n2:
            logger.warning("T1 expired %d times — giving up connection", self.RC)
            self.state = LinkState.DISCONNECTED
            raise ConnectionError("Link failure: T1 expired N2 times")
        self.RC += 1
        self.state = LinkState.TIMER_RECOVERY
        self._send_rr(nr=self.V_R, poll=True)
        self._t1.start(self._t1_timeout)

    def _on_t3_expiry(self) -> None:
        self.RC = 0
        self._t3.stop()
        self.state = LinkState.TIMER_RECOVERY
        self._send_rr(nr=self.V_R, poll=True)
        self._t1.start(self._t1_timeout)

    # ------------------------------------------------------------------ #
    # Internal: retransmission                                             #
    # ------------------------------------------------------------------ #

    def _invoke_retransmission(self) -> None:
        self.V_S = self.V_A
        for payload in list(self._unacked.values()):
            self._send_i_frame(payload)

    # ------------------------------------------------------------------ #
    # Internal: frame senders                                              #
    # ------------------------------------------------------------------ #

    def _send_sabm(self, poll: bool = True) -> None:
        raw = encode_sabm(self._dest_call, self._dest_ssid,
                          self._my_call, self._my_ssid, poll=poll)
        self._kiss.send_frame(raw)
        logger.debug("→ SABM (P=%s)", poll)

    def _send_ua(self, final: bool = True) -> None:
        raw = encode_ua(self._dest_call, self._dest_ssid,
                        self._my_call, self._my_ssid, final=final)
        self._kiss.send_frame(raw)

    def _send_dm(self, final: bool = True) -> None:
        raw = encode_dm(self._dest_call, self._dest_ssid,
                        self._my_call, self._my_ssid, final=final)
        self._kiss.send_frame(raw)

    def _send_disc(self, poll: bool = True) -> None:
        raw = encode_disc(self._dest_call, self._dest_ssid,
                          self._my_call, self._my_ssid, poll=poll)
        self._kiss.send_frame(raw)

    def _send_i_frame(self, payload: bytes) -> None:
        ns = self.V_S
        raw = encode_i_frame(
            self._dest_call, self._dest_ssid,
            self._my_call, self._my_ssid,
            ns=ns, nr=self.V_R, payload=payload,
        )
        self._unacked[ns] = payload
        self.V_S = (self.V_S + 1) % 8
        self._kiss.send_frame(raw)
        self._ack_pending = False
        if not self._t1.running:
            self._t1.start(self._t1_timeout)
        if self._t3.running:
            self._t3.stop()
        logger.debug("→ I(%d,%d) %d bytes", ns, self.V_R, len(payload))

    def _send_rr(self, nr: int, poll: bool = False) -> None:
        raw = encode_rr(self._dest_call, self._dest_ssid,
                        self._my_call, self._my_ssid,
                        nr=nr, poll=poll, command=poll)
        self._kiss.send_frame(raw)

    def _send_rnr(self, final: bool = False) -> None:
        raw = encode_rnr(self._dest_call, self._dest_ssid,
                         self._my_call, self._my_ssid,
                         nr=self.V_R, poll=final, command=not final)
        self._kiss.send_frame(raw)

    def _send_rej(self, poll: bool = False) -> None:
        raw = encode_rej(self._dest_call, self._dest_ssid,
                         self._my_call, self._my_ssid,
                         nr=self.V_R, poll=poll)
        self._kiss.send_frame(raw)

    # ------------------------------------------------------------------ #
    # Internal: helpers                                                    #
    # ------------------------------------------------------------------ #

    def _clear_exception_conditions(self) -> None:
        self._peer_receiver_busy = False
        self._own_receiver_busy  = False
        self._reject_exception   = False
        self._ack_pending        = False
        self._unacked.clear()
        self._t1.stop()
        self._t3.stop()
        self.RC = 0
