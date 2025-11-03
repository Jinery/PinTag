from sqlalchemy import func

from Database.database import Item


def find_item_by_title(db, user_id: int, title: str) -> Item:
    return db.query(Item).filter(
        Item.user_id == user_id,
        Item.title == title
    ).first()

def find_item_by_id(db, user_id: int, item_id: int) -> Item:
    return db.query(Item).filter(
        Item.user_id == user_id,
        Item.id == item_id,
    ).first()


def find_items_by_keyword(db, user_id: int, keyword: str):
    search_pattern = f"%{keyword.lower()}%"
    print(f"🔍 Searching for: '{keyword}' -> pattern: '{search_pattern}'")

    items = db.query(Item).filter(
        Item.user_id == user_id,
        func.lower(Item.title).like(search_pattern)
    ).order_by(Item.title).all()

    print(f"📋 Found {len(items)} items")
    for item in items:
        print(f"   - {item.title}")

    return items