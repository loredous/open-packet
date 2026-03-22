import socket
import threading
import pytest
from open_packet.transport.tcp import TCPTransport
from open_packet.transport.base import TransportError


def make_echo_server(host: str, port: int) -> threading.Thread:
    """Minimal echo server for testing."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(1)
    server.settimeout(2)

    def serve():
        try:
            conn, _ = server.accept()
            conn.settimeout(1)
            try:
                while True:
                    data = conn.recv(1024)
                    if not data:
                        break
                    conn.sendall(data)
            except (socket.timeout, ConnectionResetError):
                pass
            finally:
                conn.close()
        except socket.timeout:
            pass
        finally:
            server.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    return t


def test_tcp_connect_send_receive():
    host, port = "127.0.0.1", 15432
    make_echo_server(host, port)
    import time; time.sleep(0.05)

    t = TCPTransport(host=host, port=port)
    t.connect()
    try:
        t.send_bytes(b"\xc0\x00hello\xc0")
        data = t.receive_bytes(timeout=1.0)
        assert data == b"\xc0\x00hello\xc0"
    finally:
        t.disconnect()


def test_tcp_connect_failure_raises():
    t = TCPTransport(host="127.0.0.1", port=19999)
    with pytest.raises(TransportError, match="connect"):
        t.connect()


def test_tcp_send_without_connect_raises():
    t = TCPTransport(host="127.0.0.1", port=8001)
    with pytest.raises(TransportError, match="not connected"):
        t.send_bytes(b"data")
