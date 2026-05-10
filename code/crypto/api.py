import base64
import json
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.asymmetric import ed25519

from crypto.channel import SecureChannel
from crypto.ed25519 import Ed25519Auth
from crypto.lterm import LongTermKey


class ClientStorage:
    def __init__(self, password: str, key_dir: str) -> None:
        self.password = password
        self.key_dir_p: Path = Path(key_dir)
        self.key_path: Path = self.key_dir_p / "identity.key"

        self.ltk: LongTermKey
        if self.key_path.exists():
            self.ltk = LongTermKey.load_from_file(self.key_path, password)
        else:
            self.key_dir_p.mkdir(parents=True, exist_ok=True)

            self.ltk = LongTermKey.generate()
            self.ltk.save_to_file(self.key_path, password=password)

            (self.key_dir_p / "identity.pub").write_bytes(self.ltk.export_public_pem())

            config = {
                "fingerprint": self.ltk.fingerprint,
                "public_b64": self.ltk.public_b64,
            }

            (self.key_dir_p / "config.json").write_text(
                json.dumps(config, indent=2), encoding="utf-8"
            )

    def gen_ed25519_auth(self) -> Ed25519Auth:
        raw_private = self.ltk.export_private_raw()
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(raw_private)
        return Ed25519Auth(private_key)

    def gen_uid(self) -> int:
        return int.from_bytes(sha256(self.ltk.export_private_raw()).digest()[:7])

    def get_pubkey(self) -> str:
        return self.ltk.export_public_base64()


class _HandshakeState(Enum):
    NOT_HANDSHAKED = 0
    IN_PROCESS = 1
    DONE = 2
    FAILED = 3


class ClientHandshake:
    def __init__(self, storage: ClientStorage, schan: SecureChannel) -> None:
        self.storage = storage
        self.schan = schan
        self.state: _HandshakeState = _HandshakeState.NOT_HANDSHAKED

    def giveaway(self) -> dict:
        self.state = _HandshakeState.IN_PROCESS
        return self.schan.initiate_handshake()

    def handle_incoming(self, data: dict) -> dict:
        return self.schan.accept_handshake(data)

    def finalize(self, data: dict) -> bool:
        b = self.schan.finalize_handshake(data)

        if not b:
            self.state = _HandshakeState.FAILED
        else:
            self.state = _HandshakeState.DONE

        return b

    def check(self) -> bool:
        return self.state == _HandshakeState.DONE


class EncryptedChannel:
    def __init__(
        self, storage: ClientStorage, known_peer_id: Optional[bytes] = None
    ) -> None:
        self.storage = storage
        self.channel = SecureChannel(self.storage.gen_ed25519_auth(), known_peer_id)

        self.handshake = ClientHandshake(self.storage, self.channel)

    def get_pubkey(self) -> str:
        return self.storage.ltk.export_public_base64()

    def get_known_id_from_pubkey(self, pubkey: str) -> bytes:
        return LongTermKey.from_base64(pubkey, False).export_public_raw()

    def hsh_start(self) -> dict:
        return self.handshake.giveaway()

    def hsh_accept(self, data: dict) -> dict:
        return self.handshake.handle_incoming(data)

    def hsh_finalize(self, data: dict) -> bool:
        return self.handshake.finalize(data)

    # encrypting/decrypting
    def encrypt(self, data: str) -> str:
        enc_dict = self.channel.encrypt(data)
        json_bytes = json.dumps(enc_dict).encode("utf-8")
        return base64.b64encode(json_bytes).decode("utf-8")

    def decrypt(self, data: str) -> str:
        json_bytes = base64.b64decode(data)
        enc_dict = json.loads(json_bytes.decode("utf-8"))

        return self.channel.decrypt(
            nonce_b64=enc_dict["nonce"],
            ciphertext_b64=enc_dict["ciphertext"],
            tag_b64=enc_dict["tag"],
        )
