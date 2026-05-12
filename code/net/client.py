import json
import time
from enum import Enum
from select import select

from crypto.lterm import LongTermKey
import net.address as address
import net.packets as pck
import net.tcp as tcp


class ClientStates(Enum):
    NOT_CONNECTED = 0
    CONNECTED = 1
    WAITING_REG_ANS = 2
    REGISTERED = 3


class DecClient:
    def __init__(self, serv_addr: address.NetAddress, ltk: LongTermKey) -> None:
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
        self.known_pubkeys: dict[int, str] = {}

        self._unverified_backlog: list[pck.Packet] =[]

        self.ltk: LongTermKey = ltk
        self.server_pubkey: str = ""
        self.last_discovery: list[tuple[str, int]] = []

    def connect(self):
        self.sock.connect()
        self.running = True
        self.state = ClientStates.CONNECTED

    def stop(self):
        self.sock.close()

    def can_run(self) -> bool:
        return self.running

    def wait_message(self, timeout: float) -> pck.Packet | None:
        if self.state == ClientStates.NOT_CONNECTED:
            return None

        mon_socks = [self.sock.sock]
        readable, _, with_errs = select(mon_socks,[], mon_socks, timeout)

        if readable:
            try:
                str_data = self._recv()
            except Exception as ex:
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
                self.running = False
                self.state = ClientStates.NOT_CONNECTED
                return None

            return pck.Packet.deserial(json_data)

        if with_errs:
            self.running = False
            self.state = ClientStates.NOT_CONNECTED
            return None

        return None

    def register(self, token: int) -> None:
        if self.state != ClientStates.CONNECTED:
            return

        self.token = token
        pack = pck.Packet(
            from_token=self.token,
            to_token=0,
            text=self.ltk.export_public_base64(),
            metadata="REGISTER",
        )
        pack.sign(self.ltk.export_private_hazmat())

        jsoned = json.dumps(pack.serial(), ensure_ascii=False)
        self._send(jsoned)

        self.state = ClientStates.WAITING_REG_ANS

    def discovery(self) -> None:
        if self.state != ClientStates.REGISTERED:
            return

        pack = pck.Packet(
            from_token=self.token, to_token=0, text="", metadata="DISCOVERY"
        )
        pack.sign(self.ltk.export_private_hazmat())

        jsoned = json.dumps(pack.serial(), ensure_ascii=False)
        self._send(jsoned)

        self.next_discovery_time = time.time() + 5

    def message(self, peer_token: int, msg: str) -> None:
        if self.state != ClientStates.REGISTERED:
            return

        pack = pck.Packet(
            from_token=self.token, to_token=peer_token, text=msg, metadata="MESSAGE"
        )
        pack.sign(self.ltk.export_private_hazmat())

        jsoned = json.dumps(pack.serial(), ensure_ascii=False)
        self._send(jsoned)

    def fetch_msgs(self, new_dt: float):
        if self.state != ClientStates.REGISTERED:
            return

        pack = pck.Packet(from_token=self.token, to_token=0, text="", metadata="FETCH")
        pack.sign(self.ltk.export_private_hazmat())

        jsoned = json.dumps(pack.serial(), ensure_ascii=False)
        self._send(jsoned)

        self.next_fetch_time = time.time() + new_dt

    def suggest(self, serv_addr: address.NetAddress) -> None:
        if self.state == ClientStates.NOT_CONNECTED:
            return

        json_data = json.dumps(
            {"ip": serv_addr.ip_addr, "port": serv_addr.port}, ensure_ascii=False
        )
        pack = pck.Packet(
            from_token=self.token, to_token=0, text=json_data, metadata="SUGGEST"
        )
        pack.sign(self.ltk.export_private_hazmat())

        jsoned = json.dumps(pack.serial(), ensure_ascii=False)
        self._send(jsoned)

    def process_msg(self, msg: pck.Packet):
        if self.state == ClientStates.NOT_CONNECTED:
            return

        if msg.metadata == "SERVER_REG_SUCCESS":
            temp_pubkey = msg.text
            if not msg.verify(temp_pubkey):
                print("[process][fatal] Failed to verify SERVER_REG_SUCCESS signature!")
                self.running = False
                return
            self.server_pubkey = temp_pubkey

        elif msg.metadata != "SERVER_REG_FAILURE":
            if not msg.verify(self.server_pubkey):
                print("[process][fatal] Invalid signature from server!")
                self.running = False
                return

        match msg.metadata:
            case "SERVER_REG_FAILURE":
                if self.state == ClientStates.WAITING_REG_ANS:
                    self.state = ClientStates.NOT_CONNECTED
                    self.running = False

            case "SERVER_REG_SUCCESS":
                if self.state == ClientStates.WAITING_REG_ANS:
                    self.state = ClientStates.REGISTERED

            case "SERVER_DISCOVERY_ANS":
                if self.state != ClientStates.REGISTERED:
                    return

                try:
                    json_data = json.loads(msg.text)
                except Exception:
                    return

                tokens = json_data["tokens"]

                new_peers = [[pkey, t]
                    for pkey, t in tokens
                    if t != self.token and t not in self.known_peers
                ]

                self.last_discovery = tokens.copy()

                if len(new_peers) > 0:
                    for pkey, t in new_peers:
                        self.known_pubkeys[t] = pkey
                        self.known_peers.add(t)
                        self._pending_peers.add(t)

                if self._unverified_backlog:
                    to_process = self._unverified_backlog[:]
                    self._unverified_backlog.clear()

                    for back_pack in to_process:
                        if back_pack.from_token in self.known_peers:
                            if not back_pack.verify(self.known_pubkeys[back_pack.from_token]):
                                print(f"[process][backlog] failed to verify backlogged msg from {back_pack.from_token}")
                                continue

                            self.messages.setdefault(back_pack.from_token,[]).append(back_pack.text)
                            self._pending_messages.setdefault(back_pack.from_token,[]).append(back_pack.text)
                            print(f"[process][backlog] successfully processed backlogged packet from {back_pack.from_token}")
                        else:
                            if len(self._unverified_backlog) < 50:
                                self._unverified_backlog.append(back_pack)

            case "SERVER_FORWARDED_MSG":
                if self.state != ClientStates.REGISTERED:
                    return

                try:
                    json_data = json.loads(msg.text)
                except Exception:
                    return

                msgs: list[dict] = json_data["msgs"]
                for _msg in msgs:
                    fwd_pack = pck.Packet.deserial(_msg)

                    if fwd_pack.from_token not in self.known_peers:
                        print(f"[process][fwd_msg] unknown peer {fwd_pack.from_token}, queueing & forcing discovery")

                        if len(self._unverified_backlog) < 50:
                            self._unverified_backlog.append(fwd_pack)

                        self.next_discovery_time = 0
                        continue

                    if not fwd_pack.verify(self.known_pubkeys[fwd_pack.from_token]):
                        print(f"[process][fwd_msg] failed to verify msg from {fwd_pack.from_token}")
                        continue

                    self.messages.setdefault(fwd_pack.from_token,[]).append(fwd_pack.text)
                    self._pending_messages.setdefault(fwd_pack.from_token,[]).append(fwd_pack.text)

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
