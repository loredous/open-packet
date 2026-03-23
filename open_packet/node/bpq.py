# open_packet/node/bpq.py
from __future__ import annotations
import re
import time
from open_packet.link.base import ConnectionBase
from open_packet.node.base import NodeBase, NodeError, MessageHeader, Message

PROMPT = "BPQ>"
TIMEOUT = 10.0


def parse_message_list(text: str) -> list[MessageHeader]:
    headers = []
    for line in text.splitlines():
        m = re.match(
            r'^\s*(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+)$', line
        )
        if m:
            headers.append(MessageHeader(
                bbs_id=m.group(1),
                to_call=m.group(2).strip(),
                from_call=m.group(3).strip(),
                date_str=m.group(4).strip(),
                subject=m.group(5).strip(),
            ))
    return headers


def parse_message_header(line: str) -> MessageHeader | None:
    m = re.match(r'^\s*(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+)$', line)
    if not m:
        return None
    return MessageHeader(
        bbs_id=m.group(1), to_call=m.group(2).strip(),
        from_call=m.group(3).strip(), date_str=m.group(4).strip(),
        subject=m.group(5).strip(),
    )


class BPQNode(NodeBase):
    def __init__(self, connection: ConnectionBase, node_callsign: str,
                 node_ssid: int, my_callsign: str, my_ssid: int):
        self._conn = connection
        self._node_callsign = node_callsign
        self._node_ssid = node_ssid
        self._my_callsign = my_callsign
        self._my_ssid = my_ssid

    def _send_text(self, text: str) -> None:
        self._conn.send_frame((text + "\r").encode())

    def _recv_until_prompt(self, timeout: float = TIMEOUT) -> str:
        buffer = ""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = self._conn.receive_frame(timeout=1.0)
            if data:
                buffer += data.decode(errors="replace")
                if PROMPT in buffer:
                    break
        return buffer

    def connect_node(self) -> None:
        response = self._recv_until_prompt()
        if PROMPT not in response:
            raise NodeError(f"No BPQ prompt received. Got: {response!r}")

    def list_messages(self) -> list[MessageHeader]:
        self._send_text("L")
        response = self._recv_until_prompt()
        return parse_message_list(response)

    def read_message(self, bbs_id: str) -> Message:
        self._send_text(f"R {bbs_id}")
        response = self._recv_until_prompt()
        lines = response.splitlines()
        body_lines = []
        in_body = False
        header = MessageHeader(bbs_id=bbs_id, to_call="", from_call="", subject="")
        for line in lines:
            if not in_body and line.strip() == "":
                in_body = True
                continue
            if in_body and PROMPT not in line:
                body_lines.append(line)
        return Message(header=header, body="\n".join(body_lines).strip())

    def send_message(self, to_call: str, subject: str, body: str) -> None:
        self._send_text(f"S {to_call}")
        self._recv_until_prompt(timeout=5.0)
        self._send_text(subject)
        self._recv_until_prompt(timeout=5.0)
        for line in body.splitlines():
            self._send_text(line)
        self._send_text("/EX")
        self._recv_until_prompt()

    def delete_message(self, bbs_id: str) -> None:
        self._send_text(f"K {bbs_id}")
        self._recv_until_prompt()

    def list_bulletins(self, category: str = "") -> list[MessageHeader]:
        cmd = f"LB {category}".strip()
        self._send_text(cmd)
        response = self._recv_until_prompt()
        return parse_message_list(response)

    def read_bulletin(self, bbs_id: str) -> Message:
        return self.read_message(bbs_id)
