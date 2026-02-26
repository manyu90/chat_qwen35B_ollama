import aiosqlite
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "chat.db"


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'tool')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id, created_at);
        """)
        await db.commit()
    finally:
        await db.close()


async def create_conversation(title: str) -> dict:
    conv_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO conversations (id, title, created_at) VALUES (?, ?, ?)",
            (conv_id, title, now),
        )
        await db.commit()
        return {"id": conv_id, "title": title, "created_at": now}
    finally:
        await db.close()


async def list_conversations() -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, title, created_at FROM conversations ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_conversation(conv_id: str) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, title, created_at FROM conversations WHERE id = ?",
            (conv_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None

        conv = dict(row)

        cursor = await db.execute(
            "SELECT id, conversation_id, role, content, created_at "
            "FROM messages WHERE conversation_id = ? ORDER BY created_at",
            (conv_id,),
        )
        messages = await cursor.fetchall()
        conv["messages"] = [dict(m) for m in messages]
        return conv
    finally:
        await db.close()


async def delete_conversation(conv_id: str) -> bool:
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM conversations WHERE id = ?", (conv_id,)
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def add_message(conversation_id: str, role: str, content: str) -> dict:
    msg_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (msg_id, conversation_id, role, content, now),
        )
        await db.commit()
        return {
            "id": msg_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "created_at": now,
        }
    finally:
        await db.close()


async def get_messages(conversation_id: str) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, conversation_id, role, content, created_at "
            "FROM messages WHERE conversation_id = ? ORDER BY created_at",
            (conversation_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()
