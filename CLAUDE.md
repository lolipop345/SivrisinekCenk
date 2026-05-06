# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Discord bot ("SivrisinekCenk") that talks to a local OpenAI-compatible HTTP server (LM Studio "Start Server", `llama-server`, vLLM, Ollama, etc.) via the `openai` Python SDK's `AsyncOpenAI` client. The bot replies in Turkish and the system prompt in `prompts/persona.txt` is intentionally Turkish — preserve language when editing.

## Layout

```
bot.py            # Discord client + slash commands + event handlers (entry point)
config.py         # .env loading; exports DISCORD_TOKEN, OPENAI_*, SYSTEM_PROMPT, session/history limits, GUILD_ID
llm_client.py     # AsyncOpenAI wrapper; LLMClient.complete(messages) -> str
session_store.py  # Per-channel sliding session with asyncio.Lock; SessionStore + Session
prompts/
  persona.txt     # System prompt — edit this to change the bot's persona, no code change needed
.env.example      # Copy to `.env` and fill in DISCORD_TOKEN (and optionally GUILD_ID)
requirements.txt  # discord.py, python-dotenv, openai
```

## Run

```bash
pip install -r requirements.txt
cp .env.example .env  # then edit DISCORD_TOKEN
./start.sh           # orchestrated: starts SpoofDPI if missing, then runs bot
# or just: python bot.py   (if you've already started SpoofDPI / don't need it)
```

`start.sh` handles the local orchestration that's painful to remember:
- If `:8080` is free, launches SpoofDPI with `-window-size 1` (the aggressive Client Hello fragmentation needed so aiohttp's TLS handshake bypasses Turkish-style SNI-DPI on `discord.com`). If something is already on `:8080`, reuses it.
- Then runs `python bot.py` in the foreground. On Ctrl+C the trap kills any SpoofDPI it started.
- `SPOOFDPI_BIN` and `SPOOFDPI_PORT` env vars override defaults.

**Note:** `start.sh` does **not** start the LLM server (llama-server / LM Studio). You start that yourself; the bot's preflight check below tells you if it's missing.

## Preflight check

`bot.py` runs `_preflight()` synchronously at import time, before connecting to Discord:

1. `GET <OPENAI_BASE_URL>/models` — must return a model list. If the LLM server is unreachable, the bot exits with a clear hint to start it.
2. `OPENAI_MODEL` is checked against the served list — a mismatch is a warning (single-model servers like `llama-server` ignore the request `model` field, so the bot still works).
3. `GET https://discord.com/api/v10/gateway` — directly if `DISCORD_PROXY` is empty, through the proxy if set. If this fails and `DISCORD_PROXY` is empty on a DPI-restricted network (TR), the bot exits telling you to set `DISCORD_PROXY=http://127.0.0.1:8080` and run SpoofDPI. If it fails *with* a proxy, the bot exits telling you SpoofDPI's `-window-size 1` flag is probably wrong/missing.

This avoids the "bot logs in, then silently hangs" failure mode that can take 30 minutes to diagnose.

`config.py` reads `.env` once at import time. `DISCORD_TOKEN` is required and the process will fail-fast with `KeyError` if missing. Other keys (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `SESSION_TTL_SECONDS`, `HISTORY_MAX_MESSAGES`, `GUILD_ID`) have defaults but can be overridden in `.env`.

## External runtime dependencies

The bot does **not** start the LLM server. An OpenAI-compatible HTTP server must already be listening at `OPENAI_BASE_URL` (default `http://localhost:8000/v1`). Examples that satisfy the contract: LM Studio's "Start Server" button, `llama.cpp`'s `llama-server`, vLLM, Ollama (with its OpenAI-compat shim).

`OPENAI_API_KEY` defaults to `"not-needed"` because most local servers ignore auth, but the SDK rejects an empty string — keep some non-empty value.

`OPENAI_MODEL` must match a model identifier the server actually serves. Switching models is an `.env` change, not a Python change.

## Network egress

If `discord.com` is unreachable on the local network (e.g., SNI-based DPI block in TR — TLS Client Hello triggers a connection RST), set `DISCORD_PROXY` to an HTTP proxy that fragments the Client Hello so the censor can't read the SNI. The typical local fix is **SpoofDPI** running at `http://127.0.0.1:8080`. The value is passed to `discord.Client(proxy=...)` via `commands.Bot` and applies to both Discord REST and gateway WSS. Leave empty in environments where `discord.com` is directly reachable. The OpenAI/local LLM client is unaffected — it talks to `localhost` and never goes through this proxy.

## Conversation memory

State lives in `session_store.py` and is in-memory only (lost on restart).

- **Scope:** Per Discord channel (DM included; keyed by `message.channel.id`). Anyone in the channel contributes to the same session.
- **Lifetime:** Sliding inactivity window — `SESSION_TTL_SECONDS` (default 7200 = 2 hours). Each new message resets the timer. Expiry is lazy: checked on the next `get_or_create`.
- **Content:** Every message in the channel is appended to history with a `"<display_name>: <content>"` prefix on the user side, so the model can attribute who said what. The bot's own replies are appended with `role: "assistant"`.
- **Cap:** `HISTORY_MAX_MESSAGES` (default 100). The `system` message at index 0 is preserved; oldest user/assistant messages are FIFO-trimmed beyond the cap.
- **Reset:** `/clear` slash command (see below) wipes the session for the current channel.
- **Locking:** Each `Session` has its own `asyncio.Lock`. `bot.py` holds it only across list mutations (append, snapshot) — never across the LLM call, so a slow completion does not block the channel.
- **Multi-modal:** Image attachments (MIME `image/*`) are downloaded by the bot itself (via `discord.Attachment.read()`, which goes through `bot.http`'s session and therefore through `DISCORD_PROXY` if set) and **base64-encoded** into the LLM payload as `{"type": "image_url", "image_url": {"url": "data:<mime>;base64,..."}}` data-URL parts via `_build_user_content`. The LLM server therefore never makes its own outbound HTTP request — important when the server (e.g. `llama-server`) runs without proxy support and Discord CDN is firewalled. History stores only a text-only line `<display_name>: <content> [resim: <filename>]` (no URL, no base64) via `_format_for_history`; visual context is carried forward by the bot's own text replies.

## Slash commands

- `/clear` — Resets the session for the channel it was invoked in. Replies ephemerally.

Slash commands are synced once in `bot.setup_hook` (called by discord.py before `on_ready`, only once per process).

- If `GUILD_ID` is set in `.env`, sync is guild-scoped — propagation is near-instant. Use this for development.
- If `GUILD_ID` is empty, sync is global — propagation can take up to ~1 hour the first time. Use this for production.

## Trigger logic

`_should_respond` in `bot.py` decides whether the bot calls the LLM. Three conditions trigger a reply: it is `@`-mentioned, its username appears (case-insensitive) anywhere in the message, or the message is a reply to one of its own messages.

**Important:** Even when the bot does not respond, every channel message is still appended to that channel's session history. Future replies see what others said.
