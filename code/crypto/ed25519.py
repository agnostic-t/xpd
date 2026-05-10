import base64
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from crypto.x25519 import CryptoError


class Ed25519Auth:
    """
    Long-term Ed25519 keys for signing key exchanges.

    Use this to authenticate that a key exchange came from
    a known peer, preventing MITM on the ephemeral exchange.
    """

    def __init__(self, private_key: Optional[ed25519.Ed25519PrivateKey] = None):
        self._private = private_key or ed25519.Ed25519PrivateKey.generate()
        self._public = self._private.public_key()

    @property
    def public_key_raw(self) -> bytes:
        return self._public.public_bytes_raw()

    def sign_exchange(self, our_eph: bytes, peer_eph: bytes) -> bytes:
        """Sign the handshake transcript. Order: our_eph || peer_eph"""
        transcript = b"ake-v1:x25519-ed25519" + our_eph + peer_eph
        return self._private.sign(transcript)

    def verify_exchange(
        self, signer_pub: bytes, our_eph: bytes, peer_eph: bytes, signature: bytes
    ) -> bool:
        """Verify signature against explicit signer public key."""
        transcript = b"ake-v1:x25519-ed25519" + our_eph + peer_eph
        try:
            pub_key = ed25519.Ed25519PublicKey.from_public_bytes(signer_pub)
            pub_key.verify(signature, transcript)
            return True
        except InvalidSignature:
            return False

    def export_public(self) -> str:
        """Export public key as base64 for distribution."""
        return base64.b64encode(self.public_key_raw).decode("utf-8")

    @classmethod
    def import_public(cls, b64_key: str) -> "Ed25519Auth":
        """Import peer's public key for verification."""
        raw = base64.b64decode(b64_key)
        if len(raw) != 32:
            raise CryptoError("Ed25519 public key must be 32 bytes")
        instance = cls.__new__(cls)
        instance._private = None  # type: ignore
        instance._public = ed25519.Ed25519PublicKey.from_public_bytes(raw)
        return instance
