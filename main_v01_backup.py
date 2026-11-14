from config import settings
from database import create_session, get_latest_session, get_messages, save_message, add_memory, get_memories, delete_memory, close_session
from providers import ask_ai, ProviderError

HELP = """
Commands:
  /help                 Show commands
  /provider NAME        ollama, gemini, nvidia
  /model MODEL_ID       Change the current provider's model
  /remember TEXT        Save a fact to shared memory
  /facts                List saved facts
  /forget ID            Delete a saved fact
  /history              Show recent conversation
  /new                  Start a new conversation
  /exit                 Quit
"""

def main():
    provider = settings.default_provider
    models = dict(settings.models)
    session_id = get_latest_session() or create_session()
    print("\\nJARVIS v0.1 — local-first terminal assistant")
    print(f"Provider: {provider} | Local models: Qwen + Dolphin (Ollama)")
    print("Type /help for commands.\\n")

    while True:
        try:
            text = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\\nJarvis > Goodbye.")
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
                    print("Jarvis > Choose ollama, gemini, or nvidia.")
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
                print("\\n".join(f"[{i}] {v}" for i, v, _ in facts) or "Jarvis > No saved facts.")
            elif cmd == "/forget":
                print("Jarvis > Memory deleted." if arg.isdigit() and delete_memory(int(arg)) else "Jarvis > Memory ID not found.")
            elif cmd == "/history":
                for m in get_messages(session_id, 20):
                    print(f"{m['role']} > {m['content']}")
            elif cmd == "/new":
                close_session(session_id)
                session_id = create_session()
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
        facts = "\\n".join(f"- {content}" for _, content, _ in get_memories())
        system = settings.system_prompt + (f"\\n\\nUser-approved saved facts:\\n{facts}" if facts else "")
        messages = [{"role": "system", "content": system}]
        messages.extend({"role": m["role"], "content": m["content"]} for m in history)
        print("Jarvis > ", end="", flush=True)
        try:
            answer = ask_ai(provider, models[provider], messages)
            print(answer)
            save_message(session_id, "assistant", provider, answer)
        except ProviderError as e:
            print(f"\\nProvider error: {e}")

if __name__ == "__main__":
    main()
