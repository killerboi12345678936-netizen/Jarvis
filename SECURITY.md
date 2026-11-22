# Security Policy

## Supported versions

Only the latest commit on `v2-development` receives security fixes.

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's
"Report a vulnerability" (Security tab → Security advisories) so the
report stays private until a fix is available. Include:

- What data is at risk (credentials, personal messages, files).
- Steps or a proof of concept.
- Affected component (`backend/...`, `frontend/web/src/...`).

## Security design of Jarvis

- **Device pairing.** While `JARVIS_DEVICE_AUTH=1` (default), every HTTP
  and WebSocket request must present the shared device token generated
  on first start (`data/device_token.txt`). WebSockets are closed with
  code 4401 when the token is missing or wrong.
- **Read-only Telegram.** The Telegram integration only reads. There is
  no code path that sends, replies, joins, or modifies anything.
- **Approval-gated actions.** Tools that touch user data (files,
  calendar events, desktop apps) never execute on the model's word
  alone; they become pending actions that you approve.
- **File containment.** Workspace tools accept only simple filenames and
  resolve-check the final path against the workspace directory.
- **Parameterized SQL** everywhere; no string-built queries.
- **Secrets isolation.** All credentials come from `.env`, which is
  gitignored. `.env.example` contains placeholders only.

## Handling your own credentials

- The Telegram session string equals full account access. Keep `.env`
  private; never paste it in issues, logs, or screenshots.
- `data/device_token.txt`, `data/certs/dev.key`, and `data/jarvis.db`
  contain installation-private data and are gitignored.
- If you expose Jarvis beyond your LAN by mistake, rotate: delete
  `data/device_token.txt` (restart regenerates it), and re-run
  `scripts/telegram_login.py` to replace the session string.

## Scope

Jarvis is designed for a personal machine and your LAN. It is not
hardened for hostile multi-tenant exposure; do not port-forward it.
