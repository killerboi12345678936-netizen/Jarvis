
import sqlite3
from datetime import datetime, timezone
from config import BASE_DIR

DB_PATH = BASE_DIR / "jarvis.db"

MEMORY_CATEGORIES = {
    "project",
    "skill",
    "preference",
    "interest",
    "general",
}


def connect():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS sessions(
            id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            closed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            provider TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS memories(
            id INTEGER PRIMARY KEY,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)

        # Safely upgrade older databases.
        columns = {
            row["name"]
            for row in c.execute("PRAGMA table_info(memories)").fetchall()
        }

        if "category" not in columns:
            c.execute(
                "ALTER TABLE memories "
                "ADD COLUMN category TEXT NOT NULL DEFAULT 'general'"
            )


def create_session():
    with connect() as c:
        return c.execute(
            "INSERT INTO sessions(created_at) VALUES (?)",
            (now(),)
        ).lastrowid


def get_latest_session():
    with connect() as c:
        r = c.execute(
            "SELECT id FROM sessions WHERE closed_at IS NULL "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return r["id"] if r else None


def close_session(sid):
    with connect() as c:
        c.execute(
            "UPDATE sessions SET closed_at=? WHERE id=?",
            (now(), sid)
        )


def save_message(sid, role, provider, content):
    with connect() as c:
        c.execute(
            "INSERT INTO messages"
            "(session_id,role,provider,content,created_at) "
            "VALUES(?,?,?,?,?)",
            (sid, role, provider, content, now())
        )


def get_messages(sid, limit=20):
    with connect() as c:
        rows = c.execute(
            "SELECT role,provider,content,created_at "
            "FROM messages WHERE session_id=? "
            "ORDER BY id DESC LIMIT ?",
            (sid, limit)
        ).fetchall()
        return [dict(x) for x in reversed(rows)]


def add_memory(content, category="general"):
    category = category.strip().lower()
    content = content.strip()

    if category not in MEMORY_CATEGORIES:
        raise ValueError("Invalid memory category.")

    if not content:
        return None

    normalized = " ".join(content.casefold().split())

    with connect() as c:
        existing = c.execute(
            "SELECT id, content FROM memories"
        ).fetchall()

        for row in existing:
            saved = " ".join(row["content"].casefold().split())

            if saved == normalized:
                return None

        cur = c.execute(
            "INSERT INTO memories(content,created_at,category) "
            "VALUES(?,?,?)",
            (content, now(), category)
        )

        return cur.lastrowid


def get_memories():
    # Keep the original three-field format for existing code.
    with connect() as c:
        rows = c.execute(
            "SELECT id,content,created_at "
            "FROM memories ORDER BY id DESC"
        ).fetchall()

        return [
            (r["id"], r["content"], r["created_at"])
            for r in rows
        ]


def get_memory_details(category=None):
    with connect() as c:
        if category:
            rows = c.execute(
                "SELECT id,content,created_at,category "
                "FROM memories WHERE category=? ORDER BY id DESC",
                (category,)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT id,content,created_at,category "
                "FROM memories ORDER BY id DESC"
            ).fetchall()

        return [dict(r) for r in rows]


def delete_memory(mid):
    with connect() as c:
        cur = c.execute(
            "DELETE FROM memories WHERE id=?",
            (mid,)
        )
        return cur.rowcount > 0
