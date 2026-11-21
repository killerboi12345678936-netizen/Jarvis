
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from backend.memory.textutils import text_similarity


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "jarvis.db"


def now():
    return datetime.now(timezone.utc).isoformat()


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        await db.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            closed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            provider TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(session_id)
                REFERENCES sessions(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            created_at TEXT NOT NULL,
            updated_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session
        ON messages(session_id);

        CREATE INDEX IF NOT EXISTS idx_memories_category
        ON memories(category);

        CREATE TABLE IF NOT EXISTS tool_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT NOT NULL,
            arguments TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            result TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_tool_actions_status
        ON tool_actions(status);

        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            start_utc TEXT NOT NULL,
            end_utc TEXT NOT NULL,
            notes TEXT,
            source TEXT NOT NULL DEFAULT 'local',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_calendar_events_start
        ON calendar_events(start_utc);

        """)

        await db.commit()


async def create_session():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO sessions (created_at) VALUES (?)",
            (now(),),
        )
        await db.commit()
        return cursor.lastrowid


async def get_session(session_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def list_sessions(limit=50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT s.*,
                   (SELECT content FROM messages
                    WHERE session_id = s.id
                    ORDER BY id DESC LIMIT 1) AS last_message
            FROM sessions s
            ORDER BY s.id DESC
            LIMIT ?
            """,
            (limit,),
        )

        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def close_session(session_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            UPDATE sessions
            SET closed_at = ?
            WHERE id = ? AND closed_at IS NULL
            """,
            (now(), session_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def save_message(session_id, role, provider, content):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO messages
            (session_id, role, provider, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, role, provider, content, now()),
        )
        await db.commit()
        return cursor.lastrowid


async def get_messages(session_id, limit=100):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT * FROM (
                SELECT * FROM messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
            ORDER BY id ASC
            """,
            (session_id, limit),
        )

        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def add_memory(content, category="general"):
    timestamp = now()

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO memories
            (content, category, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (content, category, timestamp, timestamp),
        )
        await db.commit()
        return cursor.lastrowid


async def add_memory_dedup(content, category="general", duplicate_threshold=0.8):
    normalized = " ".join(content.split())

    existing = await get_memories(limit=500)

    for memory in existing:
        if text_similarity(normalized, memory["content"]) >= duplicate_threshold:
            return {
                "id": memory["id"],
                "duplicate": True,
                "existing": memory,
            }

    memory_id = await add_memory(normalized, category)

    return {
        "id": memory_id,
        "duplicate": False,
        "existing": None,
    }


async def get_memories(category=None, search=None, limit=100):
    query = "SELECT * FROM memories WHERE 1=1"
    params = []

    if category:
        query += " AND category = ?"
        params.append(category)

    if search:
        query += " AND content LIKE ?"
        params.append(f"%{search}%")

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def update_memory(memory_id, content=None, category=None):
    updates = []
    params = []

    if content is not None:
        updates.append("content = ?")
        params.append(content)

    if category is not None:
        updates.append("category = ?")
        params.append(category)

    if not updates:
        return False

    updates.append("updated_at = ?")
    params.append(now())
    params.append(memory_id)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"UPDATE memories SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_memory(memory_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM memories WHERE id = ?",
            (memory_id,),
        )
        await db.commit()
        return cursor.rowcount > 0


async def create_calendar_event(title, start_utc, end_utc, notes=None):
    timestamp = now()

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO calendar_events
            (title, start_utc, end_utc, notes, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'local', ?, ?)
            """,
            (title, start_utc, end_utc, notes, timestamp, timestamp),
        )
        await db.commit()
        return cursor.lastrowid


async def list_calendar_events(start_after=None, start_before=None, limit=200):
    query = "SELECT * FROM calendar_events WHERE 1=1"
    params = []

    if start_after:
        query += " AND end_utc >= ?"
        params.append(start_after)

    if start_before:
        query += " AND start_utc <= ?"
        params.append(start_before)

    query += " ORDER BY start_utc ASC LIMIT ?"
    params.append(limit)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def update_calendar_event(
    event_id,
    title=None,
    start_utc=None,
    end_utc=None,
    notes=None,
):
    updates = []
    params = []

    for column, value in (
        ("title", title),
        ("start_utc", start_utc),
        ("end_utc", end_utc),
        ("notes", notes),
    ):
        if value is not None:
            updates.append(f"{column} = ?")
            params.append(value)

    if not updates:
        return False

    updates.append("updated_at = ?")
    params.append(now())
    params.append(event_id)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"UPDATE calendar_events SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_calendar_event(event_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM calendar_events WHERE id = ?",
            (event_id,),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_event_by_id(event_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT * FROM calendar_events WHERE id = ?",
            (event_id,),
        )

        row = await cursor.fetchone()
        return dict(row) if row else None
