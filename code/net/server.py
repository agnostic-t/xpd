import json
import select
import socket
from dataclasses import dataclass

from crypto.lterm import LongTermKey

import net.address as address
import net.packets as pck
import net.tcp as tcp


@dataclass
class Client:
    address: address.NetAddress
    connection: socket.socket
    tcpsock: tcp.TCPSocket
    pubkey: str  # ИЗМЕНЕНИЕ: Сюда будем сохранять публичный ключ при коннекте
    is_server: bool = False


class DecServer:
    def __init__(self, bind_address: address.NetAddress, ltk: LongTermKey) -> None:
        self.sock = tcp.TCPSocket(bind_address)
        self.is_running = False

        self.clients: dict[address.NetAddress, Client] = {}
        self.clients_sock: dict[socket.socket, Client] = {}

        self.tokenized: dict[int, Client] = {}
        self.peer_servers: dict[socket.socket, Client] = {}
        self.remote_tokens: dict[int, Client] = {}
        self.forwarded_msgs: dict[int, list[pck.Packet]] = {}

        # ИЗМЕНЕНИЕ: Хранилище публичных ключей для всех известных токенов
        self.token_pubkeys: dict[int, str] = {}

        self.ltk: LongTermKey = ltk

    def start(self):
        self.sock.bind()
        self.sock.listen()
        self.is_running = True

    def end(self):
        self.is_running = False
        self.sock.close()
        for cli in self.clients.values():
            cli.connection.close()

    def _accept_client(self):
        conn, addr = self.sock.sock.accept()
        net_addr = address.NetAddress(ip_addr=addr[0], port=addr[1])
        cli = Client(
            address=net_addr,
            connection=conn,
            tcpsock=tcp.TCPSocket(net_addr),
            pubkey="",
            is_server=False,
        )
        cli.tcpsock.sock = conn
        self.clients[net_addr] = cli
        self.clients_sock[conn] = cli
        print(f"[accept] new client accepted: {str(cli.address)}")

    def _disconnect_client(self, cli: Client):
        print(f"[disconnect] client disconnected: {str(cli.address)}")
        cli.connection.close()

        if cli.is_server:
            if cli.connection in self.peer_servers:
                del self.peer_servers[cli.connection]

            tokens_to_remove = [t for t, c in self.remote_tokens.items() if c is cli]
            for t in tokens_to_remove:
                del self.remote_tokens[t]
                if t in self.token_pubkeys:
                    del self.token_pubkeys[t]
                print(f"[routing] removed route to token: {t}")

            if tokens_to_remove:
                self._broadcast_tokens_remove(tokens_to_remove, exclude_cli=cli)

        else:
            for token, _cli in list(self.tokenized.items()):
                if cli.address == _cli.address:
                    del self.tokenized[token]
                    if token in self.token_pubkeys:
                        del self.token_pubkeys[token]
                    print(f"[disconnect] removed local client token: {token}")

                    self._broadcast_tokens_remove([token])
                    break

        if cli.connection in self.clients_sock:
            del self.clients_sock[cli.connection]
        if cli.address in self.clients:
            del self.clients[cli.address]

    def _broadcast_tokens_remove(
        self, tokens: list[int], exclude_cli: Client | None = None
    ):
        if not tokens:
            return
        pack = pck.Packet(
            from_token=0,
            to_token=0,
            metadata="SERVER_TOKENS_REMOVE",
            text=json.dumps({"tokens": tokens}, ensure_ascii=False),
        )
        for peer_sock, peer_cli in self.peer_servers.items():
            if peer_cli is not exclude_cli:
                self._message(peer_cli, pack)

    def _process_tokens_remove(self, pack: pck.Packet, cli: Client):
        try:
            data = json.loads(pack.text)
            tokens_to_remove = data.get("tokens", [])
            removed_tokens = []
            for t in tokens_to_remove:
                if t in self.remote_tokens:
                    del self.remote_tokens[t]
                    if t in self.token_pubkeys:
                        del self.token_pubkeys[t]
                    removed_tokens.append(t)
            if removed_tokens:
                self._broadcast_tokens_remove(removed_tokens, exclude_cli=cli)
        except Exception as ex:
            print(f"[serv][p2p] failed to parse tokens remove: {ex}")

    def loop(self):
        while self.is_running:
            mon_socks = [self.sock.sock] + list(self.clients_sock.keys())
            readable, _, with_errs = select.select(mon_socks, [], mon_socks, 1.0)

            for sock in with_errs:
                if sock is self.sock.sock:
                    print("[error] server socket error!")
                    self.end()
                    return
                elif sock in self.clients_sock:
                    self._disconnect_client(self.clients_sock[sock])

            for sock in readable:
                if sock is self.sock.sock:
                    self._accept_client()
                else:
                    self._iter(self.clients_sock[sock])

    def _process_suggest(self, pack: pck.Packet, cli: Client):
        try:
            data = json.loads(pack.text)
            target_addr = address.NetAddress(ip_addr=data["ip"], port=data["port"])
            peer_tcpsock = tcp.TCPSocket(target_addr)
            peer_tcpsock.connect()

            peer_cli = Client(
                address=target_addr,
                connection=peer_tcpsock.sock,
                tcpsock=peer_tcpsock,
                pubkey="",
                is_server=True,
            )
            self.clients_sock[peer_tcpsock.sock] = peer_cli
            self.peer_servers[peer_tcpsock.sock] = peer_cli
            self._send_server_hello(peer_cli, is_ack=False)
        except Exception as ex:
            print(f"[serv][suggest] failed to connect to peer server: {ex}")

    def _send_server_hello(self, peer_cli: Client, is_ack: bool):
        # ИЗМЕНЕНИЕ: Отправляем не просто список токенов, а словарь {token: pubkey}
        known_tokens = list(self.tokenized.keys()) + list(self.remote_tokens.keys())
        tokens_dict = {
            t: self.token_pubkeys[t] for t in known_tokens if t in self.token_pubkeys
        }

        metadata = "SERVER_HELLO_ACK" if is_ack else "SERVER_HELLO"
        pack = pck.Packet(
            from_token=0,
            to_token=0,
            metadata=metadata,
            text=json.dumps(
                {"tokens": tokens_dict, "pubkey": self.ltk.export_public_base64()},
                ensure_ascii=False,
            ),
        )
        self._message(peer_cli, pack)

    def _process_server_hello(self, pack: pck.Packet, cli: Client, is_ack: bool):
        if not is_ack:
            cli.is_server = True
            self.peer_servers[cli.connection] = cli
        self._update_remote_tokens(pack, cli)
        if not is_ack:
            self._send_server_hello(cli, is_ack=True)

    def _update_remote_tokens(self, pack: pck.Packet, cli: Client):
        try:
            data = json.loads(pack.text)
            new_tokens_dict = data.get("tokens", {})  # Теперь тут {str(token): pubkey}
            added_tokens = []

            for str_t, pubkey in new_tokens_dict.items():
                t = int(str_t)
                if t not in self.tokenized and t not in self.remote_tokens:
                    self.remote_tokens[t] = cli
                    self.token_pubkeys[t] = pubkey
                    added_tokens.append(t)

            if added_tokens:
                self._broadcast_tokens_update(added_tokens, exclude_cli=cli)
        except Exception as ex:
            print(f"[serv][p2p] failed to parse tokens from peer: {ex}")

    def _broadcast_tokens_update(
        self, tokens: list[int], exclude_cli: Client | None = None
    ):
        if not tokens:
            return
        # ИЗМЕНЕНИЕ: Рассылаем словарь токен->публичный ключ
        tokens_dict = {
            t: self.token_pubkeys[t] for t in tokens if t in self.token_pubkeys
        }
        pack = pck.Packet(
            from_token=0,
            to_token=0,
            metadata="SERVER_TOKENS_UPDATE",
            text=json.dumps({"tokens": tokens_dict}, ensure_ascii=False),
        )
        for _, peer_cli in self.peer_servers.items():
            if peer_cli is not exclude_cli:
                self._message(peer_cli, pack)

    def _process_registration(self, pack: pck.Packet, cli: Client):
        token = pack.from_token
        if token in self.tokenized or token in self.remote_tokens:
            self._message(
                cli,
                pck.Packet(
                    from_token=0,
                    to_token=token,
                    metadata="SERVER_REG_FAILURE",
                    text="Failed",
                ),
            )
        else:
            self.tokenized[token] = cli
            # При регистрации пакет верифицируется в _iter.
            # Значит pack.text гарантированно является публичным ключом клиента, отправившего пакет.
            self.token_pubkeys[token] = cli.pubkey

            self._message(
                cli,
                pck.Packet(
                    from_token=0,
                    to_token=token,
                    metadata="SERVER_REG_SUCCESS",
                    text=self.ltk.export_public_base64(),  # Сервер отдает СВОЙ публичный ключ
                ),
            )
            self._broadcast_tokens_update([token])

    def _process_discovery(self, pack: pck.Packet, cli: Client):
        all_known = list(self.tokenized.keys()) + list(self.remote_tokens.keys())
        # ИЗМЕНЕНИЕ: Отвечаем форматом, который ждет клиент (список списков [pubkey, token])
        tokens_list = [
            [self.token_pubkeys[t], t] for t in all_known if t in self.token_pubkeys
        ]

        self._message(
            cli,
            pck.Packet(
                from_token=0,
                to_token=pack.from_token,
                metadata="SERVER_DISCOVERY_ANS",
                text=json.dumps({"tokens": tokens_list}, ensure_ascii=False),
            ),
        )

    def _process_inc_message(self, pack: pck.Packet, cli: Client):
        if pack.to_token in self.tokenized:
            self.forwarded_msgs.setdefault(pack.to_token, []).append(pack)
        elif pack.to_token in self.remote_tokens:
            peer_server_cli = self.remote_tokens[pack.to_token]
            self._message(
                peer_server_cli, pack, sign=False
            )  # Не подписываем транзитные пакеты

    def _get_msgs_for_peer(self, pack: pck.Packet, cli: Client):
        if (
            pack.from_token not in self.forwarded_msgs
            or not self.forwarded_msgs[pack.from_token]
        ):
            return
        msgs = [msg.serial() for msg in self.forwarded_msgs[pack.from_token]]
        self.forwarded_msgs[pack.from_token] = []

        self._message(
            cli,
            pck.Packet(
                from_token=0,
                to_token=pack.from_token,
                metadata="SERVER_FORWARDED_MSG",
                text=json.dumps({"msgs": msgs}, ensure_ascii=False),
            ),
        )

    def _message(self, cli: Client, msg: pck.Packet, sign: bool = True):
        # ИЗМЕНЕНИЕ: Автоматически подписываем пакеты от лица сервера (from_token=0)
        if sign and msg.from_token == 0:
            msg.sign(self.ltk.export_private_hazmat())
        cli.tcpsock.sendx(json.dumps(msg.serial(), ensure_ascii=False).encode())

    def _iter(self, cli: Client):
        try:
            msg = cli.tcpsock.recvx()
        except ConnectionError:
            self._disconnect_client(cli)
            return

        if not msg:
            self._disconnect_client(cli)
            return

        try:
            packet = pck.Packet.deserial(json.loads(msg.decode()))
        except Exception as ex:
            print(f"[serv][iter] error: {ex}")
            return

        # ==========================================
        # БАРЬЕР БЕЗОПАСНОСТИ: ПРОВЕРКА ПОДПИСЕЙ
        # ==========================================
        is_valid = False

        if packet.metadata in ["SERVER_HELLO", "SERVER_HELLO_ACK"]:
            peer_pubkey = json.loads(packet.text).get("pubkey")
            is_valid = packet.verify(peer_pubkey)
            if is_valid:
                cli.pubkey = peer_pubkey  # Сохраняем ключ peer-сервера

        elif packet.metadata == "REGISTER":
            # Клиент заявляет свой pubkey в тексте
            client_pubkey = packet.text
            is_valid = packet.verify(client_pubkey)
            if is_valid:
                cli.pubkey = client_pubkey

        elif packet.metadata == "MESSAGE":
            # Сквозная верификация: проверяем по ключу ОТПРАВИТЕЛЯ
            sender_pub = self.token_pubkeys.get(packet.from_token)
            if sender_pub:
                is_valid = packet.verify(sender_pub)
            else:
                print(f"[security] DROP: unknown sender pubkey for {packet.from_token}")

        else:
            # Для всего остального (DISCOVERY, FETCH, SUGGEST...)
            # мы используем публичный ключ, закрепленный за соединением (cli.pubkey)
            if cli.pubkey:
                is_valid = packet.verify(cli.pubkey)

        if not is_valid:
            print(f"[serv][security] DROP: Invalid signature for {packet.metadata}")
            return
        # ==========================================

        match packet.metadata:
            case "SERVER_HELLO":
                self._process_server_hello(packet, cli, is_ack=False)
            case "SERVER_HELLO_ACK":
                self._process_server_hello(packet, cli, is_ack=True)
            case "SERVER_TOKENS_UPDATE":
                self._update_remote_tokens(packet, cli)
            case "SERVER_TOKENS_REMOVE":
                self._process_tokens_remove(packet, cli)
            case "REGISTER":
                self._process_registration(packet, cli)
            case "DISCOVERY":
                self._process_discovery(packet, cli)
            case "SUGGEST":
                self._process_suggest(packet, cli)
            case "MESSAGE":
                self._process_inc_message(packet, cli)
            case "FETCH":
                self._get_msgs_for_peer(packet, cli)
