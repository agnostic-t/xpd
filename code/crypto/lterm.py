"""
Long-term key management for Ed25519 identity keys.

Features:
- Generate/save/load Ed25519 keypairs
- Export/import in multiple formats (raw, PEM, base64)
- Optional encryption of private keys with password
- Fingerprint calculation for key verification
- Secure file permissions handling (Unix)
"""

import base64
import os
from pathlib import Path
from typing import Optional, Union

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


class KeyManagementError(Exception):
    pass


class LongTermKey:
    """
    Ed25519 long-term identity keypair.

    Usage:
    - Server: generate once, store securely, distribute public key
    - Client: generate once, store securely, register public key with server
    """

    KEY_SIZE = 32  # Ed25519 keys are always 32 bytes
    FINGERPRINT_HASH = "SHA256"

    def __init__(self, private_key: Optional[ed25519.Ed25519PrivateKey] = None):
        self._private = private_key
        self._public = private_key.public_key() if private_key else None

    @classmethod
    def generate(cls) -> "LongTermKey":
        """Generate a new Ed25519 keypair."""
        private = ed25519.Ed25519PrivateKey.generate()
        return cls(private)

    # ========== Export formats ==========

    def export_private_raw(self) -> bytes:
        """Export private key as 32 raw bytes (NOT encrypted)."""
        if self._private is None:
            raise KeyManagementError("No private key to export")
        return self._private.private_bytes_raw()

    def export_public_raw(self) -> bytes:
        """Export public key as 32 raw bytes."""
        if self._public is None:
            raise KeyManagementError("No public key")
        return self._public.public_bytes_raw()

    def export_private_hazmat(self) -> ed25519.Ed25519PrivateKey:
        return ed25519.Ed25519PrivateKey.from_private_bytes(self.export_private_raw())

    def export_private_pem(self, password: Optional[str] = None) -> bytes:
        """
        Export private key in PEM format.

        Args:
            password: If provided, encrypt with PBKDF2+AES-256-GCM
        """
        if self._private is None:
            raise KeyManagementError("No private key to export")

        if password:
            # Encrypt with PKCS8 + PBKDF2
            return self._private.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.BestAvailableEncryption(
                    password.encode()
                ),
            )
        else:
            return self._private.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )

    def export_public_pem(self) -> bytes:
        """Export public key in PEM format."""
        if self._public is None:
            raise KeyManagementError("No public key")
        return self._public.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def export_public_base64(self) -> str:
        """Export public key as URL-safe base64 (for configs/URLs)."""
        return base64.urlsafe_b64encode(self.export_public_raw()).decode().rstrip("=")

    def export_fingerprint(self, algorithm: str = "SHA256") -> str:
        """
        Calculate key fingerprint for verification.
        Format: "ED25519:AA:BB:CC:..." (like SSH).
        """
        pub_raw = self.export_public_raw()
        if algorithm == "SHA256":
            digest = hashes.Hash(hashes.SHA256())
            digest.update(pub_raw)
            hash_bytes = digest.finalize()
            # First 16 bytes, colon-separated hex
            return "ED25519:" + ":".join(f"{b:02X}" for b in hash_bytes[:16])
        else:
            raise KeyManagementError(f"Unsupported fingerprint algorithm: {algorithm}")

    # ========== Import formats ==========

    @classmethod
    def from_private_raw(cls, raw_bytes: bytes) -> "LongTermKey":
        """Import private key from 32 raw bytes."""
        if len(raw_bytes) != cls.KEY_SIZE:
            raise KeyManagementError(f"Private key must be {cls.KEY_SIZE} bytes")
        private = ed25519.Ed25519PrivateKey.from_private_bytes(raw_bytes)
        return cls(private)

    @classmethod
    def from_public_raw(cls, raw_bytes: bytes) -> "LongTermKey":
        """Import public key only (for verification, no signing)."""
        if len(raw_bytes) != cls.KEY_SIZE:
            raise KeyManagementError(f"Public key must be {cls.KEY_SIZE} bytes")
        instance = cls.__new__(cls)
        instance._private = None
        instance._public = ed25519.Ed25519PublicKey.from_public_bytes(raw_bytes)
        return instance

    @classmethod
    def from_pem(
        cls,
        pem_data: bytes,
        password: Optional[str] = None,
    ) -> "LongTermKey":
        """
        Import key from PEM format.

        Args:
            pem_ PEM-encoded key (private or public)
            password: If private key is encrypted
        """
        # Try private key first
        try:
            private = serialization.load_pem_private_key(
                pem_data,
                password=password.encode() if password else None,
            )
            if not isinstance(private, ed25519.Ed25519PrivateKey):
                raise KeyManagementError("Not an Ed25519 private key")
            return cls(private)
        except (ValueError, TypeError, UnsupportedAlgorithm):
            pass

        # Try public key
        try:
            public = serialization.load_pem_public_key(pem_data)
            if not isinstance(public, ed25519.Ed25519PublicKey):
                raise KeyManagementError("Not an Ed25519 public key")
            instance = cls.__new__(cls)
            instance._private = None
            instance._public = public
            return instance
        except Exception as e:
            raise KeyManagementError(f"Failed to parse PEM: {e}")

    @classmethod
    def from_base64(cls, b64_key: str, is_private: bool) -> "LongTermKey":
        """Import key from base64-encoded raw bytes."""
        # Add padding if needed
        padded = b64_key + "=" * (-len(b64_key) % 4)
        raw = base64.urlsafe_b64decode(padded)

        if is_private:
            return cls.from_private_raw(raw)
        else:
            return cls.from_public_raw(raw)

    # ========== File I/O with security ==========

    def save_to_file(
        self,
        path: Union[str, Path],
        password: Optional[str] = None,
        mode: int = 0o600,
    ) -> None:
        """
        Save private key to file securely.

        Args:
            path: File path to save
            password: Encrypt key with this password
            mode: File permissions (default: owner read/write only)
        """
        path_obj = Path(path)

        # Ensure parent directory exists and is secure
        path_obj.parent.mkdir(parents=True, exist_ok=True)

        # Export and write
        pem_data = self.export_private_pem(password)

        # Write with secure permissions
        fd = os.open(str(path_obj), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        try:
            os.write(fd, pem_data)
        finally:
            os.close(fd)

        # Double-check permissions (in case umask interfered)
        os.chmod(str(path_obj), mode)

    @classmethod
    def load_from_file(
        cls,
        path: Union[str, Path],
        password: Optional[str] = None,
    ) -> "LongTermKey":
        """Load private key from file."""
        path_obj = Path(path)
        if not path_obj.is_file():
            raise KeyManagementError(f"Key file not found: {path}")

        # Check permissions (warn if too open)
        stat = path_obj.stat()
        if stat.st_mode & 0o077:  # Any permissions for group/other
            import warnings

            warnings.warn(
                f"Key file {path} has insecure permissions: {oct(stat.st_mode)}. "
                "Consider: chmod 600",
                UserWarning,
            )

        pem_data = path_obj.read_bytes()
        return cls.from_pem(pem_data, password)

    # ========== Properties ==========

    @property
    def has_private(self) -> bool:
        return self._private is not None

    @property
    def fingerprint(self) -> str:
        return self.export_fingerprint()

    @property
    def public_b64(self) -> str:
        return self.export_public_base64()
