import datetime
import logging

from sqlalchemy import Integer, String, DateTime, Text, Boolean, BigInteger
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql.schema import Column, ForeignKey

logger = logging.getLogger(__name__)

DATABASE_URL = "sqlite+aiosqlite:///pintag_data.db"

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)

    boards = relationship("Board", back_populates="user")
    items = relationship("Item", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"


class Board(Base):
    __tablename__ = 'boards'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    name = Column(String, nullable=False)
    emoji = Column(String, default="📁")
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.timezone.utc))

    user = relationship("User", back_populates="boards")
    items = relationship("Item", back_populates="board", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Board(name='{self.name}', user_id={self.user_id})>"


class Item(Base):
    __tablename__ = 'items'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id'))
    board_id = Column(Integer, ForeignKey('boards.id'))
    title = Column(String(255), nullable=False)
    content_type = Column(String(50), nullable=False)
    content_data = Column(Text)
    file_path = Column(String(500))
    file_size = Column(Integer)
    encrypted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.timezone.utc))

    user = relationship("User", back_populates="items")
    board = relationship("Board", back_populates="items")

    def __repr__(self):
        return f"<Item(title='{self.title}', type='{self.content_type}')>"


engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def create_default_board(user_id: int, db: AsyncSession):
    default_board = Board(
        user_id=user_id,
        name="Неотсортированное",
        emoji="📥"
    )
    db.add(default_board)
    await db.commit()
    await db.refresh(default_board)
    return default_board