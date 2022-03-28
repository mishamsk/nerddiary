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
    def __init__(self, password_or_key: str | bytes, init_token: bytes = None, control_message: bytes = None) -> None:
        """Inits a new Encryption provider. Encrypts messages into a (salt, iterations, encrypted_message) tokens. Decrypts such tokens.

        If no `init_token` is given and a password is used, a new salt is generated, standard iterations value is set and a new key is derived from a given password.

        If `init_token` is provided it is decrypted using the given password or key. Throws `cryptography.fernet.InvalidToken` if it failed (meaning the password or key is incorrect)

        If a `control_message` is given, the decrypted message is compared to `control_message`. In case of mismatch a `ValueError` is raised"""

        salt = iterations = key = password = None

        if isinstance(password_or_key, str):
            password = password_or_key
        elif isinstance(password_or_key, bytes):
            if init_token is None:
                raise ValueError("Key may not be used without an `init_token`")
            key = password_or_key
        else:
            raise ValueError("`password_or_key` must be either a `str` password ot `bytes` key")

        if init_token is not None:
            decoded = b64d(init_token)
            salt, iter, token = decoded[:16], decoded[16:20], b64e(decoded[20:])
            iterations = int.from_bytes(iter, "big")
            key = key or _derive_key(password.encode(), salt, iterations)
            init_message = Fernet(key).decrypt(token)

            if control_message is not None and control_message != init_message:
                raise ValueError("Init message didn't match control bytes")

        self._iterations = iterations or ITERATIONS
        self._salt = salt or secrets.token_bytes(16)
        self._key = key or _derive_key(password.encode(), self._salt, self._iterations)

    @property
    def salt(self) -> bytes:
        return self._salt  # pragma: no cover

    @property
    def iterations(self) -> int:
        return self._iterations  # pragma: no cover

    @property
    def key(self) -> bytes:
        return self._key

    def encrypt(self, message: bytes) -> bytes:
        """Encrypts message and stores it alongside the salt & iterations"""
        return b64e(
            b"%b%b%b"
            % (
                self._salt,
                self._iterations.to_bytes(4, "big"),
                b64d(Fernet(self._key).encrypt(message)),
            )
        )

    def decrypt(self, token: bytes) -> bytes:
        """Validates the message has the same salt & iterations stored and then decrypts the message.

        Throws `ValueError` if salt or iterations mismatch, which means that the password used to derive the key may have been correct, but the salt/iterations used were wrong

        Throws `cryptography.fernet.InvalidToken` if salt and iterations match but decryption failed (meaning somehow the correct salt/iteration was given during initialization but the password is incorrect)
        """

        decoded = b64d(token)
        salt, iter, token = decoded[:16], decoded[16:20], b64e(decoded[20:])
        iterations = int.from_bytes(iter, "big")
        if salt != self._salt or iterations != self._iterations:
            raise ValueError("Salt or iterations mismatch")
        return Fernet(self._key).decrypt(token)
