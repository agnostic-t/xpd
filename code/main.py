import argparse
import random

from net import address, client, server


def server_main():
    serv = server.DecServer(address.NetAddress("127.0.0.1", 9000))
    serv.start()
    serv.loop()
    serv.end()


def client_main():
    cli = client.DecClient(address.NetAddress("127.0.0.1", 9000))
    cli.connect()

    token = random.randint(0, 1000)

    cli.register(token)
    clients = cli.discovery()
    for peer in clients:
        cli.message(peer, f"Hello from cli {token}")

    cli.wait_messages(-1)
    while cli.has_messages():
        msg = cli.get_message()
        print(f"got message from {msg.from_cli}: {msg.text}")

    cli.stop()


def main(type: str):
    if type == "server":
        server_main()

    if type == "client":
        client_main()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--type", help="Type of program, server or client")

    args = parser.parse_args()
    main(args.type)
