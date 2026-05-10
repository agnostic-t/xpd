"""
Modern key exchange module using X25519 + HKDF + AES-GCM.

Features:
- Ephemeral X25519 keys for Perfect Forward Secrecy
- HKDF-SHA256 for key derivation
- Optional Ed25519 signatures for authentication
- AES-256-GCM for authenticated encryption
- Clean API for client/server roles
"""

import base64
import hmac
import os
import secrets
from dataclasses import dataclass, field
from typing import Optional, Tuple, Union

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class CryptoError(Exception):
    pass


@dataclass
class SessionKeys:
    """Derived keys for a secure session."""

    encryption_key: bytes  # 32 bytes for AES-256
    mac_key: bytes  # 32 bytes for HMAC (optional, for extra integrity)
    nonce_base: bytes  # 12 bytes base for nonce construction

    def derive_nonce(self, counter: int) -> bytes:
        """Generate unique nonce from base + counter (big-endian)."""
        if counter < 0 or counter > 0xFFFFFFFF:
            raise CryptoError("Nonce counter out of range")
        return self.nonce_base + counter.to_bytes(4, "big")


@dataclass
class KeyExchangeResult:
    """Result of successful key exchange."""

    session_keys: SessionKeys
    peer_public_key: bytes  # For logging/verification
    our_ephemeral_public: bytes
    salt: bytes  # For reproducibility/debugging (not secret)


class X25519Exchange:
    """
    Ephemeral X25519 key exchange with HKDF derivation.

    Usage pattern:
    1. Each side creates instance, generates ephemeral keys
    2. Exchange public keys over network
    3. Call complete_exchange() with peer's public key
    4. Use derived SessionKeys for AES-GCM encryption
    """

    KEY_SIZE = 32  # X25519 keys are always 32 bytes
    SHARED_SECRET_SIZE = 32
    DERIVED_KEY_SIZE = 32  # For AES-256

    def __init__(self, info: bytes = b"x25519-aes-gcm-v1"):
        self._private: Optional[x25519.X25519PrivateKey] = None
        self._public: Optional[bytes] = None
        self._info = info
        self._completed = False

    def generate_ephemeral_keys(self) -> bytes:
        """Generate new ephemeral keypair, return public key (32 bytes, raw)."""
        self._private = x25519.X25519PrivateKey.generate()
        public = self._private.public_key()
        self._public = public.public_bytes_raw()
        self._completed = False
        return self._public

    def complete_exchange(
        self,
        peer_public_raw: bytes,
        salt: Optional[bytes] = None,
        peer_context: Optional[bytes] = None,
    ) -> KeyExchangeResult:
        """
        Complete key exchange after receiving peer's public key.

        Args:
            peer_public_raw: 32-byte raw public key from peer
            salt: Optional salt for HKDF (use random for each session)
            peer_context: Optional context string for key separation

        Returns:
            KeyExchangeResult with derived session keys
        """
        if self._private is None or self._public is None:
            raise CryptoError("Call generate_ephemeral_keys() first")
        if len(peer_public_raw) != self.KEY_SIZE:
            raise CryptoError(f"Peer public key must be {self.KEY_SIZE} bytes")
        if self._completed:
            raise CryptoError("Exchange already completed")

        # Load peer's public key
        peer_public = x25519.X25519PublicKey.from_public_bytes(peer_public_raw)

        # Compute shared secret (32 bytes)
        shared = self._private.exchange(peer_public)

        # Optional: add context to info for domain separation
        info = self._info
        if peer_context:
            info = info + b":" + peer_context

        # Derive session keys via HKDF
        if salt is None:
            salt = secrets.token_bytes(16)

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=self.DERIVED_KEY_SIZE * 2 + 12,  # enc_key + mac_key + nonce_base
            salt=salt,
            info=info,
        )
        derived = hkdf.derive(shared)

        enc_key = derived[:32]
        mac_key = derived[32:64]
        nonce_base = derived[64:]

        self._completed = True

        return KeyExchangeResult(
            session_keys=SessionKeys(
                encryption_key=enc_key,
                mac_key=mac_key,
                nonce_base=nonce_base,
            ),
            peer_public_key=peer_public_raw,
            our_ephemeral_public=self._public,
            salt=salt,
        )

    def get_public_key(self) -> Optional[bytes]:
        """Return our ephemeral public key (raw bytes) or None."""
        return self._public
