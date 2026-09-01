"""
Admin routes for accounts and roles.

SECURITY PRINCIPLE: Role-Based Access Control. Every route here is
guarded by require_admin, and every action is logged with the admin's
id -- an administrator changing somebody else's access is precisely
the thing that has to be answerable later.
"""

from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.logging_config import get_security_logger
from app.models.user import User, UserRole
from app.schemas.auth import UserResponse

router = APIRouter()
logger = get_security_logger("app.admin")


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    List all users. Admin only.
    """
    logger.warning("Admin listing all users", extra={
        "admin_id": admin.id,
        "action": "admin_list_users",
        "target": "all_users"
    })
    
    # Bounded. This was an unqualified .all(): fine with 22 accounts, and a
    # way to load the entire user table into memory the day it is not. The
    # response is still a plain list, so callers are unaffected.
    return (
        db.query(User)
        .order_by(User.id)
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    Delete a user. Admin only.
    Cannot delete yourself.
    """
    if admin.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    logger.warning("Admin deleted user", extra={
        "admin_id": admin.id,
        "action": "admin_delete_user",
        "target": user_id
    })
    
    db.delete(user)
    db.commit()
    return None

# --- Role management --------------------------------------------------------
#
# WHY THIS EXISTS AT ALL: without it there is no way to create a second admin.
# The first one is made by hand against the database; every one after that has
# to come from here, and a platform with exactly one administrator is one
# forgotten password away from having none.


class RoleChange(BaseModel):
    """
    A role change, restricted to the three real roles.

    A Literal rather than the UserRole enum so an unknown value is a 422 at
    the edge instead of something the handler has to remember to reject.
    """

    role: Literal["user", "merchant", "admin"]


@router.patch("/users/{user_id}/role")
async def change_user_role(
    user_id: int,
    body: RoleChange,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Grant or revoke a role. Admin only.

    TWO GUARDS, BOTH ABOUT NOT LOCKING EVERYONE OUT:

      - An admin cannot change their OWN role. Demoting yourself by accident
        is unrecoverable from inside the application, and there is no reason
        to do it deliberately that a second admin cannot serve better.
      - The last admin cannot be demoted by anyone. A platform with zero
        admins cannot appoint one, and the only route back is manual surgery
        on the database.

    Demoting a merchant does NOT delete their store or its listings. The
    prices stay, and stay visible if the store was verified -- pulling a shop
    off the site is what unverify is for, and conflating the two would make
    a role change silently destroy a shop's public presence.
    """
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if target.id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot change your own role. Ask another admin.",
        )

    new_role = UserRole(body.role)

    if target.role == UserRole.admin and new_role != UserRole.admin:
        remaining = (
            db.query(User)
            .filter(User.role == UserRole.admin, User.id != target.id)
            .count()
        )
        if remaining == 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot demote the last admin. Promote someone else first.",
            )

    previous = target.role
    target.role = new_role
    db.commit()

    logger.warning("Admin changed a user role", extra={
        "admin_id": admin.id,
        "action": "admin_change_role",
        "target": f"user {target.id}: {previous.value} -> {new_role.value}",
    })
    return {"id": target.id, "email": target.email, "role": new_role.value}
