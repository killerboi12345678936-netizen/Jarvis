
from config import settings
from database import (
    create_session, get_latest_session, get_messages,
    save_message, add_memory, get_memories, get_memory_details,
    delete_memory, close_session, init_db, MEMORY_CATEGORIES
)
from providers import ask_ai, ProviderError


HELP = """
Commands:
  /help                       Show commands
  /provider NAME              ollama, gemini, nvidia
  /model MODEL_ID              Change current model
  /remember CATEGORY | TEXT   Save a categorized memory
  /facts                      List all memories
  /facts CATEGORY             List memories in a category
  /forget ID                  Delete a memory
  /approve                    Approve suggested memory
  /reject                     Reject suggested memory
  /history                    Show recent conversation
  /new                        Start new conversation
  /exit                       Quit

Categories:
  project, skill, preference, interest, general
"""


def suggest_memory(user_text):
    import re

    text = user_text.strip()

    if not text or len(text) > 200 or len(text.split()) > 30:
        return None

    patterns = (
        r"^i am\b",
        r"^i['’]m\b",
        r"^i prefer\b",
        r"^i like\b",
        r"^i love\b",
        r"^i enjoy\b",
        r"^my preferred\b",
        r"^my favorite\b",
    )

    if not any(re.match(p, text, re.IGNORECASE) for p in patterns):
        return None

    sensitive_terms = (
        "password", "passcode", "api key", "secret key",
        "home address", "phone number", "credit card",
        "medical diagnosis", "bank account"
    )

    if any(term in text.lower() for term in sensitive_terms):
        return None

    return text


def main():
    init_db()

    provider = settings.default_provider
    models = dict(settings.models)
    session_id = get_latest_session() or create_session()
    pending_memory = None

    print("\nJARVIS v0.3 — categorized memory")
    print(f"Provider: {provider}")
    print("Type /help for commands.\n")

    while True:
        try:
            text = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nJarvis > Goodbye.")
            close_session(session_id)
            break

        if not text:
            continue

        # COMMAND HANDLING
        if text.startswith("/"):
            cmd, _, arg = text.partition(" ")
            cmd = cmd.lower()
            arg = arg.strip()

            if cmd == "/help":
                print(HELP)

            elif cmd == "/provider":
                if arg.lower() in ("ollama", "gemini", "nvidia"):
                    provider = arg.lower()
                    print(f"Jarvis > Provider set to {provider}.")
                else:
                    print("Choose ollama, gemini, or nvidia.")

            elif cmd == "/model":
                if arg:
                    models[provider] = arg
                print(f"Jarvis > {provider} model: {models[provider]}")

            elif cmd == "/remember":
                if "|" not in arg:
                    print("Usage: /remember category | memory")
                else:
                    category, content = arg.split("|", 1)
                    category = category.strip().lower()
                    content = content.strip()

                    if category not in MEMORY_CATEGORIES:
                        print(
                            "Jarvis > Invalid category. Choose: "
                            + ", ".join(sorted(MEMORY_CATEGORIES))
                        )
                    elif not content:
                        print("Jarvis > Memory cannot be empty.")
                    else:
                        mid = add_memory(content, category)

                        if mid is None:
                            print("Jarvis > That memory already exists.")
                        else:
                            print(
                                f"Jarvis > Saved {category} "
                                f"memory with ID {mid}."
                            )

            elif cmd == "/facts":
                category = arg.lower() if arg else None

                if category and category not in MEMORY_CATEGORIES:
                    print("Jarvis > Invalid category.")
                else:
                    facts = get_memory_details(category)

                    for fact in facts:
                        print(
                            f"[{fact['id']}] "
                            f"[{fact['category']}] "
                            f"{fact['content']}"
                        )

                    if not facts:
                        print("Jarvis > No saved facts found.")

            elif cmd == "/forget":
                if arg.isdigit() and delete_memory(int(arg)):
                    print("Jarvis > Memory deleted.")
                else:
                    print("Jarvis > Memory ID not found.")

            elif cmd == "/approve":
                if pending_memory:
                    mid = add_memory(pending_memory, "general")

                    if mid is None:
                        print("Jarvis > That memory already exists.")
                    else:
                        print(f"Jarvis > Memory saved with ID {mid}.")

                    pending_memory = None
                else:
                    print("Jarvis > No pending memory.")

            elif cmd == "/reject":
                if pending_memory:
                    pending_memory = None
                    print("Jarvis > Memory suggestion rejected.")
                else:
                    print("Jarvis > No pending memory.")

            elif cmd == "/history":
                for m in get_messages(session_id, 20):
                    print(f"{m['role']} > {m['content']}")

            elif cmd == "/new":
                close_session(session_id)
                session_id = create_session()
                pending_memory = None
                print("Jarvis > New conversation started.")

            elif cmd in ("/exit", "/quit"):
                close_session(session_id)
                print("Jarvis > Goodbye.")
                break

            else:
                print("Jarvis > Unknown command. Type /help.")

            continue

        # NORMAL AI CONVERSATION
        save_message(session_id, "user", provider, text)

        history = get_messages(session_id, settings.history_limit)

        facts = "\n".join(
            f"- [{category}] {content}"
            for _, content, _, category in get_memory_details()
        )

        system = settings.system_prompt

        if facts:
            system += "\n\nUser-approved saved facts:\n" + facts

        messages = [{"role": "system", "content": system}]

        messages.extend(
            {"role": m["role"], "content": m["content"]}
            for m in history
        )

        print("Jarvis > ", end="", flush=True)

        try:
            answer = ask_ai(provider, models[provider], messages)
            print(answer)

            save_message(session_id, "assistant", provider, answer)

            # Suggest memory using only the user's message.
            pending_memory = None
            suggestion = suggest_memory(text)

            if suggestion:
                pending_memory = suggestion
                print(
                    "\nJarvis [Memory suggestion] > "
                    + suggestion
                )
                print("Type /approve to save or /reject to discard.")

        except ProviderError as e:
            print(f"\nProvider error: {e}")


if __name__ == "__main__":
    main()
