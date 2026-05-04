from dataclasses import dataclass

import net.address as address
import net.tcp as tcp


@dataclass
class DecMessage:
    from_cli: int
    text: str


@dataclass
class DecPeer:
    token: int


class DecClient:
    def __init__(self, serv_addr: address.NetAddress) -> None:
        self.addr = serv_addr
        self.sock = tcp.TCPSocket(self.addr)

    def connect(self):
        self.sock.connect()

    def stop(self):
        self.sock.close()

    def wait_messages(self, timeout: int) -> None:
        pass

    def register(self, token: int) -> None:
        pass

    def discovery(self) -> list[DecPeer]:
        return []

    def message(self, peer: DecPeer, msg: str) -> None:
        pass

    def has_messages(self) -> bool:
        return False

    def get_message(self) -> DecMessage:
        return DecMessage(from_cli=0, text="")

    def _send(self, data: str) -> None:
        self.sock.sendx(data.encode())

    def _recv(self) -> str:
        return self.sock.recvx().decode()
