import secrets
from base64 import urlsafe_b64decode as b64d
from base64 import urlsafe_b64encode as b64e

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

BACKEND = default_backend()
ITERATIONS = 390000


def _derive_key(password: bytes, salt: bytes, iterations: int = ITERATIONS) -> bytes:
    """Derive a secret key from a given password and salt"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
        backend=BACKEND,
    )
    return b64e(kdf.derive(password))


class EncryptionProdiver:
    def __init__(self, password: str, iterations: int = ITERATIONS) -> None:
        self._password = password
        self._iterations = iterations
        self._salt = secrets.token_bytes(16)
        self._key = _derive_key(password.encode(), self._salt, self._iterations)

    def encrypt(self, message: bytes) -> bytes:
        return b64e(
            b"%b%b%b"
            % (
                self._salt,
                self._iterations.to_bytes(4, "big"),
                b64d(Fernet(self._key).encrypt(message)),
            )
        )

    def decrypt(self, token: bytes) -> bytes:
        decoded = b64d(token)
        salt, iter, token = decoded[:16], decoded[16:20], b64e(decoded[20:])
        iterations = int.from_bytes(iter, "big")
        if salt != self._salt or iterations != self._iterations:
            key = _derive_key(self._password.encode(), salt, iterations)
        else:
            key = self._key
        return Fernet(key).decrypt(token)
