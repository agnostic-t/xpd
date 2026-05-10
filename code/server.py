import argparse

from crypto.api import ClientStorage
from net import address, server


def main(ip: str, port: int):
    storage = ClientStorage(key_dir="./runtime/keys/server", password="1234")
    serv = server.DecServer(address.NetAddress(ip, port), storage.ltk)
    serv.start()
    try:
        serv.loop()
    except KeyboardInterrupt:
        print("[serv] interrupted, exiting")

    serv.end()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Server program for decmsg")
    parser.add_argument("-i", "--ip", help="IP address to bind/connect", required=True)
    parser.add_argument(
        "-p", "--port", type=int, help="PORT to bind/connect", required=True
    )

    args = parser.parse_args()
    main(args.ip, args.port)
