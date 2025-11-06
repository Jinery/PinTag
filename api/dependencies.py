from fastapi import Header, HTTPException
from typing import Optional


async def verify_token(user_id: int, x_auth_token: Optional[str] = Header(None)):
    if not x_auth_token:
        raise HTTPException(
            status_code=401,
            detail="Authentication token required"
        )