"""
RSA cryptographic module using the cryptography library.

Fixed version with modern API, secure defaults, and explicit error handling.
"""

import base64
import json
from pathlib import Path
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class RSACryptoError(Exception):
    pass


class RSACrypto:
    _OAEP_OVERHEAD: dict[int, int] = {2048: 66, 3072: 66, 4096: 66}

    def __init__(self, key_size: int = 2048) -> None:
        if key_size not in (2048, 3072, 4096):
            raise ValueError(
                f"Unsupported key size: {key_size}. Use 2048, 3072 or 4096."
            )
        self._key_size: int = key_size
        self._private_key: Optional[rsa.RSAPrivateKey] = None
        self._public_key: Optional[rsa.RSAPublicKey] = None

    def gen_keys(self, save_path: Optional[str] = None) -> dict[str, str]:
        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self._key_size,
        )
        self._public_key = self._private_key.public_key()

        private_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        keys = {
            "private_key": base64.b64encode(private_pem).decode("utf-8"),
            "public_key": base64.b64encode(public_pem).decode("utf-8"),
            "key_size": self._key_size,
        }

        if save_path is not None:
            self.save_keys(save_path, keys)
        return keys

    def save_keys(self, path: str, keys: dict[str, str]) -> None:
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        path_obj.write_text(
            json.dumps(keys, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def load_keys(self, path: str) -> dict[str, str]:
        path_obj = Path(path)
        if not path_obj.is_file():
            raise RSACryptoError(f"Keys file not found: {path}")

        try:
            keys = json.loads(path_obj.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise RSACryptoError(f"Invalid JSON in keys file: {e}")

        required = {"private_key", "public_key"}
        if not required.issubset(keys.keys()):
            raise RSACryptoError(f"Missing required fields: {required - keys.keys()}")

        self.load_keys_in_memory(keys)
        return keys

    def load_keys_in_memory(self, keys: dict[str, str]) -> None:
        if "private_key" not in keys or "public_key" not in keys:
            raise RSACryptoError(
                "Keys dict must contain 'private_key' and 'public_key'"
            )

        try:
            private_pem = base64.b64decode(keys["private_key"])
            self._private_key = serialization.load_pem_private_key(
                private_pem, password=None
            )

            self._public_key = self._private_key.public_key()
        except (ValueError, TypeError, serialization.UnsupportedAlgorithm) as e:
            raise RSACryptoError(f"Failed to load keys: {e}")

    def get_max_len(self) -> int:
        return self._key_size // 8 - self._OAEP_OVERHEAD[self._key_size]

    def encrypt(self, plaintext: str) -> str:
        if self._public_key is None:
            raise RSACryptoError(
                "Public key not loaded. Call gen_keys() or load_keys() first."
            )

        plaintext_bytes = plaintext.encode("utf-8")
        max_len = (self._key_size // 8) - self._OAEP_OVERHEAD[self._key_size]
        if len(plaintext_bytes) > max_len:
            raise RSACryptoError(
                f"Plaintext too long for RSA-OAEP. Max {max_len} bytes for {self._key_size}-bit key."
            )

        encrypted = self._public_key.encrypt(
            plaintext_bytes,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return base64.b64encode(encrypted).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        if self._private_key is None:
            raise RSACryptoError(
                "Private key not loaded. Call gen_keys() or load_keys() first."
            )

        try:
            encrypted = base64.b64decode(ciphertext)
            decrypted = self._private_key.decrypt(
                encrypted,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
            return decrypted.decode("utf-8")
        except ValueError as e:
            raise RSACryptoError(
                f"Decryption failed (wrong key or corrupted data): {e}"
            )

    def sign(self, plaintext: str) -> str:
        """Sign plaintext using PSS-SHA256 (recommended over PKCS1v15)."""
        if self._private_key is None:
            raise RSACryptoError("Private key not loaded.")

        signature = self._private_key.sign(
            plaintext.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def verify(self, plaintext: str, signature: str) -> bool:
        """Verify signature. Returns True if valid, False otherwise."""
        if self._public_key is None:
            raise RSACryptoError("Public key not loaded.")

        try:
            sig_bytes = base64.b64decode(signature)
            self._public_key.verify(
                sig_bytes,
                plaintext.encode("utf-8"),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            return True
        except InvalidSignature:
            return False
        except Exception as e:
            raise RSACryptoError(f"Signature verification error: {e}")
