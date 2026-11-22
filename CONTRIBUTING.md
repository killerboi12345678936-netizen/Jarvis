# Contributing to Jarvis

Thanks for your interest in improving Jarvis. This project is a
local-first personal assistant; the guiding rules are below.

## Ground rules

1. **Telegram is read-only by design.** Jarvis must never send messages,
   reply, join groups, or modify anything on Telegram. Do not add write
   paths to the Telegram integration.
2. **Consequential actions need approval.** Anything that creates or
   modifies user data (files, calendar events, desktop apps) must go
   through the `approval_required` permission flow, never auto-execute.
3. **Secrets stay in `.env`.** Never hardcode or commit API keys, the
   Telegram session string, device tokens, or certificates.
4. **Local-first.** Features must work with Ollama alone; cloud
   providers are optional additions.

## Development setup

```
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
cd frontend\web && npm install
```

Start the backend and frontend as described in the README, or use
`start_jarvis.bat`.

## Running tests

Backend (all tests must pass):

```
.venv\Scripts\python.exe -m pytest tests/ -q
```

Frontend:

```
cd frontend\web
npm run test
npm run lint
npm run build
```

## Code style

- Python: 4 spaces, double quotes, no linter configured — match the
  surrounding style of the file you edit.
- TypeScript/React: `npm run lint` (oxlint) must pass.
- Keep changes focused: one feature or fix per pull request.
- Add or update tests for behavior you change. Parser, planner, and
  permissions changes in particular must come with regression tests.

## Where things live

| Path | Contents |
| --- | --- |
| `backend/api/routes/` | HTTP/SSE/WebSocket endpoints |
| `backend/tools/` | tool registry, stream parser, dispatcher, permissions |
| `backend/integrations/` | Telegram (read-only), calendar, planning |
| `backend/memory/` | SQLite schema and retrieval |
| `backend/voice/` | VAD, streaming STT, sentence TTS |
| `backend/providers/` | Ollama/Gemini/NVIDIA adapters |
| `frontend/web/src/` | React UI (App.tsx, components, lib) |
| `tests/` | pytest suites |
| `scripts/` | setup and helper scripts (login, certs, launcher) |

## Reporting issues

Include: what you asked Jarvis, the model/provider used, relevant
backend log output (redact tokens and personal data), and steps to
reproduce. Never paste your Telegram session string or device token
into an issue — treat them as passwords.
