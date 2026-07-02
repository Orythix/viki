"""Encrypted credential store for API keys and secrets.

Uses a key derived from the machine's hardware ID + a salt file,
so credentials are tied to a specific machine and cannot be read
if the data directory is copied elsewhere.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from pathlib import Path

from viki.config.logger import viki_logger

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


_SALT_FILE = ".cred_salt"
_STORE_FILE = "credentials.enc"
_KEY_LENGTH = 32
_ITERATIONS = 600_000


def _get_machine_id() -> str:
    """Derive a machine-specific identifier for key generation."""
    candidates = []
    if sys.platform == "win32":
        try:
            import subprocess

            result = subprocess.run(
                ["wmic", "csproduct", "get", "uuid"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line and line != "UUID":
                    candidates.append(line)
        except Exception:
            pass
    elif sys.platform == "linux":
        for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                candidates.append(Path(path).read_text().strip())
            except OSError:
                pass
    elif sys.platform == "darwin":
        try:
            import subprocess

            result = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                if "IOPlatformUUID" in line:
                    candidates.append(line.split('"')[-2])
        except Exception:
            pass

    # Fallback: hostname + user home
    candidates.append(
        os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", "unknown")
    )
    candidates.append(os.path.expanduser("~"))

    return hashlib.sha256("|".join(candidates).encode()).hexdigest()


def _get_or_create_salt(data_dir: str) -> bytes:
    salt_path = os.path.join(data_dir, _SALT_FILE)
    if os.path.exists(salt_path):
        with open(salt_path, "rb") as f:
            return f.read()
    salt = os.urandom(16)
    os.makedirs(data_dir, exist_ok=True)
    with open(salt_path, "wb") as f:
        f.write(salt)
    return salt


def _derive_key(machine_id: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_LENGTH,
        salt=salt,
        iterations=_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(machine_id.encode()))


class CredentialManager:
    """Encrypted credential store tied to the current machine."""

    def __init__(self, data_dir: str | None = None):
        if not HAS_CRYPTO:
            viki_logger.warning(
                "cryptography not installed — CredentialManager disabled. "
                "Install with: pip install cryptography"
            )
            self._enabled = False
            self._store: dict[str, str] = {}
            self._path: str | None = None
            return

        self._enabled = True
        self._data_dir = data_dir or os.environ.get(
            "VIKI_DATA_DIR",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
        )
        os.makedirs(self._data_dir, exist_ok=True)

        machine_id = _get_machine_id()
        salt = _get_or_create_salt(self._data_dir)
        self._key = _derive_key(machine_id, salt)
        self._cipher = Fernet(self._key)
        self._path = os.path.join(self._data_dir, _STORE_FILE)
        self._store = {}
        self._load()

    def _load(self) -> None:
        if not self._enabled or self._path is None or not os.path.exists(self._path):
            return
        try:
            encrypted = Path(self._path).read_bytes()
            decrypted = self._cipher.decrypt(encrypted)
            self._store = json.loads(decrypted.decode())
        except (InvalidToken, json.JSONDecodeError, Exception) as e:
            viki_logger.error("Failed to decrypt credential store: %s", e)
            self._store = {}

    def _save(self) -> None:
        if not self._enabled or self._path is None:
            return
        try:
            raw = json.dumps(self._store, indent=2).encode()
            encrypted = self._cipher.encrypt(raw)
            Path(self._path).write_bytes(encrypted)
        except Exception as e:
            viki_logger.error("Failed to save credential store: %s", e)

    def get(self, key: str, default: str | None = None) -> str | None:
        """Retrieve a credential. Falls back to environment variable."""
        if key in self._store:
            return self._store[key]
        return os.environ.get(key, default)

    def set(self, key: str, value: str) -> None:
        """Store a credential."""
        self._store[key] = value
        self._save()

    def delete(self, key: str) -> bool:
        """Delete a credential. Returns True if existed."""
        existed = key in self._store
        self._store.pop(key, None)
        if existed:
            self._save()
        return existed

    def list_keys(self) -> list[str]:
        """List all stored credential keys (not values)."""
        return list(self._store.keys())

    def is_available(self) -> bool:
        return self._enabled and self._path is not None and os.path.exists(self._path)


# CLI helper
def _run_credential_cli():
    """Command-line interface for credential management."""
    import argparse

    parser = argparse.ArgumentParser(description="VIKI Credential Manager")
    parser.add_argument("action", choices=["get", "set", "delete", "list"], help="Action")
    parser.add_argument("key", nargs="?", help="Credential key (e.g. OPENAI_API_KEY)")
    parser.add_argument("value", nargs="?", help="Credential value (for 'set')")
    parser.add_argument("--data-dir", help="VIKI data directory")

    args = parser.parse_args()
    mgr = CredentialManager(data_dir=args.data_dir)

    if not mgr._enabled:
        print("Error: cryptography library not installed.")
        sys.exit(1)

    if args.action == "get":
        if not args.key:
            print("Error: key required for 'get'")
            sys.exit(1)
        val = mgr.get(args.key)
        if val is None:
            print(f"Key '{args.key}' not found in store or environment.")
        else:
            print(val)

    elif args.action == "set":
        if not args.key or not args.value:
            print("Error: key and value required for 'set'")
            sys.exit(1)
        mgr.set(args.key, args.value)
        print(f"Credential '{args.key}' stored securely.")

    elif args.action == "delete":
        if not args.key:
            print("Error: key required for 'delete'")
            sys.exit(1)
        if mgr.delete(args.key):
            print(f"Credential '{args.key}' deleted.")
        else:
            print(f"Key '{args.key}' not found.")

    elif args.action == "list":
        keys = mgr.list_keys()
        if keys:
            print("Stored credentials:")
            for k in keys:
                print(f"  - {k}")
        else:
            print("No credentials stored.")


if __name__ == "__main__":
    _run_credential_cli()
