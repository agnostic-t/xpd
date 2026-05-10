import argparse
import os
import queue
import random
import threading
import time
from dataclasses import dataclass
from re import L

import db.chat as chd
import gui.client as cli
from net import address, client


@dataclass
class NetContext:
    is_running: threading.Event
    inbox: queue.Queue
    outbox: queue.Queue
    gui: cli.GUIClient
    ncli: client.DecClient


def netthread(ctx: NetContext):
    try:
        ctx.ncli.connect()
        print(f"[client] connected to {str(ctx.ncli.addr)}")
    except Exception as ex:
        print(f"[client] failed to connect: {ex}")
        ctx.gui.force_exit()
        return

    token = random.randint(0, 100000000000)
    print(f"[client] self token: {token}")

    ctx.ncli.register(token)

    while ctx.ncli.can_run():
        now = time.time()
        if ctx.ncli.state == client.ClientStates.REGISTERED:
            if now >= ctx.ncli.next_discovery_time:
                ctx.ncli.discovery()
            if now >= ctx.ncli.next_fetch_time:
                ctx.ncli.fetch_msgs(0.5)

        try:
            pkt = ctx.ncli.wait_message(timeout=0)
        except Exception as ex:
            print(f"[client] interrupted ({ex}), exiting...")
            ctx.gui.force_exit()
            break

        if pkt:
            ctx.ncli.process_msg(pkt)

        if ctx.ncli.has_new_messages():
            msgs: dict[int, list[str]] = ctx.ncli.get_new_messages()
            for t, txts in msgs.items():
                for txt in txts:
                    ctx.inbox.put(("msg", (t, txt, int(time.time()), False)))

        if ctx.ncli.has_new_peers():
            peers: list[int] = ctx.ncli.get_new_peers()
            for p in peers:
                ctx.inbox.put(("peer", p))

        while not ctx.outbox.empty():
            print("[main] got new msg from GUI")
            tkn, msg = ctx.outbox.get_nowait()
            ctx.ncli.message(tkn, msg)

    ctx.ncli.stop()


def main(ip: str, port: int, database: str):
    chat_db = chd.ChatDatabase(database)
    chat_db.clear(True, True)

    app = cli.GUIClient(chat_db)
    ncli = client.DecClient(address.NetAddress(ip, port))

    ctx = NetContext(
        gui=app,
        inbox=app.inbox,
        outbox=app.outbox,
        is_running=app.running,
        ncli=ncli,
    )

    nthr = threading.Thread(target=netthread, args=(ctx,))
    nthr.start()

    app.build()
    app.import_from_db()

    app.run()

    ncli.stop()
    nthr.join()


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

    args = parser.parse_args()

    os.makedirs(args.database, exist_ok=True)
    main(args.ip, args.port, args.database)
