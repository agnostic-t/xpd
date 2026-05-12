import argparse
from hashlib import sha256
import json
import os
import queue
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import db.chat as chd
import gui.client as cli
from crypto.api import ClientStorage, EncryptedChannel
from crypto.lterm import LongTermKey
from net import address, client


class ChanState(Enum):
    NOT_HANDSHAKED = 0
    AWAITING_FINAL = 1
    HANDSHAKED = 2
    FAILED = 3


@dataclass
class ChanContext:
    state: ChanState
    side: int


class ChanStorage:
    def __init__(self, storage: ClientStorage, self_token: int) -> None:
        self.chans: dict[int, EncryptedChannel] = {}
        self.states: dict[int, ChanContext] = {}

        self.storage = storage
        self.self_token = self_token

    def new_peer(self, token: int, peer_pubkey_b64: str, ncli: client.DecClient):
        if token in self.states:
            return

        peer_pub_raw = LongTermKey.from_base64(
            peer_pubkey_b64, False
        ).export_public_raw()
        self.chans[token] = EncryptedChannel(self.storage, known_peer_id=peer_pub_raw)

        is_initiator = self.self_token > token
        self.states[token] = ChanContext(
            state=ChanState.NOT_HANDSHAKED, side=0 if is_initiator else 1
        )

        if is_initiator:
            print(f"[hsh] starting handshake with {token} (as initiator)")
            hs_msg = self.chans[token].hsh_start()
            self.states[token].state = ChanState.AWAITING_FINAL
            ncli.message(token, json.dumps({"type": "hs_init", "data": hs_msg}))

    def process_hs_msg(self, token: int, msg_dict: dict, ncli: client.DecClient):
        ctx = self.states.get(token)
        chan = self.chans.get(token)

        if not ctx or not chan:
            return

        msg_type = msg_dict.get("type")
        msg_data = msg_dict.get("data")

        if (
            msg_type == "hs_init"
            and ctx.side == 1
            and ctx.state == ChanState.NOT_HANDSHAKED
        ):
            resp_msg = chan.hsh_accept(msg_data)
            ctx.state = ChanState.HANDSHAKED
            print(f"[hsh] successfully handshaked with {token} (as responder)")

            ncli.message(token, json.dumps({"type": "hs_resp", "data": resp_msg}))

        elif (
            msg_type == "hs_resp"
            and ctx.side == 0
            and ctx.state == ChanState.AWAITING_FINAL
        ):
            success = chan.hsh_finalize(msg_data)
            if success:
                ctx.state = ChanState.HANDSHAKED
                print(f"[hsh] successfully handshaked with {token} (as initiator)")
            else:
                ctx.state = ChanState.FAILED
                print(f"[hsh] failed to handshake with {token}")

    def decrypt(self, token: int, msg: str) -> str:
        if not self.check(token):
            raise ValueError("Cannot decrypt: Channel not handshaked")
        return self.chans[token].decrypt(msg)

    def encrypt(self, token: int, msg: str) -> str:
        if not self.check(token):
            raise ValueError("Cannot encrypt: Channel not handshaked")
        return self.chans[token].encrypt(msg)

    def check(self, token: int) -> bool:
        ctx = self.states.get(token)
        return ctx is not None and ctx.state == ChanState.HANDSHAKED


@dataclass
class NetContext:
    is_running: threading.Event
    inbox: queue.Queue
    outbox: queue.Queue
    gui: cli.GUIClient
    ncli: client.DecClient

    storage: ClientStorage
    chans: ChanStorage


def netthread(ctx: NetContext):
    try:
        ctx.ncli.connect()
        print(f"[client] connected to {str(ctx.ncli.addr)}")
    except Exception as ex:
        print(f"[client] failed to connect: {ex}")
        ctx.gui.force_exit()
        return

    print(f"[client] self token: {ctx.chans.self_token}")
    ctx.ncli.register(ctx.chans.self_token)

    while ctx.ncli.can_run():
        now = time.time()
        if ctx.ncli.state == client.ClientStates.REGISTERED:
            if now >= ctx.ncli.next_discovery_time:
                ctx.ncli.discovery()
                lt = [t for _, t in ctx.ncli.last_discovery.copy()]

                for p in ctx.gui.contacts_exists:
                    if ctx.gui.cards[p].is_online != p in lt:
                        print(f"[stats] {p} turned {"online" if p in lt else "offline"}")
                        ctx.gui.cards[p].is_online = p in lt

                    ctx.gui.set_contact_online(token=p, is_online=p in lt)

                ctx.ncli.last_discovery = []

            if now >= ctx.ncli.next_fetch_time:
                ctx.ncli.fetch_msgs(1)

        try:
            pkt = ctx.ncli.wait_message(timeout=1)
        except Exception as ex:
            print(f"[client] interrupted ({ex}), exiting...")
            ctx.gui.force_exit()
            break

        if pkt:
            ctx.ncli.process_msg(pkt)

        if ctx.ncli.has_new_peers():
            peers: list[int] = ctx.ncli.get_new_peers()
            for p in peers:

                peer_pub_b64 = ctx.ncli.known_pubkeys.get(p)
                if peer_pub_b64:
                    ctx.chans.new_peer(p, peer_pub_b64, ctx.ncli)
                    ctx.inbox.put(("peer", (peer_pub_b64, p)))

        if ctx.ncli.has_new_messages():
            msgs: dict[int, list[str]] = ctx.ncli.get_new_messages()
            for t, txts in msgs.items():
                for txt in txts:
                    try:
                        msg_dict = json.loads(txt)
                        msg_type = msg_dict.get("type")

                        if msg_type in ["hs_init", "hs_resp"]:
                            ctx.chans.process_hs_msg(t, msg_dict, ctx.ncli)

                        elif msg_type == "chat":
                            if ctx.chans.check(t):
                                plain_text = ctx.chans.decrypt(t, msg_dict["data"])
                                ctx.inbox.put(
                                    ("msg", (t, plain_text, int(time.time()), False))
                                )
                            else:
                                print(
                                    f"[main] WARNING: received chat msg from {t}, but channel not handshaked."
                                )

                    except json.JSONDecodeError:
                        print(f"[main] Failed to decode JSON message from {t}")
                    except Exception as ex:
                        print(f"[main] Crypto error processing message from {t}: {ex}")

        while not ctx.outbox.empty():
            tkn, plain_msg = ctx.outbox.get_nowait()

            if ctx.chans.check(tkn):
                try:
                    enc_msg = ctx.chans.encrypt(tkn, plain_msg)
                    payload = json.dumps({"type": "chat", "data": enc_msg})
                    ctx.ncli.message(tkn, payload)
                    print(f"[main] Sent encrypted message to {tkn}")
                except Exception as ex:
                    print(f"[main] Failed to encrypt/send msg to {tkn}: {ex}")
            else:
                print(
                    f"[main] Failed to send msg to {tkn}: Channel not handshaked yet."
                )

    ctx.ncli.stop()


def main(ip: str, port: int, database: str, password: str, clean: bool):
    chat_db = chd.ChatDatabase(database)
    if clean:
        print("[main] cleaning database")
        chat_db.clear(True, True)

    storage = ClientStorage(password, str(Path(database) / "keys"))

    app = cli.GUIClient(chat_db)
    ncli = client.DecClient(address.NetAddress(ip, port), storage.ltk)

    ctx = NetContext(
        gui=app,
        inbox=app.inbox,
        outbox=app.outbox,
        is_running=app.running,
        ncli=ncli,
        storage=storage,
        chans=ChanStorage(storage, self_token=storage.gen_uid()),
    )

    print("[main] self name:", sha256(f"{storage.gen_uid()}".encode()).hexdigest()[2:9])

    nthr = threading.Thread(target=netthread, args=(ctx,), daemon=True)
    nthr.start()

    app.build()
    app.import_from_db()
    app.run()

    ncli.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GUI+NET Client for decmsg")
    parser.add_argument("-i", "--ip", help="IP address to bind/connect", required=True)
    parser.add_argument(
        "-p", "--port", type=int, help="PORT to bind/connect", required=True
    )
    parser.add_argument(
        "-d",
        "--database",
        type=str,
        help="Path to directory to store message/contact databases",
        default=".databases",
    )

    parser.add_argument(
        "-c", "--clean", action="store_true", help="Start with clean chat databases"
    )

    args = parser.parse_args()

    os.makedirs(args.database, exist_ok=True)
    main(args.ip, args.port, args.database, "12345", args.clean)
