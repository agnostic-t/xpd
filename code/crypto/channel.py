import base64
import secrets
from typing import Optional, Union

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from crypto.ed25519 import Ed25519Auth
from crypto.x25519 import CryptoError, SessionKeys, X25519Exchange


class SecureChannel:
    """
    Authenticated Key Exchange: X25519 + Ed25519 + AES-256-GCM

    Flow:
    Initiator: initiate_handshake() → send to peer
    Responder: accept_handshake(init_msg) → send response back
    Initiator: finalize_handshake(resp_msg) → channel ready
    """

    def __init__(
        self,
        identity: Ed25519Auth,
        known_peer_id: Optional[bytes] = None,
    ):
        self._identity = identity
        self._known_peer_id = known_peer_id
        self._x25519 = X25519Exchange()
        self._aesgcm: Optional[AESGCM] = None
        self._session_keys: Optional[SessionKeys] = None
        self._our_ephemeral: Optional[bytes] = None
        self._nonce_counter = 0

    # ================= INITIATOR SIDE =================

    def initiate_handshake(self) -> dict:
        """Step 1: Generate ephemeral keys, prepare first message."""
        self._our_ephemeral = self._x25519.generate_ephemeral_keys()
        return {
            "ephemeral_x25519": base64.b64encode(self._our_ephemeral).decode(),
            "identity_ed25519": base64.b64encode(
                self._identity.public_key_raw
            ).decode(),
        }

    def finalize_handshake(self, resp_msg: dict) -> bool:
        """Step 3: Verify responder's signature, complete channel setup."""
        peer_eph = base64.b64decode(resp_msg["ephemeral_x25519"])
        peer_id = base64.b64decode(resp_msg["identity_ed25519"])
        sig = base64.b64decode(resp_msg["signature"])

        self._check_peer_identity(peer_id)

        # Deterministic key derivation (same inputs → same AES key on both sides)
        result = self._x25519.complete_exchange(
            peer_eph, salt=self._our_ephemeral + peer_eph
        )
        self._aesgcm = AESGCM(result.session_keys.encryption_key)
        self._session_keys = result.session_keys

        # Verify signature: responder signed (their_eph || our_eph)
        if not self._identity.verify_exchange(
            signer_pub=peer_id,
            our_ephemeral=peer_eph,  # from responder's perspective: "our"
            peer_ephemeral=self._our_ephemeral,  # "peer" = us
            signature=sig,
        ):
            raise CryptoError("Responder signature verification failed")

        self._nonce_counter = 0
        return True

    # ================= RESPONDER SIDE =================

    def accept_handshake(self, init_msg: dict) -> dict:
        """Step 2: Process initiator message, compute shared secret, sign & respond."""
        peer_eph = base64.b64decode(init_msg["ephemeral_x25519"])
        peer_id = base64.b64decode(init_msg["identity_ed25519"])

        self._check_peer_identity(peer_id)

        self._our_ephemeral = self._x25519.generate_ephemeral_keys()

        # Derive keys (same salt as initiator will use)
        result = self._x25519.complete_exchange(
            peer_eph, salt=self._our_ephemeral + peer_eph
        )
        self._aesgcm = AESGCM(result.session_keys.encryption_key)
        self._session_keys = result.session_keys

        # Sign transcript: context + our_eph + peer_eph
        sig = self._identity.sign_exchange(self._our_ephemeral, peer_eph)
        self._nonce_counter = 0

        return {
            "ephemeral_x25519": base64.b64encode(self._our_ephemeral).decode(),
            "identity_ed25519": base64.b64encode(
                self._identity.public_key_raw
            ).decode(),
            "signature": base64.b64encode(sig).decode(),
        }

    # ================= SHARED LOGIC =================

    def _check_peer_identity(self, received_id: bytes) -> None:
        if self._known_peer_id and received_id != self._known_peer_id:
            raise CryptoError(
                f"Peer identity mismatch. Expected: {self._known_peer_id.hex()[:16]}..., "
                f"Got: {received_id.hex()[:16]}..."
            )

    def encrypt(
        self, plaintext: Union[str, bytes], aad: Optional[bytes] = None
    ) -> dict:
        if self._aesgcm is None:
            raise CryptoError("Handshake not completed")
        if isinstance(plaintext, str):
            plaintext = plaintext.encode("utf-8")

        nonce = self._session_keys.derive_nonce(self._nonce_counter)
        self._nonce_counter += 1

        ct_with_tag = self._aesgcm.encrypt(nonce, plaintext, aad)
        ct, tag = ct_with_tag[:-16], ct_with_tag[-16:]

        return {
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ct).decode(),
            "tag": base64.b64encode(tag).decode(),
        }

    def decrypt(
        self,
        nonce_b64: str,
        ciphertext_b64: str,
        tag_b64: str,
        aad: Optional[bytes] = None,
    ) -> str:
        if self._aesgcm is None:
            raise CryptoError("Handshake not completed")

        nonce = base64.b64decode(nonce_b64)
        ct = base64.b64decode(ciphertext_b64)
        tag = base64.b64decode(tag_b64)

        try:
            return self._aesgcm.decrypt(nonce, ct + tag, aad).decode("utf-8")
        except InvalidTag:
            raise CryptoError("Authentication failed: invalid tag or corrupted data")
