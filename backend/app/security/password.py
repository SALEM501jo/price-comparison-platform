"""
Password hashing and verification.
SECURITY PRINCIPLE: Never store plain text. Slow down attackers.
"""

from passlib.context import CryptContext

# bcrypt with cost factor 12
# Cost factor determines how many rounds of hashing:
#   10 = ~60ms per hash
#   12 = ~250ms per hash  (current OWASP recommendation)
#   14 = ~1s per hash
# 
# TRADE-OFF: Every login request burns 250ms of CPU.
# An attacker with a leaked DB needs 250ms per guess.
# At cost 12, 1 billion guesses = ~8 years on modern GPU.
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12
)


def hash_password(plain_password: str) -> str:
    """
    Hash a password for storage.
    The returned string contains: algorithm, cost, salt, hash.
    Example: $2b$12$randomsalt..............................hash
    """
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_dummy_hash() -> str:
    """
    Generate a dummy bcrypt hash for timing attack prevention.
    
    TIMING ATTACK EXPLANATION:
    If user doesn't exist, we return "not found" in 1ms.
    If user exists but password is wrong, we run bcrypt in 250ms.
    An attacker measures response time:
        - 1ms = user doesn't exist
        - 250ms = user exists, wrong password
    They can enumerate valid emails this way.
    
    THE FIX:
    Always run verify_password(), even if user not found.
    Pass a dummy hash so the function takes ~250ms regardless.
    """
    # This is a valid bcrypt hash structure. verify_password() will fail
    # but take the same time as a real hash verification.
    return "$2b$12$abcdefghijklmnopqrstuuxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"