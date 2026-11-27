import os

import numpy as np
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import PipelineError
from .timing import measure


def require_key(key: bytes):
    if not isinstance(key, bytes) or len(key) != 32:
        raise PipelineError("AES-256 requires 32 bytes of key material.")


@measure("encrypt")
def encrypt(vector: np.ndarray, key: bytes, aad: bytes | None = None) -> bytes:
    """Return a 12-byte nonce followed by AES-GCM ciphertext and tag."""
    require_key(key)
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, memoryview(vector).cast("B"), aad)


def open_into(blob: bytes, key: bytes, aad: bytes, destination: memoryview) -> None:
    """Decrypt into caller-owned scratch space (15 bytes of AES buffer slack)."""
    try:
        require_key(key)
        if len(blob) != len(destination) - 15 + 28:
            raise PipelineError("Invalid encrypted template length.")
        decryptor = Cipher(algorithms.AES(key), modes.GCM(blob[:12], blob[-16:])).decryptor()
        decryptor.authenticate_additional_data(aad)
        decryptor.update_into(memoryview(blob)[12:-16], destination)
        try:
            decryptor.finalize()
        except InvalidTag:
            raise PipelineError("Template authentication failed. Check key and stored data.") from None
    except BaseException:
        np.frombuffer(destination, dtype=np.uint8).fill(0)
        raise
