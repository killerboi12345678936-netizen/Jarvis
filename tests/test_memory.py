
import asyncio

import pytest

from backend.memory.database import (
    add_memory,
    add_memory_dedup,
    close_session,
    create_session,
    delete_memory,
    get_memories,
    get_messages,
    get_session,
    list_sessions,
    save_message,
    update_memory,
)
from backend.memory.retrieval import (
    find_relevant_memories,
    memory_context_block,
)
from backend.memory.textutils import text_similarity, tokenize


def test_tokenize_filters_stopwords_and_short_words():
    assert tokenize("The cat is on the mat!") == {"cat", "mat"}

    assert tokenize("") == set()

    assert tokenize("I do") == set()


def test_text_similarity_extremes():
    assert text_similarity("red apple", "red apple") == 1.0

    assert text_similarity("red apple", "green car") == 0.0


def test_memory_crud_with_filters(temp_db):
    math_id = asyncio.run(add_memory("Exam on Friday", "school"))
    tea_id = asyncio.run(add_memory("I like green tea", "food"))

    all_memories = asyncio.run(get_memories())

    assert {memory["id"] for memory in all_memories} == {
        math_id,
        tea_id,
    }

    school = asyncio.run(get_memories(category="school"))

    assert len(school) == 1
    assert school[0]["content"] == "Exam on Friday"

    found = asyncio.run(get_memories(search="green"))

    assert len(found) == 1
    assert found[0]["id"] == tea_id

    updated = asyncio.run(update_memory(tea_id, content="I like oolong"))

    assert updated is True

    refreshed = asyncio.run(get_memories(category="food"))

    assert refreshed[0]["content"] == "I like oolong"

    assert asyncio.run(update_memory(tea_id)) is False

    assert asyncio.run(update_memory(9999, content="x")) is False

    assert asyncio.run(delete_memory(math_id)) is True

    assert asyncio.run(delete_memory(math_id)) is False


def test_add_memory_dedup_flags_normalized_duplicate(temp_db):
    first = asyncio.run(
        add_memory_dedup("I love pizza with extra cheese")
    )

    assert first["duplicate"] is False

    duplicate = asyncio.run(
        add_memory_dedup("I  love pizza with extra cheese ")
    )

    assert duplicate["duplicate"] is True
    assert duplicate["existing"]["id"] == first["id"]

    distinct = asyncio.run(add_memory_dedup("I love sushi"))

    assert distinct["duplicate"] is False
    assert distinct["id"] != first["id"]


def test_session_message_flow_and_limits(temp_db):
    session_id = asyncio.run(create_session())

    session = asyncio.run(get_session(session_id))

    assert session is not None
    assert session["closed_at"] is None

    for role, text in (
        ("user", "one"),
        ("assistant", "two"),
        ("user", "three"),
        ("assistant", "four"),
    ):
        asyncio.run(save_message(session_id, role, "ollama", text))

    last_two = asyncio.run(get_messages(session_id, limit=2))

    assert [message["content"] for message in last_two] == [
        "three",
        "four",
    ]

    assert [message["role"] for message in last_two] == [
        "user",
        "assistant",
    ]

    sessions = asyncio.run(list_sessions())

    assert sessions[0]["id"] == session_id
    assert sessions[0]["last_message"] == "four"

    assert asyncio.run(close_session(session_id)) is True

    assert asyncio.run(close_session(session_id)) is False

    closed = asyncio.run(get_session(session_id))

    assert closed["closed_at"] is not None


def test_find_relevant_memories_ranks_by_overlap(temp_db):
    asyncio.run(add_memory("My mathematics exam is on Friday"))
    asyncio.run(add_memory("I prefer green tea in the morning"))

    relevant = asyncio.run(
        find_relevant_memories("When is my mathematics exam?")
    )

    assert len(relevant) == 1
    assert "mathematics" in relevant[0]["content"]

    tea = asyncio.run(find_relevant_memories("green tea"))

    assert len(tea) == 1
    assert "green tea" in tea[0]["content"]

    assert asyncio.run(find_relevant_memories("Is it?")) == []


def test_memory_context_block_formatting(temp_db):
    assert memory_context_block([]) == ""

    block = memory_context_block([
        {"category": "school", "content": "Exam on Friday"},
    ])

    assert block.startswith("Known facts about the user")

    assert "- [school] Exam on Friday" in block
