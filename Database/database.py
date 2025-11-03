import datetime
import logging

from sqlalchemy import Integer, String, DateTime, Text, Boolean, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.sql.schema import Column, ForeignKey

logger = logging.getLogger(__name__)

DATABASE_URL = "sqlite:///pintag_data.db"

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

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    board_id = Column(Integer, ForeignKey('boards.id'), index=True)

    title = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    content_data = Column(Text)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.timezone.utc))

    user = relationship("User", back_populates="items")
    board = relationship("Board", back_populates="items")

    def __repr__(self):
        return f"<Item(title='{self.title}', type='{self.content_type}')>"


engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_default_board(user_id: int, db):
    default_board = Board(
        user_id=user_id,
        name="Неотсортированное",
        emoji = "📥"
    )
    db.add(default_board)
    return default_board
