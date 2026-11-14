
from config import settings
from database import (
    create_session, get_latest_session, get_messages,
    save_message, add_memory, get_memories,
    delete_memory, close_session
)
from providers import ask_ai, ProviderError

HELP = """
Commands:
  /help                 Show commands
  /provider NAME        ollama, gemini, nvidia
  /model MODEL_ID       Change current model
  /remember TEXT        Save a fact manually
  /facts                List saved facts
  /forget ID            Delete a fact
  /approve              Save suggested memory
  /reject               Reject suggested memory
  /history              Show recent conversation
  /new                  Start new conversation
  /exit                 Quit
"""


def suggest_memory(user_text):
    import re

    text = user_text.strip()

    if not text or len(text) > 200 or len(text.split()) > 30:
        return None

    # Only accept clear statements about the user.
    patterns = (
        r"^i am\b",
        r"^i['’]m\b",
        r"^i prefer\b",
        r"^i like\b",
        r"^i love\b",
        r"^i enjoy\b",
        r"^i['’]m learning\b",
        r"^i['’]m building\b",
        r"^my preferred\b",
        r"^my favorite\b",
    )

    if not any(re.match(pattern, text, re.IGNORECASE) for pattern in patterns):
        return None

    # Never save messages that appear to contain sensitive information.
    sensitive_terms = (
        "password", "passcode", "api key", "secret key",
        "home address", "phone number", "credit card",
        "medical diagnosis", "bank account"
    )

    if any(term in text.lower() for term in sensitive_terms):
        return None

    return text


def main():
    provider = settings.default_provider
    models = dict(settings.models)
    session_id = get_latest_session() or create_session()
    pending_memory = None

    print("\nJARVIS v0.2 — intelligent memory")
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

        if text.startswith("/"):
            cmd, _, arg = text.partition(" ")
            cmd, arg = cmd.lower(), arg.strip()

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
                if arg:
                    print(f"Jarvis > Saved memory ID {add_memory(arg)}.")
                else:
                    print("Usage: /remember text")

            elif cmd == "/facts":
                facts = get_memories()
                for i, content, created in facts:
                    print(f"[{i}] {content}")
                if not facts:
                    print("Jarvis > No saved facts.")

            elif cmd == "/forget":
                if arg.isdigit() and delete_memory(int(arg)):
                    print("Jarvis > Memory deleted.")
                else:
                    print("Jarvis > Memory ID not found.")

            elif cmd == "/approve":
                if pending_memory:
                    mid = add_memory(pending_memory)
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

        save_message(session_id, "user", provider, text)
        history = get_messages(session_id, settings.history_limit)

        facts = "\n".join(
            f"- {content}" for _, content, _ in get_memories()
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
                    f"{suggestion}"
                )
                print(
                    "Type /approve to save or /reject to discard."
                )

        except ProviderError as e:
            print(f"\nProvider error: {e}")


if __name__ == "__main__":
    main()
