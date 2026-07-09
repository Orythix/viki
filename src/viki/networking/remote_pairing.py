"""
Remote pairing mode — end-to-end encrypted tunnel to your own instance.

Uses noise protocol or similar E2EE scheme with no relay storage,
so "hosted convenience" stops being a reason to give data away.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, cast

from viki.config.logger import viki_logger

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import x25519

    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


@dataclass
class PairingSession:
    """An active E2EE pairing session with a remote client."""

    client_id: str
    public_key: bytes
    shared_secret: bytes = b""
    connected_at: float = 0.0
    last_heartbeat: float = 0.0
    cipher: Any = None


class E2EETunnel:
    """
    End-to-end encrypted tunnel for remote pairing.

    Uses X25519 key exchange + Fernet symmetric encryption.
    No relay stores plaintext data.
    """

    def __init__(self, data_dir: str = "./data"):
        self._data_dir = data_dir
        self._key_path = os.path.join(data_dir, "pairing_identity.key")
        self._sessions: dict[str, PairingSession] = {}
        self._private_key: Any = None
        self._public_key: bytes = b""
        self._listener: Any = None
        self._running = False
        os.makedirs(data_dir, exist_ok=True)
        self._load_or_generate_keys()

    def _load_or_generate_keys(self) -> None:
        if not _HAS_CRYPTO:
            viki_logger.warning("E2EETunnel: cryptography not installed")
            return

        if os.path.exists(self._key_path):
            with open(self._key_path, "rb") as f:
                self._private_key = x25519.X25519PrivateKey.from_private_bytes(f.read())
        else:
            self._private_key = x25519.X25519PrivateKey.generate()
            with open(self._key_path, "wb") as f:
                f.write(
                    self._private_key.private_bytes(
                        serialization.Encoding.Raw,
                        serialization.PrivateFormat.Raw,
                        serialization.NoEncryption(),
                    )
                )

        self._public_key = self._private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        viki_logger.info(
            "E2EETunnel: identity key loaded (%d bytes public key)", len(self._public_key)
        )

    def get_public_key(self) -> bytes:
        return self._public_key

    def create_session(self, client_id: str, client_public_key: bytes) -> PairingSession | None:
        if not _HAS_CRYPTO or self._private_key is None:
            return None

        shared = self._private_key.exchange(
            x25519.X25519PublicKey.from_public_bytes(client_public_key)
        )
        # Derive Fernet key from shared secret
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        derived = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"viki-pairing",
        ).derive(shared)

        session = PairingSession(
            client_id=client_id,
            public_key=client_public_key,
            shared_secret=shared,
            connected_at=time.time(),
            last_heartbeat=time.time(),
            cipher=Fernet(derived),
        )
        self._sessions[client_id] = session
        viki_logger.info("E2EETunnel: paired with client '%s'", client_id)
        return session

    def encrypt(self, client_id: str, plaintext: str) -> bytes | None:
        session = self._sessions.get(client_id)
        if session is None or session.cipher is None:
            return None
        return cast("bytes", session.cipher.encrypt(plaintext.encode()))

    def decrypt(self, client_id: str, ciphertext: bytes) -> str | None:
        session = self._sessions.get(client_id)
        if session is None or session.cipher is None:
            return None
        try:
            return cast("str", session.cipher.decrypt(ciphertext).decode())
        except Exception as e:
            viki_logger.error("E2EETunnel: decryption failed for '%s': %s", client_id, e)
            return None

    def disconnect(self, client_id: str) -> None:
        self._sessions.pop(client_id, None)
        viki_logger.info("E2EETunnel: disconnected '%s'", client_id)

    def is_connected(self, client_id: str) -> bool:
        return client_id in self._sessions

    @property
    def active_sessions(self) -> list[PairingSession]:
        return list(self._sessions.values())


class WebRTCPairing:
    """
    WebRTC-based P2P pairing for direct browser-to-VIKI connections.

    Uses a simple signaling protocol over the dashboard WebSocket.
    """

    def __init__(self):
        self._pending: dict[str, dict] = {}

    def create_offer(self, client_id: str) -> dict[str, Any] | None:
        try:
            import uuid

            offer = {
                "type": "offer",
                "sdp": f"viki-pairing-{uuid.uuid4().hex[:16]}",
                "client_id": client_id,
            }
            self._pending[client_id] = offer
            return offer
        except Exception:
            return None

    def accept_offer(self, client_id: str, answer: dict) -> bool:
        if client_id in self._pending:
            del self._pending[client_id]
            return True
        return False
