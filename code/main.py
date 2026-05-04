import argparse
import random
import time
from operator import add

from net import address, client, server


def server_main(ip: str, port: int):
    serv = server.DecServer(address.NetAddress(ip, port))
    serv.start()
    try:
        serv.loop()
    except KeyboardInterrupt:
        print("[serv] interrupted, exiting")

    serv.end()


def client_main(ip: str, port: int):
    cli = client.DecClient(address.NetAddress(ip, port))
    try:
        cli.connect()
        print(f"[client] connected to {str(cli.addr)}")
    except Exception as ex:
        print(f"[client] failed to connect: {ex}")
        return

    token = random.randint(0, 100000000000)
    print(f"[client] self token: {token}")

    cli.register(token)

    i = 0
    suggested = False
    while cli.can_run():
        if cli.state == client.ClientStates.REGISTERED and not suggested:
            cli.suggest(address.NetAddress(ip, 9001 if port == 9000 else 9000))
            suggested = True

        if time.time() >= cli.next_discovery_time:
            cli.discovery()

        if time.time() >= cli.next_fetch_time:
            cli.fetch_msgs()

        try:
            msg = cli.wait_message(1)  # 1 second
            if not msg:
                continue
        except KeyboardInterrupt:
            print("[client] interrupted, exiting...")
            break

        cli.process_msg(msg)

        if len(cli.known_peers) > 0:
            peer = random.choice(cli.known_peers)
            cli.message(peer, f"Hello from {cli.token} ({i})")
            i += 1

    cli.stop()


def main(type: str, ip: str, port: int):
    if type == "server":
        server_main(ip, port)

    if type == "client":
        client_main(ip, port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-t", "--type", help="Type of program, server or client", required=True
    )
    parser.add_argument("-i", "--ip", help="IP address to bind/connect", required=True)
    parser.add_argument(
        "-p", "--port", type=int, help="PORT to bind/connect", required=True
    )

    args = parser.parse_args()
    main(args.type, args.ip, args.port)
