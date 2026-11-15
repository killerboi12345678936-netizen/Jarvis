
import json

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
