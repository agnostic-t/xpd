class NetAddress:
    def __init__(self, ip_addr: str, port: int) -> None:
        self.ip_addr = ip_addr
        self.port = port

    def convert_to_sock(self) -> tuple[str, int]:
        return (self.ip_addr, self.port)

    def __str__(self) -> str:
        return f"{self.ip_addr}:{self.port}"
