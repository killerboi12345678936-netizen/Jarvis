
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.memory.database import (
    add_memory_dedup,
    get_memories,
    update_memory,
    delete_memory,
)

router = APIRouter(prefix="/api/memories", tags=["Memories"])

Category = Literal[
    "general",
    "project",
    "skill",
    "preference",
    "interest",
]


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    category: Category = "general"


class MemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=5000)
    category: Category | None = None


@router.post("/")
async def create_memory(request: MemoryCreate):
    result = await add_memory_dedup(
        request.content,
        request.category,
    )

    return {
        "success": True,
        "memory_id": result["id"],
        "duplicate": result["duplicate"],
    }


@router.get("/")
async def memories(
    category: Category | None = None,
    search: str | None = None,
    limit: int = 100,
):
    limit = max(1, min(limit, 500))

    results = await get_memories(
        category=category,
        search=search,
        limit=limit,
    )

    return {
        "count": len(results),
        "memories": results,
    }


@router.put("/{memory_id}")
async def edit_memory(memory_id: int, request: MemoryUpdate):
    success = await update_memory(
        memory_id,
        content=request.content,
        category=request.category,
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Memory not found or no changes supplied.",
        )

    return {"success": True}


@router.delete("/{memory_id}")
async def remove_memory(memory_id: int):
    success = await delete_memory(memory_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Memory not found.",
        )

    return {"success": True}
