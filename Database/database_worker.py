import logging
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from Database.database import get_db, Item, Board
from utils.item_searcher import find_item_by_id, find_item_by_title, find_items_by_keyword

logger = logging.getLogger()


async def get_all_items_by_keyword(user_id: int, keyword: str):
    async for db in get_db():
        try:
            search_pattern = f"%{keyword}%"

            result = await db.execute(
                select(Item, Board)
                .join(Board, Item.board_id == Board.id)
                .filter(
                    Item.user_id == user_id,
                    func.lower(Item.title).like(func.lower(search_pattern))
                )
                .order_by(Item.title)
            )

            items_with_boards = result.all()
            items = []
            for item, board in items_with_boards:
                item.board = board
                items.append(item)

            return items
        except SQLAlchemyError as sqlex:
            raise sqlex


async def get_item_by_title(user_id: int, item_title: str):
    async for db in get_db():
        try:
            return await find_item_by_title(db, user_id, item_title)
        except SQLAlchemyError as sqlex:
            raise sqlex

async def get_item_by_id(user_id: int, item_id: int):
    async for db in get_db():
        try:
            return await find_item_by_id(db, user_id, item_id)
        except SQLAlchemyError as sqlex:
            raise sqlex


async def get_all_user_boards(user_id: int):
    async for db in get_db():
        try:
            result = await db.execute(
                select(Board).filter(Board.user_id == user_id).order_by(Board.name)
            )
            return result.scalars().all()
        except SQLAlchemyError as sqlex:
            raise sqlex


async def get_all_user_items(user_id: int):
    async for db in get_db():
        try:
            result = await db.execute(select(Item).filter(Item.user_id == user_id))
            return result.scalars().all()
        except SQLAlchemyError as sqlex:
            raise sqlex


async def get_all_user_board_count(user_id: int) -> int:
    async for db in get_db():
        try:
            result = await db.execute(
                select(func.count(Board.id)).filter(Board.user_id == user_id)
            )
            return result.scalar()
        except SQLAlchemyError as sqlex:
            raise sqlex


async def get_all_user_item_count(user_id: int):
    async for db in get_db():
        try:
            result = await db.execute(
                select(func.count(Item.id)).filter(Item.user_id == user_id)
            )
            return result.scalar()
        except SQLAlchemyError as sqlex:
            raise sqlex


async def get_board_item_count(user_id: int, board_id: int) -> int:
    async for db in get_db():
        try:
            result = await db.execute(
                select(func.count(Item.id)).filter(
                    Item.user_id == user_id,
                    Item.board_id == board_id
                )
            )
            return result.scalar()
        except SQLAlchemyError as sqlex:
            raise sqlex


async def get_board_by_name(user_id: int, board_name: str):
    async for db in get_db():
        try:
            result = await db.execute(
                select(Board).filter(
                    Board.user_id == user_id,
                    func.lower(Board.name) == func.lower(board_name),
                )
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as sqlex:
            raise sqlex


async def get_board_by_id(user_id: int, board_id: int):
    async for db in get_db():
        try:
            result = await db.execute(
                select(Board).filter(
                    Board.user_id == user_id,
                    Board.id == board_id
                )
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as sqlex:
            raise sqlex


async def update_board_name(user_id: int, board_id: int, new_name: str, new_emoji: str = None):
    async for db in get_db():
        try:
            result = await db.execute(
                select(Board).filter(
                    Board.id == board_id,
                    Board.user_id == user_id
                )
            )
            board = result.scalar_one_or_none()

            if not board:
                raise ValueError("Board not found")
            old_name = board.name
            old_emoji = board.emoji
            final_emoji = new_emoji if new_emoji else old_emoji
            board.name = new_name
            board.emoji = final_emoji

            await db.commit()

            return (old_name, old_emoji, new_name, final_emoji)
        except SQLAlchemyError as sqlex:
            await db.rollback()
            raise sqlex


async def create_new_board(user_id: int, board_name: str, board_emoji: str):
    async for db in get_db():
        try:
            new_board = Board(
                name=board_name,
                emoji=board_emoji,
                user_id=user_id,
            )
            db.add(new_board)
            await db.commit()
            await db.refresh(new_board)
            return new_board
        except SQLAlchemyError as sqlex:
            await db.rollback()
            raise sqlex


async def remove_board_by_id(user_id: int, board_id: int):
    async for db in get_db():
        try:
            result = await db.execute(
                select(Board).filter(Board.id == board_id, Board.user_id == user_id)
            )
            board = result.scalar_one_or_none()

            if not board:
                raise ValueError("Board not found")

            await db.delete(board)
            await db.commit()
            return True
        except SQLAlchemyError as sqlex:
            await db.rollback()
            raise sqlex



async def get_all_items_by_board_id(user_id: int, board_id: int):
    async for db in get_db():
        try:
            result = await db.execute(
                select(Item).filter(
                    Item.user_id == user_id,
                    Item.board_id == board_id
                ).order_by(Item.title)
            )
            return result.scalars().all()
        except SQLAlchemyError as sqlex:
            raise sqlex


async def create_new_item(user_id: int, board_id: int, title: str, content_type: str, content_data: str,
    file_path: str, file_size: int, encrypted: bool):
    async for db in get_db():
        try:
            new_item = Item(
                user_id=user_id,
                board_id=board_id,
                title=title,
                content_type=content_type,
                content_data=content_data,
                file_path=file_path,
                file_size=file_size,
                encrypted=encrypted,
            )
            db.add(new_item)
            await db.commit()
            await db.refresh(new_item)
            return new_item
        except SQLAlchemyError as sqlex:
            await db.rollback()
            raise sqlex


async def remove_item_by_id(user_id: int, item_id: int):
    async for db in get_db():
        try:
            result = await db.execute(
                select(Item).filter(Item.id == item_id, Item.user_id == user_id)
            )
            item = result.scalar_one_or_none()

            if not item:
                raise ValueError("Item not found")

            await db.delete(item)
            await db.commit()
            return True
        except SQLAlchemyError as sqlex:
            await db.rollback()
            raise sqlex


async def move_item(user_id: int, item_id: int, new_board_id: int):
    async for db in get_db():
        try:
            result = await db.execute(
                select(Item).filter(
                    Item.id == item_id,
                    Item.user_id == user_id
                )
            )
            item = result.scalar_one_or_none()

            if not item:
                raise ValueError("Item not found")

            item.board_id = new_board_id
            await db.commit()

        except SQLAlchemyError as sqlex:
            await db.rollback()
            raise sqlex


async def get_item_stats(user_id: int):
    async for db in get_db():
        try:
            result = await db.execute(
                select(Item.content_type, func.count(Item.id))
                .filter(Item.user_id == user_id)
                .group_by(Item.content_type)
            )
            return result.all()
        except SQLAlchemyError as sqlex:
            raise sqlex