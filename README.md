# Jarvis

Local-first personal AI assistant with a web interface, real-time voice,
tools, memory, and read-only integrations. Runs entirely on your machine;
cloud providers are optional.

- **Backend**: Python 3.10+, FastAPI, SQLite (aiosqlite), WebSocket + SSE
- **Frontend**: React 19 + TypeScript + Vite (installable PWA, mobile-friendly)
- **Voice**: faster-whisper (speech to text) and Piper (text to speech), server-side VAD with barge-in
- **CLI**: the original v0.1 terminal app (`main.py`) still works unchanged

## What Jarvis can do

| Area | Capability |
| --- | --- |
| Chat | Streaming responses (SSE), multi-provider (Ollama, Gemini, NVIDIA), conversation sessions with history |
| Voice | Live WebSocket voice mode: VAD utterance detection, streamed transcription, sentence-by-sentence TTS, barge-in interruption, continuous conversation, tunable thresholds |
| Tools | Model-emitted tool calls executed safely in rounds: time, notes, memory, desktop apps, system info, calendar, Telegram digests and study plans |
| Memory | Saved facts with categories, fuzzy dedup, token-overlap retrieval injected into the system prompt |
| Permissions | Approval-required tools create pending actions; nothing consequential runs until you approve it (inline action card or Actions panel) |
| Telegram | Read-only study group reading (Mathematics/Physics/Chemistry), classified digests (announcements, assignments, tests, lecture recordings, deadlines) and study-plan workflows. Jarvis never sends messages |
| Calendar | ICS import (URL or file, with recurrence expansion) + local events; free-slot finding and calendar-aware study plans |
| Desktop | Allowlisted app launching and system info, gated by the approval flow |
| Access | Device-token pairing for LAN/phone use, self-signed TLS dev certificates, PWA install on Android |

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
  parses them out of streamed text and salvages the malformed variants small
  models emit (single brackets, stray braces, Python-style literals,
  `arguments: none`). Unparseable markup is never shown to the user.
- `backend/tools/service.py` runs automatic tools immediately, feeds results
  back to the model for a natural-language answer, and proposes
  approval-required tools into the `tool_actions` table.
- Study-group requests are routed deterministically to the Telegram digest
  and planning workflow (`backend/integrations/telegram/report.py`), so a
  small model cannot fail to pick the right tool.
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
6. Install frontend dependencies:
   ```
   cd frontend/web
   npm install
   ```
7. Start the backend and frontend:
   - Backend: `.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000`
   - Frontend dev server: `npm run dev` (https://localhost:5173)
   - Or run both with `start_jarvis.bat` from the project root.
8. Optional voice: the Piper voice model is not stored in this
   repository — download it as described in "Voice setup" below.
   faster-whisper downloads its own model on first use (or set
   `WHISPER_MODEL`).

### Phone / LAN access (optional)

1. Generate development TLS certificates:
   `python scripts/make_dev_cert.py` (writes `data/certs/`; install the
   generated `dev.crt` as a trusted CA on your phone).
2. Find your machine's LAN address: `python scripts/lan_ip.py`.
3. Open `https://<your-lan-ip>:5173` on the phone and pair.

### Device pairing

The first browser to connect asks for the device token from
`data/device_token.txt` (regenerate it by deleting that file and restarting
the backend). All API and WebSocket endpoints require this token while
`JARVIS_DEVICE_AUTH=1` (the default). It is a shared secret for *your*
devices only — do not publish it.

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
| `JARVIS_DEVICE_AUTH` | `1` (default) require the device token on every request |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION` | Telegram auth (read-only; run `python scripts/telegram_login.py` to create a session string) |
| `TELEGRAM_GROUP_MATH`, `TELEGRAM_GROUP_PHYSICS`, `TELEGRAM_GROUP_CHEMISTRY` | Group usernames or numeric IDs per subject |
| `CALENDAR_ICS_URL`, `CALENDAR_ICS_FILE` | External calendar source |
| `MEMORY_CONTEXT_LIMIT` | Saved facts injected into the system prompt |

## Telegram setup (read-only)

1. Create an app at https://my.telegram.org to get an API ID and API hash.
2. Run `python scripts/telegram_login.py` and follow the prompts; it writes
   the session string directly into `.env` and never prints it.
3. Put each study group's username or numeric ID into
   `TELEGRAM_GROUP_MATH` / `TELEGRAM_GROUP_PHYSICS` / `TELEGRAM_GROUP_CHEMISTRY`.
4. Restart the backend.

Jarvis only calls read operations (`iter_messages`, `get_entity`,
`get_dialogs`); there is no send/reply/join path in the codebase. The
session string is a full account credential — keep `.env` private.

## Calendar setup

Point `CALENDAR_ICS_URL` at your calendar's private ICS address or
`CALENDAR_ICS_FILE` at a local `.ics` export. Events are merged with
locally created events. Calendar events are never modified automatically;
creating or deleting events is an approval-required tool.

## Voice setup

- Text to speech uses Piper; the default voice model
  (`en_US-lessac-medium`) is **not bundled with the repository**. Download
  both files into `data/voice/`:
  `en_US-lessac-medium.onnx` and `en_US-lessac-medium.onnx.json` from
  https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/lessac/medium
  (MIT licensed), or point `PIPER_MODEL` in `.env` at any other Piper
  `.onnx` voice. If the model is missing, TTS fails with a clear message
  describing exactly this; text chat and everything else keep working.
  `PIPER_EXECUTABLE` can point at a piper binary if you prefer not to use
  the Python package.
- Speech to text uses faster-whisper; the model downloads on first use
  (configurable via `WHISPER_MODEL`, `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE`).
- Live voice mode needs microphone permission; it works best in Chrome/Edge.

## API keys and privacy

API keys belong in `.env` only; never commit or share that file. When Gemini
or NVIDIA is selected, conversation content and retrieved memories are sent
to that provider — use Ollama for fully local inference. Telegram access is
read-only by design and the codebase contains no message-sending path.

## Security model

- Device pairing: every API and WebSocket request must present the device
  token; unpaired clients see a pairing gate.
- Approval flow: consequential tools (create/delete events, launch apps,
  create notes) become pending actions and execute only after you approve them.
- Desktop launching is restricted to the `DESKTOP_ALLOWED_APPS` allowlist.
- Workspace file tools accept only simple safe filenames and resolve-check
  against the workspace directory.
- All database access uses parameterized SQL; no secrets are hardcoded.
- TLS termination happens at the Vite dev server (self-signed dev certs);
  the FastAPI backend itself speaks plain HTTP. Started manually it binds
  to localhost; `start_jarvis.bat` binds it to `0.0.0.0` for LAN/phone
  use — every request still requires the device token, so only paired
  devices can reach it.
- The API is designed for your own LAN, not the public internet. Do not
  port-forward it.

## Testing

Backend: `.venv\Scripts\python.exe -m pytest tests/ -q` — covers the tool
parser and pipeline (including malformed model output and streaming),
intent routing, Telegram digest normalization, memory CRUD and retrieval,
permissions lifecycle, calendar integration, desktop tools, voice VAD
state machine, and device auth.

Frontend: `npm run test` in `frontend/web` covers the sentence
segmentation helper used for progressive TTS display.

## CLI (v0.1, unchanged)

`py main.py` starts the original terminal assistant.

Commands: `/help`, `/provider ollama|gemini|nvidia`, `/model MODEL_ID`,
`/remember TEXT`, `/facts`, `/forget ID`, `/history`, `/new`, `/exit`.

## Data

`data/jarvis.db` stores sessions, messages, memories, tool actions, and
local calendar events. `data/workspace/` holds assistant-created notes.
Voice models live under `data/voice/`. Keep these folders private; nothing
is uploaded anywhere except to the cloud provider you explicitly select.

## Licences

Jarvis is released under the Apache License 2.0 (see `LICENSE`).

Key dependencies and their licences, all installed via `pip`/`npm` into
your own environment:

| Dependency | Licence |
| --- | --- |
| Telethon | MIT |
| icalendar | BSD-2-Clause |
| recurring-ical-events | LGPL-3.0-or-later |
| faster-whisper | MIT |
| piper-tts | GPL-3.0-or-later |
| en_US-lessac-medium Piper voice | MIT (rhasspy/piper-voices) |

These are separate programs you install and run alongside Jarvis, so
their licences impose no extra obligations on Jarvis source releases.
If you distribute a bundled installer that ships piper-tts (GPL) or the
LGPL dependency inside it, that component's licence terms apply to that
distribution.

## Known limitations

- Small local models (e.g. qwen2.5:3b) sometimes misformat tool calls;
  the parser and corrective rounds handle the observed variants, and
  larger models behave better.
- Study plans are suggestions only: the planner works from actual
  Telegram messages and your calendar, but it never creates or modifies
  calendar events automatically.
- Telegram digests depend on the configured groups having recent messages.
- Voice mode requires microphone permission and works best in Chrome/Edge.
- The tool set is intentionally small and allowlisted; Jarvis is not a
  general agent with arbitrary shell access.
- Development certificates are self-signed; install `dev.crt` as a trusted
  CA on devices you use, or accept the browser warning.
