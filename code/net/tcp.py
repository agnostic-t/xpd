import socket

import net.address


class TCPSocket:
    def __init__(self, addr: net.address.NetAddress) -> None:
        self.addr: net.address.NetAddress = addr
        self.sock: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def bind(self):
        self.sock.bind(self.addr.convert_to_sock())

    def listen(self):
        self.sock.listen()

    def close(self):
        self.sock.close()

    def connect(self):
        self.sock.connect(self.addr.convert_to_sock())

    def recv(self, n: int) -> bytes:
        return self.sock.recv(n)

    def send(self, data: bytes) -> int:
        return self.sock.send(data)

    def sendx(self, data: bytes | bytearray) -> None:
        length_prefix = len(data).to_bytes(4, byteorder="big")

        self.sock.sendall(length_prefix)
        self.sock.sendall(data)

    def recvx(self) -> bytearray | None:
        length_prefix = self._recvall(4)
        if not length_prefix:
            return None

        to_recv = int.from_bytes(length_prefix, byteorder="big")
        if to_recv > 1024 * 1024 * 5:
            print(f"[tcp][warning] message is too big: {to_recv} bytes")
            return None

        return self._recvall(to_recv)

    def _recvall(self, n: int) -> bytearray | None:
        data = bytearray()
        while len(data) < n:
            packet = self.sock.recv(n - len(data))
            if not packet:
                return None
            data.extend(packet)
        return data
