import os
from typing import Optional, List

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
from telegram.ext import Application

from database.database_worker import get_all_user_boards, get_board_item_count, get_all_items_by_board_id, \
    get_board_by_id, get_all_items_by_keyword, create_user_connection, get_user_connections, create_new_item, \
    get_item_by_id, remove_item_by_id, get_connection_by_id
from handler.auth_handler import send_connection_request

from .dependencies import verify_token

bot_application: Optional[Application] = None

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

app = FastAPI(
    title="PinTag API",
    description="API для доступа к закладкам из Flutter приложения",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class BoardOut(BaseModel):
    id: int
    name: str
    emoji: str
    item_count: int


class ItemOut(BaseModel):
    id: int
    title: str
    content_type: str
    content_data: Optional[str]
    created_at: str
    board_name: str
    board_emoji: str


class ConnectionRequest(BaseModel):
    client_name: str

class CreateItemRequest(BaseModel):
    board_id: int
    title: str
    content_type: str
    content_data: Optional[str] = None


@app.post("/users/{user_id}/generate-connect")
async def generate_connect_id(
    user_id: int,
    request: ConnectionRequest,
    background_tasks: BackgroundTasks,
    token: str = Depends(verify_token),
):
    try:
        connection = await create_user_connection(user_id, request.client_name)

        async def notify_bot():
            application = Application.builder().token(TOKEN).build()
            await application.initialize()
            await application.start()
            try:
                await send_connection_request(user_id, connection.connect_id, request.client_name, application)
            finally:
                await application.stop()
                await application.shutdown()

        background_tasks.add_task(notify_bot)

        return {
            "status": "success",
            "connect_id": connection.connect_id,
            "message": "Код сгенерирован. Подтверди подключение в боте."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/connections/{connect_id}/status")
async def get_connection_status(connect_id: str, token: str = Depends(verify_token)):
    try:
        connection = await get_connection_by_id(connect_id)

        if not connection:
            raise HTTPException(status_code=404, detail="Подключение не найдено")

        return {
            "connect_id": connection.connect_id,
            "client_name": connection.client_name,
            "status": connection.status,
            "created_at": connection.created_at.isoformat(),
            "confirmed_at": connection.confirmed_at.isoformat() if connection.confirmed_at else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}/connections/pending")
async def get_pending_connections(user_id: int, token: str = Depends(verify_token)):
    try:
        connections = await get_user_connections(user_id)
        pending = [conn for conn in connections if conn.status == 'pending']

        return [
            {
                "connect_id": conn.connect_id,
                "client_name": conn.client_name,
                "created_at": conn.created_at.isoformat()
            }
            for conn in pending
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}/connections")
async def get_connections(user_id: int, token: str = Depends(verify_token)):
    try:
        connections = await get_user_connections(user_id)
        return [
            {
                "id": conn.id,
                "client_name": conn.client_name,
                "status": conn.status,
                "created_at": conn.created_at.isoformat(),
                "confirmed_at": conn.confirmed_at.isoformat() if conn.confirmed_at else None
            }
            for conn in connections
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}/boards", response_model=List[BoardOut])
async def get_user_boards(user_id: int, token: str = Depends(verify_token)):
    try:
        boards = await get_all_user_boards(user_id)

        result = []
        for board in boards:
            count = await get_board_item_count(user_id, board.id)
            result.append(BoardOut(
                id=board.id,
                name=board.name,
                emoji=board.emoji,
                item_count=count
            ))

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}/boards/{board_id}/items", response_model=List[ItemOut])
async def get_board_items(user_id: int, board_id: int, token: str = Depends(verify_token)):
    try:
        items = await get_all_items_by_board_id(user_id, board_id)
        board = await get_board_by_id(user_id, board_id)

        result = []
        for item in items:
            result.append(ItemOut(
                id=item.id,
                title=item.title,
                content_type=item.content_type,
                content_data=item.content_data,
                created_at=item.created_at.isoformat(),
                board_name=board.name,
                board_emoji=board.emoji
            ))

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/users/{user_id}/items")
async def create_item(
        user_id: int,
        request: CreateItemRequest,
        token: str = Depends(verify_token)
):
    try:
        board = await get_board_by_id(user_id, request.board_id)
        if not board:
            raise HTTPException(status_code=404, detail="Доска не найдена")

        new_item = await create_new_item(
            user_id=user_id,
            board_id=request.board_id,
            title=request.title,
            content_type=request.content_type,
            content_data=request.content_data,
            file_path=None,
            file_size=0,
            encrypted=False
        )

        return {
            "status": "success",
            "item_id": new_item.id,
            "message": f"Элемент '{request.title}' создан"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}/search", response_model=List[ItemOut])
async def search_items(user_id: int, q: str, token: str = Depends(verify_token)):
    try:
        items = await get_all_items_by_keyword(user_id, q)

        result = []
        for item in items:
            board = await get_board_by_id(user_id, item.board_id)
            result.append(ItemOut(
                id=item.id,
                title=item.title,
                content_type=item.content_type,
                content_data=item.content_data,
                created_at=item.created_at.isoformat(),
                board_name=board.name,
                board_emoji=board.emoji
            ))

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/users/{user_id}/items/{item_id}")
async def delete_item(user_id: int, item_id: int, token: str = Depends(verify_token)):
    try:
        item = await get_item_by_id(user_id, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Элемент не найден")

        await remove_item_by_id(user_id, item_id)

        return {
            "status": "success",
            "message": f"Элемент '{item.title}' удален"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}/stats")
async def get_user_stats(user_id: int, token: str = Depends(verify_token)):
    try:
        from database.database_worker import (
            get_all_user_board_count, get_all_user_item_count, get_item_stats
        )

        board_count = await get_all_user_board_count(user_id)
        total_items = await get_all_user_item_count(user_id)
        item_stats = await get_item_stats(user_id)

        return {
            "boards_count": board_count,
            "total_items": total_items,
            "items_by_type": dict(item_stats)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    return {"message": "PinTag API", "status": "running"}