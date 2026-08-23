"""
Password hashing and verification using bcrypt directly.
SECURITY PRINCIPLE: Never store plain text. Slow down attackers.
"""

import bcrypt


def hash_password(plain_password: str) -> str:
    """
    Hash a password for storage.
    bcrypt has a 72-byte limit. We truncate if necessary.
    """
    # Encode to bytes and truncate to 72 bytes (bcrypt limit)
    password_bytes = plain_password.encode('utf-8')[:72]
    # Generate salt with cost factor 12
    salt = bcrypt.gensalt(rounds=12)
    # Hash and return as string
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.
    """
    password_bytes = plain_password.encode('utf-8')[:72]
    hash_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hash_bytes)


def get_dummy_hash() -> str:
    """
    Generate a dummy bcrypt hash for timing attack prevention.
    This is a real hash of "dummy" — verification will always fail.
    """
    # Pre-generated hash of "dummy" with cost 12
    return "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6LqT7iL8e8ZR1ZHy"