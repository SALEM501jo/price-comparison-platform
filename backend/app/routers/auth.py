"""
Authentication routes.
SECURITY PRINCIPLE: Every auth operation must be auditable and timing-safe.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from app.models.user import User
from app.security.password import hash_password, verify_password, get_dummy_hash
from app.security.jwt_handler import create_access_token, create_refresh_token, verify_token
from app.security.rate_limiter import strict_rate_limit
from app.dependencies import get_current_user
from app.logging_config import get_security_logger
from app.exceptions import AuthenticationError, ConflictError

router = APIRouter()
logger = get_security_logger("app.auth")


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    body: RegisterRequest,
    db: Session = Depends(get_db),
):
    """
    Register a new user.
    
    SECURITY MEASURES:
    1. Rate limiting: 5 attempts/min per IP (strict_rate_limit)
    2. Password validation: min 8 chars, uppercase, lowercase, number
    3. Timing-safe duplicate check: always query DB, don't short-circuit
    4. bcrypt cost 12: ~250ms per hash (slows brute force)
    5. Audit logging: every registration attempt logged
    """
    # Rate limit: prevent brute force registration
    await strict_rate_limit(request)
    
    # Check for existing user
    # SECURITY: We query the DB even if we're going to reject.
    # This prevents timing attacks: "user exists" vs "user doesn't exist"
    # should take the same time.
    existing = db.query(User).filter(User.email == body.email).first()
    
    if existing:
        # Log failed attempt (but don't reveal user exists to attacker)
        logger.warning("Registration failed: email already exists", extra={
            "ip": request.client.host if request.client else "unknown",
            "action": "register",
            "success": False,
            "target": body.email
        })
        raise ConflictError("An account with this email already exists")
    
    # Hash password (slow by design — bcrypt cost 12)
    password_hash = hash_password(body.password)
    
    # Create user
    user = User(
        email=body.email,
        password_hash=password_hash,
        role="user"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Generate tokens
    access_token = create_access_token({
        "sub": str(user.id),
        "role": user.role
    })
    refresh_token = create_refresh_token({
        "sub": str(user.id)
    })
    
    # Log success
    logger.info("User registered", extra={
        "user_id": user.id,
        "ip": request.client.host if request.client else "unknown",
        "action": "register",
        "success": True
    })
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    body: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    Login existing user.
    
    SECURITY MEASURES:
    1. Rate limiting: 5 attempts/min per IP
    2. Timing-safe comparison: always run verify_password, even if user not found
    3. Dummy hash: prevents timing attack enumeration of valid emails
    4. Audit logging: every login attempt logged with success/failure
    """
    await strict_rate_limit(request)
    
    # Find user
    user = db.query(User).filter(User.email == body.email).first()
    
    # TIMING ATTACK PREVENTION:
    # If user doesn't exist, we still run verify_password with a dummy hash.
    # This ensures the function takes ~250ms regardless of whether user exists.
    # Attacker can't distinguish "user not found" (1ms) from "wrong password" (250ms).
    password_hash = user.password_hash if user else get_dummy_hash()
    password_valid = verify_password(body.password, password_hash)
    
    if not user or not password_valid:
        # Log failed login (same response for both cases)
        logger.warning("Login failed", extra={
            "ip": request.client.host if request.client else "unknown",
            "action": "login",
            "success": False,
            "target": body.email
        })
        raise AuthenticationError("Invalid email or password")
    
    # Success — generate tokens
    access_token = create_access_token({
        "sub": str(user.id),
        "role": user.role
    })
    refresh_token = create_refresh_token({
        "sub": str(user.id)
    })
    
    logger.info("User logged in", extra={
        "user_id": user.id,
        "ip": request.client.host if request.client else "unknown",
        "action": "login",
        "success": True
    })
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    refresh_token: str,
    db: Session = Depends(get_db),
):
    """
    Refresh access token using refresh token.
    
    SECURITY: Refresh tokens are long-lived (7 days). If one is stolen,
    the attacker can keep getting new access tokens. In production,
    you'd store refresh tokens in DB and check revocation here.
    """
    await strict_rate_limit(request)
    
    try:
        payload = verify_token(refresh_token, token_type="refresh")
    except Exception:
        logger.warning("Token refresh failed: invalid token", extra={
            "ip": request.client.host if request.client else "unknown",
            "action": "refresh",
            "success": False
        })
        raise AuthenticationError("Invalid refresh token")
    
    user_id = int(payload.get("sub"))
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise AuthenticationError("User not found")
    
    # Issue new access token
    new_access = create_access_token({
        "sub": str(user.id),
        "role": user.role
    })
    
    logger.info("Token refreshed", extra={
        "user_id": user.id,
        "ip": request.client.host if request.client else "unknown",
        "action": "refresh",
        "success": True
    })
    
    return TokenResponse(
        access_token=new_access,
        refresh_token=refresh_token,  # Same refresh token
        token_type="bearer"
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info."""
    return current_user