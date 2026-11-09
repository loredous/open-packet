# open_packet/node/bpq.py
from __future__ import annotations
import re
import time
from open_packet.link.base import ConnectionBase
from open_packet.node.base import NodeBase, NodeError, MessageHeader, Message, FileHeader

TIMEOUT = 30.0        # max wait for the first data after a command (RF links can be slow)
IDLE_TIMEOUT = 30.0   # max silence between ANY remote frames (RR counts); slow RF can gap 15-20s

# LinBPQ/BPQ32 default maximum file size (bytes).
MAX_FILE_SIZE = 65535

# Matches a BPQ32 prompt: CALLSIGN> at the start of a line (bare CR or LF counts as
# a line start).  Node prompts look like "W0IA> BBS CHAT NODES..." and BBS prompts
# look like "de k0ark>" (BPQ32 uses the ham "de" prefix), so > is NOT the last
# character — endswith(">") does not work for either.
_PROMPT_RE = re.compile(r'(?:^|\r|\n)(?:de\s+)?[A-Za-z0-9- ]+>')


def _has_prompt(text: str) -> bool:
    return bool(_PROMPT_RE.search(text))


def parse_message_list(text: str) -> list[MessageHeader]:
    headers = []
    for line in text.splitlines():
        # BPQ32 format: ID  DATE  TYPE  SIZE  TO  FROM  SUBJECT
        m = re.match(
            r'^\s*(\d+)\s+(\S+)\s+\S+\s+\S+\s+(\S+)\s+(\S+)\s+(.+)$', line
        )
        if m:
            headers.append(MessageHeader(
                bbs_id=m.group(1),
                date_str=m.group(2).strip(),
                to_call=m.group(3).strip(),
                from_call=m.group(4).strip(),
                subject=m.group(5).strip(),
            ))
    return headers


def parse_file_list(text: str) -> list[FileHeader]:
    files = []
    current_dir = ""
    for line in text.splitlines():
        dir_match = re.match(r'^\s*Dir:\s*(\S+)', line, re.IGNORECASE)
        if dir_match:
            current_dir = dir_match.group(1)
            continue
        m = re.match(r'^\s*(\S+)\s+(\d+)\s+(\S+)\s+(.+)$', line)
        if m:
            files.append(FileHeader(
                filename=m.group(1).strip(),
                directory=current_dir,
                size=int(m.group(2)),
                date_str=m.group(3).strip(),
                description=m.group(4).strip(),
            ))
    return files


def _base_call(callsign: str) -> str:
    """Return the base callsign with any SSID suffix stripped, uppercased."""
    return callsign.split("-")[0].upper()


def parse_nodes_list(text: str) -> list:
    from open_packet.store.models import NodeHop
    hops = []
    seen_bases: set[str] = set()
    for line in text.splitlines():
        if _has_prompt(line):
            break
        parts = line.split()
        i = 0
        while i < len(parts):
            token = parts[i]
            # Strip alias prefix (e.g. "BCARES:W0IA-1" -> "W0IA-1")
            if ":" in token:
                token = token.split(":")[-1]
            # Valid callsign: only letters, digits, dash; must contain a digit;
            # must not be a pure number (port/quality/hops column).
            if (not re.match(r'^[A-Za-z0-9-]+$', token)
                    or not re.search(r'\d', token)
                    or token.isdigit()):
                i += 1
                continue
            base = _base_call(token)
            if base not in seen_bases:
                seen_bases.add(base)
                # Port is the next raw token if it's a pure integer
                port = None
                if i + 1 < len(parts) and parts[i + 1].isdigit():
                    port = int(parts[i + 1])
                hops.append(NodeHop(callsign=token, port=port))
            i += 1
    return hops


def parse_message_header(line: str) -> MessageHeader | None:
    # BPQ32 format: ID  DATE  TYPE  SIZE  TO  FROM  SUBJECT
    m = re.match(r'^\s*(\d+)\s+(\S+)\s+\S+\s+\S+\s+(\S+)\s+(\S+)\s+(.+)$', line)
    if not m:
        return None
    return MessageHeader(
        bbs_id=m.group(1), date_str=m.group(2).strip(),
        to_call=m.group(3).strip(), from_call=m.group(4).strip(),
        subject=m.group(5).strip(),
    )


class BPQNode(NodeBase):
    def __init__(self, connection: ConnectionBase, node_callsign: str,
                 node_ssid: int, my_callsign: str, my_ssid: int,
                 hop_path=None, path_strategy: str = "path_route"):
        self._conn = connection
        self._node_callsign = node_callsign
        self._node_ssid = node_ssid
        self._my_callsign = my_callsign
        self._my_ssid = my_ssid
        self._hop_path = hop_path or []
        self._path_strategy = path_strategy

    def _send_text(self, text: str) -> None:
        self._conn.send_frame((text + "\r").encode())

    # After a CR-terminated chunk, wait this long for another frame before
    # concluding the response is complete (used by end_on_cr callers).
    _CR_WAIT = 2.0

    def _recv_until_prompt(self, timeout: float = TIMEOUT, end_on_cr: bool = False) -> str:
        buffer = ""
        first_data_deadline = time.monotonic() + timeout
        idle_deadline: float | None = None
        cr_deadline: float | None = None
        while True:
            now = time.monotonic()
            if cr_deadline is not None and now >= cr_deadline:
                break
            if idle_deadline is not None:
                if now >= idle_deadline:
                    break
            elif now >= first_data_deadline:
                break
            data = self._conn.receive_frame(timeout=1.0)
            if data is not None:                          # any frame (RR, I-frame, …)
                idle_deadline = time.monotonic() + IDLE_TIMEOUT
                cr_deadline = None                        # new activity resets CR wait
            if data:                                      # I-frame payload only
                chunk = data.decode(errors="replace")
                buffer += chunk
                if _has_prompt(buffer):
                    break
                if end_on_cr and chunk.endswith("\r"):
                    cr_deadline = time.monotonic() + self._CR_WAIT
        return buffer

    def connect_node(self) -> None:
        # Traverse hop_path[1:] with C commands for path_route strategy.
        # hop_path[0] is already handled by the link layer (connection.connect()).
        if self._path_strategy == "path_route" and len(self._hop_path) > 1:
            for hop in self._hop_path[1:]:
                if hop.port is not None:
                    self._send_text(f"C {hop.port} {hop.callsign}")
                else:
                    self._send_text(f"C {hop.callsign}")
                response = self._recv_until_prompt(end_on_cr=True)
                # Relay nodes send "Failure with X" (or similar) when the
                # target is unreachable — detect and raise immediately.
                if "Failure" in response or "No link" in response:
                    raise NodeError(
                        f"Relay could not reach {hop.callsign}: {response.strip()!r}"
                    )
                # Relay nodes send "Connected to X" before the remote node's
                # greeting arrives.  Wait for the remote greeting if needed.
                if not _has_prompt(response) and "Connected to" in response:
                    response += self._recv_until_prompt()
                if not _has_prompt(response):
                    raise NodeError(f"No prompt after C command to {hop.callsign}. Got: {response!r}")
        # Navigate from node to BBS, then trigger the prompt.
        self._send_text("BBS")
        response = self._recv_until_prompt()
        if "Connected to BBS" not in response and not _has_prompt(response):
            raise NodeError(f"Failed to connect to BBS. Got: {response!r}")
        if not _has_prompt(response):
            # Trigger the BBS prompt with a bare CR
            self._send_text("")
            response = self._recv_until_prompt()
        # Some BBS nodes prompt for a name on first connect; reply with callsign.
        if "name" in response.lower():
            self._send_text(self._my_callsign)
            response = self._recv_until_prompt()
        if not _has_prompt(response):
            raise NodeError(f"No BBS prompt received. Got: {response!r}")

    def wait_for_prompt(self) -> None:
        """Consume the node's initial greeting after AX.25 connect."""
        self._recv_until_prompt()

    def list_linked_nodes(self) -> list:
        self._send_text("NODES")
        response = self._recv_until_prompt(end_on_cr=True)
        return parse_nodes_list(response)

    def list_files(self, directory: str = "") -> list[FileHeader]:
        cmd = f"DIR {directory}".strip()
        self._send_text(cmd)
        response = self._recv_until_prompt()
        return parse_file_list(response)

    def read_file(self, filename: str) -> str:
        self._send_text(f"D {filename}")
        response = self._recv_until_prompt()
        lines = response.splitlines()
        body_lines = []
        in_body = False
        for line in lines:
            if not in_body and line.strip() == "":
                in_body = True
                continue
            if in_body and not _has_prompt(line):
                body_lines.append(line)
        return "\n".join(body_lines).strip()

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
            if in_body and not _has_prompt(line):
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

    def post_bulletin(self, category: str, subject: str, body: str) -> None:
        self._send_text(f"SB {category}")
        self._recv_until_prompt(timeout=5.0)
        self._send_text(subject)
        self._recv_until_prompt(timeout=5.0)
        for line in body.splitlines():
            self._send_text(line)
        self._send_text("/EX")
        self._recv_until_prompt()

    def upload_file(self, filename: str, description: str, content: str) -> None:
        """Upload a file to the BBS using the U command.

        Raises NodeError if the encoded content exceeds MAX_FILE_SIZE bytes.
        """
        if len(content.encode()) > MAX_FILE_SIZE:
            raise NodeError(
                f"File too large: {len(content.encode())} bytes "
                f"(max {MAX_FILE_SIZE} bytes)"
            )
        self._send_text(f"U {filename}")
        self._recv_until_prompt(timeout=5.0)  # wait for description prompt
        self._send_text(description)
        self._recv_until_prompt(timeout=5.0)  # wait for content prompt
        for line in content.splitlines():
            self._send_text(line)
        self._send_text("/EX")
        self._recv_until_prompt()
