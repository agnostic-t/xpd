import json
import time
from dataclasses import dataclass
from enum import Enum
from select import select

import net.address as address
import net.packets as pck
import net.tcp as tcp


class ClientStates(Enum):
    NOT_CONNECTED = 0
    CONNECTED = 1
    WAITING_REG_ANS = 2
    REGISTERED = 3


class DecClient:
    def __init__(self, serv_addr: address.NetAddress) -> None:
        self.addr = serv_addr
        self.sock = tcp.TCPSocket(self.addr)
        self.token: int = 0
        self.running: bool = False
        self.state: ClientStates = ClientStates.NOT_CONNECTED

        self.next_discovery_time = 0
        self.next_fetch_time = 0
        self.messages: dict[int, list[str]] = {}

        self._pending_messages: dict[int, list[str]] = {}
        self._pending_peers: set[int] = set()

        self.known_peers: set[int] = set()

    def connect(self):
        self.sock.connect()
        self.running = True
        self.state = ClientStates.CONNECTED

    def stop(self):
        self.sock.close()

    def can_run(self) -> bool:
        return self.running

    def wait_message(self, timeout: int) -> pck.Packet | None:
        if self.state == ClientStates.NOT_CONNECTED:
            print("[client][wait_msg] cannot wait messages, not connected")
            return

        mon_socks = [self.sock.sock]

        readable, _, with_errs = select(mon_socks, [], mon_socks, timeout)

        if readable:
            try:
                str_data = self._recv()
            except Exception as ex:
                print(f"[wait_msgs] something happened with connection: {ex}")
                self.running = False
                self.state = ClientStates.NOT_CONNECTED
                return None

            if not str_data:
                self.running = False
                self.state = ClientStates.NOT_CONNECTED
                raise RuntimeError("Unexpected behavior, data cannot be None")

            try:
                json_data = json.loads(str_data)
            except Exception as ex:
                print(f"[wait_msgs] failed get json data: {ex}")
                self.running = False
                self.state = ClientStates.NOT_CONNECTED
                return None

            return pck.Packet.deserial(json_data)

        if with_errs:
            print("[wait_msgs] something happened with connection: POLLHUP/POLLERR")
            self.running = False
            self.state = ClientStates.NOT_CONNECTED
            return None

        return None

    def register(self, token: int) -> None:
        if self.state != ClientStates.CONNECTED:
            print("[client][register] cannot start registration, not connected")
            return

        self.token = token

        pack = pck.Packet(
            from_token=self.token, to_token=0, text="", metadata="REGISTER"
        )

        jsoned = json.dumps(pack.serial(), ensure_ascii=False)
        self._send(jsoned)

        self.state = ClientStates.WAITING_REG_ANS

    def discovery(self) -> None:
        if self.state != ClientStates.REGISTERED:
            print("[client][discovery] cannot start discovery, not registered")
            return

        pack = pck.Packet(
            from_token=self.token, to_token=0, text="", metadata="DISCOVERY"
        )

        jsoned = json.dumps(pack.serial(), ensure_ascii=False)
        self._send(jsoned)

        self.next_discovery_time = time.time() + 5

    def message(self, peer_token: int, msg: str) -> None:
        if self.state != ClientStates.REGISTERED:
            print("[client][message] cannot send message, not registered")
            return

        pack = pck.Packet(
            from_token=self.token, to_token=peer_token, text=msg, metadata="MESSAGE"
        )

        jsoned = json.dumps(pack.serial(), ensure_ascii=False)
        self._send(jsoned)

    def fetch_msgs(self, new_dt: float):
        if self.state != ClientStates.REGISTERED:
            print("[client][fetch_msgs] cannot fetch messages, not registered")
            return

        pack = pck.Packet(from_token=self.token, to_token=0, text="", metadata="FETCH")

        jsoned = json.dumps(pack.serial(), ensure_ascii=False)
        self._send(jsoned)

        self.next_fetch_time = time.time() + new_dt

    def suggest(self, serv_addr: address.NetAddress) -> None:
        if self.state == ClientStates.NOT_CONNECTED:
            print("[client][suggest] cannot suggest server, not connected")
            return

        json_data = json.dumps(
            {"ip": serv_addr.ip_addr, "port": serv_addr.port}, ensure_ascii=False
        )
        pack = pck.Packet(
            from_token=self.token, to_token=0, text=json_data, metadata="SUGGEST"
        )

        jsoned = json.dumps(pack.serial(), ensure_ascii=False)
        self._send(jsoned)

    def process_msg(self, msg: pck.Packet):
        if self.state == ClientStates.NOT_CONNECTED:
            print("[client][process_msg] cannot start discovery, not registered")
            return

        match msg.metadata:
            case "SERVER_REG_FAILURE":
                if self.state == ClientStates.WAITING_REG_ANS:
                    print(f"[process] failed to register: {msg.text}")
                    self.state = ClientStates.NOT_CONNECTED
                    self.running = False
                else:
                    print(
                        f"[process] warning: something happened with server, wrong metadata code received ({msg.metadata})"
                    )
            case "SERVER_REG_SUCCESS":
                if self.state == ClientStates.WAITING_REG_ANS:
                    print(f"[process] successfully registered: {msg.text}")
                    self.state = ClientStates.REGISTERED
                else:
                    print(
                        f"[process] warning: something happened with server, wrong metadata code received ({msg.metadata})"
                    )

            case "SERVER_DISCOVERY_ANS":
                if self.state != ClientStates.REGISTERED:
                    print(
                        f"[process] warning: something happened with server, wrong metadata code received ({msg.metadata})"
                    )
                    return

                data = msg.text
                try:
                    json_data = json.loads(data)
                except Exception as ex:
                    print(
                        f"[process] failed to process JSON data in SERVER_DISCOVERY_ANS: {ex}"
                    )
                    return

                tokens = json_data["tokens"]
                tokens = [
                    t for t in tokens if t != self.token and t not in self.known_peers
                ]

                if len(tokens) == 0:
                    # print("[process][discovery] no new aquired peers from discovery")
                    return

                print(
                    f"[process][discovery] new peers: {len(tokens)}, db size: {len(self.known_peers) + len(tokens)}"
                )
                self.known_peers.update(tokens)
                self._pending_peers.update(tokens)

            case "SERVER_FORWARDED_MSG":
                if self.state != ClientStates.REGISTERED:
                    print(
                        f"[process] warning: something happened with server, wrong metadata code received ({msg.metadata})"
                    )
                    return

                data = msg.text
                try:
                    json_data = json.loads(data)
                except Exception as ex:
                    print(
                        f"[process][fwd_msg] failed to get proper JSON from data from server: {ex}"
                    )
                    return

                msgs: list[dict] = json_data["msgs"]
                for _msg in msgs:
                    fwd_pack = pck.Packet.deserial(_msg)
                    if fwd_pack.from_token not in self.known_peers:
                        print(
                            f"[process][fwd_msg] dropping packet from unknown peer: {fwd_pack.from_token}"
                        )
                        continue

                    self.messages.setdefault(fwd_pack.from_token, []).append(
                        fwd_pack.text
                    )
                    self._pending_messages.setdefault(fwd_pack.from_token, []).append(
                        fwd_pack.text
                    )
                    print(
                        f"[process][fwd_msg] got new packet from {fwd_pack.from_token}: {fwd_pack.text}"
                    )

    def get_new_messages(self) -> dict[int, list[str]]:
        result = dict(self._pending_messages)
        self._pending_messages.clear()
        return result

    def get_new_peers(self) -> list[int]:
        result = list(self._pending_peers)
        self._pending_peers.clear()
        return result

    def has_new_peers(self) -> bool:
        return bool(self._pending_peers)

    def has_new_messages(self) -> bool:
        return bool(self._pending_messages)

    def _send(self, data: str) -> None:
        self.sock.sendx(data.encode())

    def _recv(self) -> str | None:
        data = self.sock.recvx()
        if data:
            return data.decode()
        return None
