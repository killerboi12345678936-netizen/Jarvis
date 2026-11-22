
import json
from datetime import datetime, timedelta, timezone

import aiosqlite

from backend.memory.database import DB_PATH, now


async def propose_action(tool_name, arguments):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO tool_actions
            (tool_name, arguments, status, created_at, updated_at)
            VALUES (?, ?, 'pending', ?, ?)
            """,
            (
                tool_name,
                json.dumps(arguments),
                now(),
                now(),
            ),
        )

        await db.commit()
        return cursor.lastrowid


async def get_action(action_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT * FROM tool_actions WHERE id = ?",
            (action_id,),
        )

        row = await cursor.fetchone()
        return dict(row) if row else None


async def list_actions(status=None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        if status:
            cursor = await db.execute(
                """
                SELECT * FROM tool_actions
                WHERE status = ?
                ORDER BY id DESC
                """,
                (status,),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM tool_actions ORDER BY id DESC"
            )

        return [dict(row) for row in await cursor.fetchall()]


async def update_action(action_id, status, result=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            UPDATE tool_actions
            SET status = ?, result = ?, updated_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (status, result, now(), action_id),
        )

        await db.commit()
        return cursor.rowcount == 1


async def claim_action(action_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            UPDATE tool_actions
            SET status = 'executing', updated_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (now(), action_id),
        )
        await db.commit()
        return cursor.rowcount == 1


async def finish_action(action_id, status, result=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            UPDATE tool_actions
            SET status = ?, result = ?, updated_at = ?
            WHERE id = ? AND status = 'executing'
            """,
            (status, result, now(), action_id),
        )
        await db.commit()
        return cursor.rowcount == 1


async def recover_stale_actions(max_age_seconds=600):
    """Mark actions stuck in 'executing' as failed.

    If the backend crashes between claim_action() and finish_action(),
    the action would otherwise stay 'executing' forever, invisible to
    the pending filter and impossible to retry."""

    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(seconds=max_age_seconds)
    ).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            UPDATE tool_actions
            SET status = 'failed',
                result = ?,
                updated_at = ?
            WHERE status = 'executing' AND updated_at < ?
            """,
            (
                "Execution was interrupted before it could finish. "
                "Approve again to retry.",
                now(),
                cutoff,
            ),
        )
        await db.commit()
        return cursor.rowcount
