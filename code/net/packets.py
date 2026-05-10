import base64
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519


class Packet:
    def __init__(
        self,
        from_token: int,
        to_token: int,
        text: str,
        metadata: str,
        signature: str | None = None,
    ):
        self.from_token = from_token
        self.to_token = to_token
        self.text = text
        self.metadata = metadata
        self.signature = signature

    def _get_signable_payload(self) -> bytes:
        data = {
            "from_token": self.from_token,
            "to_token": self.to_token,
            "text": self.text,
            "metadata": self.metadata,
        }

        return json.dumps(data, sort_keys=True).encode("utf-8")

    def sign(self, private_key: ed25519.Ed25519PrivateKey):
        payload = self._get_signable_payload()

        sig_bytes = private_key.sign(payload)

        self.signature = base64.b64encode(sig_bytes).decode("utf-8")

    def verify(self, pubkey_b64: str) -> bool:
        if not self.signature:
            return False

        try:
            padded_pub = pubkey_b64 + "=" * (-len(pubkey_b64) % 4)
            pub_bytes = base64.urlsafe_b64decode(padded_pub)

            sig_bytes = base64.b64decode(self.signature)

            public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)

            payload = self._get_signable_payload()

            public_key.verify(sig_bytes, payload)
            return True

        except (InvalidSignature, ValueError, TypeError):
            return False

    @staticmethod
    def deserial(data: dict) -> "Packet":
        return Packet(
            from_token=data["from_token"],
            to_token=data["to_token"],
            text=data["text"],
            metadata=data["metadata"],
            signature=data.get("signature"),
        )

    def serial(self) -> dict:
        return {
            "from_token": self.from_token,
            "to_token": self.to_token,
            "text": self.text,
            "metadata": self.metadata,
            "signature": self.signature,
        }
