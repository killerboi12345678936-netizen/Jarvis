# Jarvis v1.0

Local-first personal AI assistant with a web interface, real-time voice,
tools, memory, and read-only integrations. Runs entirely on your machine;
cloud providers are optional.

- **Backend**: Python 3.10+, FastAPI, SQLite (aiosqlite), WebSocket + SSE
- **Frontend**: React 19 + TypeScript + Vite
- **Voice**: faster-whisper (speech to text) and Piper (text to speech), server-side VAD with barge-in
- **CLI**: the original v0.1 terminal app (`main.py`) still works unchanged

## What Jarvis can do

| Area | Capability |
| --- | --- |
| Chat | Streaming responses (SSE), multi-provider (Ollama, Gemini, NVIDIA), conversation sessions with history |
| Voice | Live WebSocket voice mode: VAD utterance detection, streamed transcription, sentence-by-sentence TTS, barge-in interruption, continuous conversation, tunable thresholds |
| Tools | Model-emitted tool calls executed safely in rounds: time, notes, memory, desktop apps, system info, calendar |
| Memory | Saved facts with categories, fuzzy dedup, token-overlap retrieval injected into the system prompt |
| Permissions | Approval-required tools create pending actions; nothing consequential runs until you approve it in the Actions panel |
| Telegram | Read-only study group reading (Mathematics/Physics/Chemistry), classified digests, study plans. Jarvis never sends messages |
| Calendar | ICS import (URL or file, with recurrence expansion) + local events; free-slot finding and calendar-aware study plans |
| Desktop | Allowlisted app launching and system info, gated by the approval flow |

## Architecture

```
frontend/web (React)  ──SSE──►  FastAPI (backend/main.py)
        │                            │
        └──WebSocket──► /api/voice/ws│
                                     ├─ providers/manager (Ollama/Gemini/NVIDIA)
                                     ├─ memory/ (SQLite: sessions, messages, memories)
                                     ├─ tools/ (registry, parser, permissions, service)
                                     ├─ integrations/ (telegram, calendar, planning)
                                     └─ voice/ (stream VAD, whisper STT, Piper TTS)
```

- Tool calls are `<<TOOL:{...}>>` markers in model output; `backend/tools/parser.py`
  strips them from streamed text (tolerating malformed variants small models emit).
- `backend/tools/service.py` runs automatic tools immediately and proposes
  approval-required tools into the `tool_actions` table.
- Voice pipeline: client streams PCM16 @16 kHz; the server VAD detects
  utterances, transcribes, streams the answer, and synthesizes sentences
  while listening for barge-in.

## Setup (Windows)

1. Install Python 3.10+, Node.js 18+, and Ollama.
2. Create and activate a virtual environment:
   `py -m venv .venv` then `.venv\Scripts\Activate.ps1`
3. Install backend dependencies:
   `py -m pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill in what you use
   (Ollama needs nothing; cloud providers need API keys).
5. Pull the default model:
   `ollama pull qwen2.5:3b`
6. Install frontend dependencies and start both servers:
   ```
   cd frontend/web
   npm install
   ```
   Backend: `.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000`
   Frontend dev server: `npm run dev` (http://localhost:5173)
7. Optional voice models: place a Piper voice at `data/voice/en_US-lessac-medium.onnx`
   and let faster-whisper download its model on first use (or set `WHISPER_MODEL`).

### Frontend production build

```
cd frontend/web
npm run build
npm run test
```

## Configuration (.env)

All settings are optional; defaults are in `.env.example`.

| Variable | Purpose |
| --- | --- |
| `DEFAULT_PROVIDER`, `OLLAMA_URL`, `OLLAMA_MODEL`, `DOLPHIN_MODEL` | Local model provider |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Google Gemini adapter |
| `NVIDIA_API_KEY`, `NVIDIA_BASE_URL`, `NVIDIA_MODEL` | NVIDIA API adapter |
| `HISTORY_LIMIT` | Messages of history sent per request |
| `WHISPER_MODEL`, `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE`, `WHISPER_PRELOAD` | Speech to text |
| `PIPER_EXECUTABLE`, `PIPER_MODEL` | Text to speech |
| `VOICE_SAMPLE_RATE`, `VAD_SPEECH_THRESHOLD`, `VAD_SILENCE_MS`, `VAD_MIN_SPEECH_MS`, `VAD_BARGE_IN_THRESHOLD` | Voice streaming tuning |
| `TOOLS_ENABLED`, `TOOL_MAX_ROUNDS` | Tool calling |
| `DESKTOP_ALLOWED_APPS` | `name=executable` pairs the desktop tool may launch |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION` | Telegram auth (read-only; run `python scripts/telegram_login.py` to create a session string) |
| `TELEGRAM_GROUP_MATH`, `TELEGRAM_GROUP_PHYSICS`, `TELEGRAM_GROUP_CHEMISTRY` | Group usernames/ids per subject |
| `CALENDAR_ICS_URL`, `CALENDAR_ICS_FILE` | External calendar source |
| `MEMORY_CONTEXT_LIMIT` | Saved facts injected into the system prompt |

## API keys and privacy

API keys belong in `.env` only; never commit or share that file. When Gemini
or NVIDIA is selected, conversation content and retrieved memories are sent
to that provider — use Ollama for fully local inference. Telegram access is
read-only by design and the codebase contains no message-sending path.

## Security model

- Approval flow: consequential tools (create/delete events, launch apps)
  become pending actions and execute only after you approve them.
- Desktop launching is restricted to the `DESKTOP_ALLOWED_APPS` allowlist.
- Workspace file tools accept only simple safe filenames and resolve-check
  against the workspace directory.
- All database access uses parameterized SQL; CORS is restricted to the
  Vite dev origin; no secrets are hardcoded.
- The API has no authentication — it is designed for localhost use only.
  Do not expose port 8000 to a network.

## Testing

Backend (52 tests): `.venv\Scripts\python.exe -m pytest tests/ -q`
covers the tool parser (including split-marker streaming), memory CRUD and
retrieval, permissions lifecycle, calendar integration, desktop tools,
voice VAD state machine, and Telegram digest formatting.

Frontend (7 tests): `npm run test` in `frontend/web` covers the sentence
segmentation helper used for progressive TTS display.

## CLI (v0.1, unchanged)

`py main.py` starts the original terminal assistant.

Commands: `/help`, `/provider ollama|gemini|nvidia`, `/model MODEL_ID`,
`/remember TEXT`, `/facts`, `/forget ID`, `/history`, `/new`, `/exit`.

## Data

`data/jarvis.db` stores sessions, messages, memories, tool actions, and
local calendar events. `data/workspace/` holds assistant-created notes.
Voice models live under `data/voice/`. Keep this folder private; nothing
is uploaded anywhere except to the cloud provider you explicitly select.

## Known limitations

- Small local models (e.g. qwen2.5:3b) sometimes misformat tool calls or
  produce placeholder text in study plans; larger models behave better.
- Voice mode requires microphone permission and works best in Chrome/Edge.
- Telegram digests depend on the configured groups having recent messages.
- The web API has no authentication layer (localhost-only by design).
