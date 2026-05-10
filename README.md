# Simple Messenger

- Decentralized, but not P2P
- Has AES encryption
- ED25519 for client authorization
- X25519 for ephemeral keys
- Has Perferct Forward Secrecy
- Uses TCP as transport

## Installation and Usage

```sh
pip install -r ./requirements
cd code
python ./main -i SERVER_IP -p SERVER_PORT # For GUI client
python ./server -i BIND_IP -p BIND_PORT # For server
```

You can also run a distributor and install client via `curl`

```sh
cd code
python ./distributor.py

# Installation

```