from fastapi import Header, HTTPException
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select

from database.database import get_db, UserConnection


async def verify_token(user_id: int, x_auth_token: Optional[str] = Header(None)):
    if not x_auth_token:
        raise HTTPException(
            status_code=401,
            detail="Authentication token required"
        )

    async for db in get_db():
        try:
            result = await db.execute(
                select(UserConnection).where(
                    UserConnection.user_id == user_id,
                    UserConnection.connect_id == x_auth_token,
                    UserConnection.status == 'accepted'
                )
            )
            connection = result.scalar_one_or_none()

            if not connection:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid or expired authentication token"
                )

            return user_id
        except SQLAlchemyError:
            raise HTTPException(
                status_code=500,
                detail="Database error"
            )