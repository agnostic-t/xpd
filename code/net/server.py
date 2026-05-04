import json
import select
import socket
from dataclasses import dataclass

import net.address as address
import net.packets as pck
import net.tcp as tcp


@dataclass
class Client:
    address: address.NetAddress
    connection: socket.socket
    tcpsock: tcp.TCPSocket
    is_server: bool = False


class DecServer:
    def __init__(self, bind_address: address.NetAddress) -> None:
        self.sock = tcp.TCPSocket(bind_address)
        self.is_running = False

        self.clients: dict[address.NetAddress, Client] = {}
        self.clients_sock: dict[socket.socket, Client] = {}

        # Local clients
        self.tokenized: dict[int, Client] = {}

        # Servers
        self.peer_servers: dict[socket.socket, Client] = {}

        # Remote client: server which knows it
        self.remote_tokens: dict[int, Client] = {}

        # to_token: Packet
        self.forwarded_msgs: dict[int, list[pck.Packet]] = {}

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
                print(f"[routing] removed route to token: {t}")

            if tokens_to_remove:
                self._broadcast_tokens_remove(tokens_to_remove, exclude_cli=cli)

        else:
            for token, _cli in list(self.tokenized.items()):
                if cli.address == _cli.address:
                    del self.tokenized[token]
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
                    removed_tokens.append(t)
                    print(f"[serv][routing] route to {t} removed via network update")

            if removed_tokens:
                self._broadcast_tokens_remove(removed_tokens, exclude_cli=cli)

        except Exception as ex:
            print(f"[serv][p2p] failed to parse tokens remove from peer: {ex}")

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
                    client = self.clients_sock[sock]
                    self._iter(client)

    def _process_suggest(self, pack: pck.Packet, cli: Client):
        print(f"[serv][suggest] client suggested to connect to: {pack.text}")
        try:
            data = json.loads(pack.text)
            target_addr = address.NetAddress(ip_addr=data["ip"], port=data["port"])

            peer_tcpsock = tcp.TCPSocket(target_addr)
            peer_tcpsock.connect()

            peer_cli = Client(
                address=target_addr,
                connection=peer_tcpsock.sock,
                tcpsock=peer_tcpsock,
                is_server=True,
            )
            self.clients_sock[peer_tcpsock.sock] = peer_cli
            self.peer_servers[peer_tcpsock.sock] = peer_cli

            print(
                f"[serv][suggest] successfully connected to peer server {target_addr}"
            )

            self._send_server_hello(peer_cli, is_ack=False)

        except Exception as ex:
            print(f"[serv][suggest] failed to connect to peer server: {ex}")

    def _send_server_hello(self, peer_cli: Client, is_ack: bool):
        known_tokens = list(self.tokenized.keys()) + list(self.remote_tokens.keys())
        metadata = "SERVER_HELLO_ACK" if is_ack else "SERVER_HELLO"

        pack = pck.Packet(
            from_token=0,
            to_token=0,
            metadata=metadata,
            text=json.dumps({"tokens": known_tokens}, ensure_ascii=False),
        )
        self._message(peer_cli, pack)

    def _process_server_hello(self, pack: pck.Packet, cli: Client, is_ack: bool):
        if not is_ack:
            print(f"[serv][p2p] peer {cli.address} identified as Server")
            cli.is_server = True
            self.peer_servers[cli.connection] = cli

        self._update_remote_tokens(pack, cli)

        if not is_ack:
            self._send_server_hello(cli, is_ack=True)

    def _update_remote_tokens(self, pack: pck.Packet, cli: Client):
        try:
            data = json.loads(pack.text)
            new_tokens = data.get("tokens", [])

            added_tokens = []
            for t in new_tokens:
                if t not in self.tokenized and t not in self.remote_tokens:
                    self.remote_tokens[t] = cli
                    added_tokens.append(t)
                    print(
                        f"[serv][routing] learned route to token {t} via server {cli.address}"
                    )

            if added_tokens:
                self._broadcast_tokens_update(added_tokens, exclude_cli=cli)

        except Exception as ex:
            print(f"[serv][p2p] failed to parse tokens from peer: {ex}")

    def _broadcast_tokens_update(
        self, tokens: list[int], exclude_cli: Client | None = None
    ):
        if not tokens:
            return

        pack = pck.Packet(
            from_token=0,
            to_token=0,
            metadata="SERVER_TOKENS_UPDATE",
            text=json.dumps({"tokens": tokens}, ensure_ascii=False),
        )

        for _, peer_cli in self.peer_servers.items():
            if peer_cli is not exclude_cli:
                self._message(peer_cli, pack)

    def _process_registration(self, pack: pck.Packet, cli: Client):
        print(
            f"[serv][reg] new client registers: {str(cli.address)}, token: {pack.from_token}"
        )

        token = pack.from_token
        if token in self.tokenized or token in self.remote_tokens:
            print("[serv][reg] cannot register such client, already exists in network")
            self._message(
                cli,
                pck.Packet(
                    from_token=0,
                    to_token=token,
                    metadata="SERVER_REG_FAILURE",
                    text="Failed to register",
                ),
            )
        else:
            print("[serv][reg] registered new local client")
            self._message(
                cli,
                pck.Packet(
                    from_token=0,
                    to_token=token,
                    metadata="SERVER_REG_SUCCESS",
                    text="Successfully registered new token",
                ),
            )

            self.tokenized[token] = cli
            self._broadcast_tokens_update([token])

    def _process_discovery(self, pack: pck.Packet, cli: Client):
        print(
            f"[serv][discovery] requested discovery from {str(cli.address)} (T:{pack.from_token})"
        )

        all_known_tokens = list(self.tokenized.keys()) + list(self.remote_tokens.keys())

        json_data = json.dumps({"tokens": all_known_tokens}, ensure_ascii=False)
        self._message(
            cli,
            pck.Packet(
                from_token=0,
                to_token=pack.from_token,
                metadata="SERVER_DISCOVERY_ANS",
                text=json_data,
            ),
        )

    def _process_inc_message(self, pack: pck.Packet, cli: Client):
        print(f"[serv][inc_msg] message from {pack.from_token} -> {pack.to_token}")

        if pack.to_token in self.tokenized:
            if pack.to_token not in self.forwarded_msgs:
                self.forwarded_msgs[pack.to_token] = [pack]
            else:
                self.forwarded_msgs[pack.to_token].append(pack)

            print(f"[serv][inc_msg] stored for local client: {pack.to_token}")

        elif pack.to_token in self.remote_tokens:
            peer_server_cli = self.remote_tokens[pack.to_token]

            self._message(peer_server_cli, pack)

            print(f"[serv][inc_msg] forwarded to peer server for: {pack.to_token}")

        else:
            print(f"[serv][inc_msg] DROP: unknown destination token {pack.to_token}")

    def _get_msgs_for_peer(self, pack: pck.Packet, cli: Client):
        if pack.from_token not in self.forwarded_msgs:
            return []

        msgs = [msg.serial() for msg in self.forwarded_msgs[pack.from_token]]
        if msgs == []:
            return

        json_data = json.dumps({"msgs": msgs}, ensure_ascii=False)

        self.forwarded_msgs[pack.from_token] = []
        self._message(
            cli,
            pck.Packet(
                from_token=0,
                to_token=pack.from_token,
                metadata="SERVER_FORWARDED_MSG",
                text=json_data,
            ),
        )

    def _message(self, cli: Client, msg: pck.Packet):
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

        str_data = msg.decode()
        try:
            json_data: dict = json.loads(str_data)
        except Exception as ex:
            print(f"[serv][iter] failed to load JSON data: {ex}")
            return

        packet = pck.Packet.deserial(json_data)
        print(
            f"[serv][pack] got pkt: {packet.from_token}->{packet.to_token}: {packet.text[:30]}... ({packet.metadata})"
        )

        match packet.metadata:
            # P2P server cmds
            case "SERVER_HELLO":
                self._process_server_hello(packet, cli, is_ack=False)
            case "SERVER_HELLO_ACK":
                self._process_server_hello(packet, cli, is_ack=True)
            case "SERVER_TOKENS_UPDATE":
                self._update_remote_tokens(packet, cli)
            case "SERVER_TOKENS_REMOVE":
                self._process_tokens_remove(packet, cli)

            # client cmds
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
