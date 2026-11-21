
from backend.memory.database import get_memories
from backend.memory.textutils import tokenize


async def find_relevant_memories(
    query,
    limit=6,
    candidate_limit=200,
    min_score=0.2,
):
    memories = await get_memories(limit=candidate_limit)

    if not memories:
        return []

    query_tokens = tokenize(query)

    if not query_tokens:
        return []

    scored = []

    for memory in memories:
        memory_tokens = tokenize(memory["content"])

        overlap = len(query_tokens & memory_tokens)

        if not overlap:
            continue

        coverage = overlap / len(query_tokens)

        if coverage >= min_score:
            scored.append((coverage, memory["id"], memory))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)

    return [memory for _, _, memory in scored[:limit]]


def memory_context_block(memories):
    if not memories:
        return ""

    lines = [
        f"- [{memory['category']}] {memory['content']}"
        for memory in memories
    ]

    return (
        "Known facts about the user. Use them for context when "
        "relevant; do not recite them unless it helps the answer:\n"
        + "\n".join(lines)
    )
