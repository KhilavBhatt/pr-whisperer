"""
Symmetric encryption helpers for storing reversible secrets (like GitHub
OAuth access tokens) in the database. Uses Fernet, which is authenticated
encryption — it also detects if the encrypted value has been tampered with.

This is NOT for passwords. Passwords should always be hashed (one-way),
never encrypted. This module is specifically for secrets we need to
retrieve in their original form later, like a token we must send back
to GitHub's API.
"""

from cryptography.fernet import Fernet
from django.conf import settings


def _get_fernet():
    """Build a Fernet instance from the project's ENCRYPTION_KEY."""
    return Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt_token(plaintext: str) -> str:
    """Encrypt a plaintext string for storage. Returns a string safe for a TextField."""
    fernet = _get_fernet()
    encrypted_bytes = fernet.encrypt(plaintext.encode())
    return encrypted_bytes.decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a previously-encrypted string back to its original plaintext."""
    fernet = _get_fernet()
    decrypted_bytes = fernet.decrypt(ciphertext.encode())
    return decrypted_bytes.decode()
