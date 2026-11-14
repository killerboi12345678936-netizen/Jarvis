# Jarvis v0.1

Local-first terminal assistant for Windows, macOS, and Linux.

## Features
- Ollama local model provider (Qwen 2.5 3B default; Dolphin 3 8B selectable)
- Gemini and NVIDIA API provider adapters
- Provider/model switching
- SQLite conversation history and explicit saved facts
- No distributed phone/tablet inference, voice, autonomous agents, or desktop control in v0.1

## Windows setup
1. Install Python 3.10+ and Ollama.
2. Open PowerShell in this extracted folder.
3. Create a virtual environment:
   `py -m venv .venv`
4. Activate it:
   `.venv\\Scripts\\Activate.ps1`
   If PowerShell blocks activation, use Command Prompt and run:
   `.venv\\Scripts\\activate.bat`
5. Install dependencies:
   `py -m pip install -r requirements.txt`
6. Copy `.env.example` to `.env` (File Explorer: copy, paste, rename the copy to `.env`).
7. Pull the default model:
   `ollama pull qwen2.5:3b`
8. Start Jarvis:
   `py main.py`

## Dolphin
Dolphin is included as a selectable Ollama model, not a separate app. Its exact tag can vary by Ollama library entry. Check the Ollama model library before pulling; the example configuration uses `dolphin3:8b`.
After verifying the tag, pull it with `ollama pull dolphin3:8b`, then in Jarvis run:
`/model dolphin3:8b`
To make Dolphin the default, set `OLLAMA_MODEL=dolphin3:8b` in `.env`.
Dolphin is less restrictive in alignment, but no model is guaranteed to comply with every request. Check laptop RAM before using larger variants.

## Commands
`/help`, `/provider ollama|gemini|nvidia`, `/model MODEL_ID`, `/remember TEXT`, `/facts`, `/forget ID`, `/history`, `/new`, `/exit`.

## API keys
Cloud API keys belong in `.env` only. Never commit or share that file. When Gemini or NVIDIA is selected, conversation content and saved facts included in the prompt are sent to that provider. Use Ollama for on-device inference.

## Data
`jarvis.db` is created in this folder and stores conversation history and saved facts. Keep this folder private.
