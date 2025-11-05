from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from Database.database import Item


async def find_item_by_title(db, user_id: int, title: str) -> Item:
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Item)
        .options(selectinload(Item.board))
        .filter(
            Item.user_id == user_id,
            func.lower(Item.title) == func.lower(title)
        )
    )
    return result.scalar_one_or_none()


async def find_item_by_id(db, user_id: int, item_id: int) -> Item:
    result = await db.execute(
        select(Item)
        .options(selectinload(Item.board))  # Это ключевое!
        .filter(
            Item.user_id == user_id,
            Item.id == item_id,
        )
    )
    item = result.scalar_one_or_none()
    return item


async def find_items_by_keyword(db, user_id: int, keyword: str):
    search_pattern = f"%{keyword}%"
    print(f"Searching for: '{keyword}' -> pattern: '{search_pattern}'")

    result = await db.execute(
        select(Item).filter(
            Item.user_id == user_id,
            func.lower(Item.title).like(func.lower(search_pattern))
        ).order_by(Item.title)
    )
    items = result.scalars().all()

    print(f"📋 Found {len(items)} items")
    for item in items:
        print(f"   - '{item.title}'")

    return items