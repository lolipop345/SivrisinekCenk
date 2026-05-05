# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Discord bot ("SivrisinekCenk") that proxies messages to a local LLM via the LM Studio CLI. The bot replies in Turkish and the system prompt in `prompts/persona.txt` is intentionally Turkish — preserve language when editing.

## Layout

```
bot.py           # Discord client + event handlers (entry point)
config.py        # .env loading; exports DISCORD_TOKEN, LMS_PATH, MODEL_NAME, SYSTEM_PROMPT
lms_client.py    # subprocess wrapper around `lms chat`; single public fn `chat(user_input)`
prompts/
  persona.txt    # System prompt — edit this to change the bot's persona, no code change needed
.env.example     # Copy to `.env` and fill in DISCORD_TOKEN
requirements.txt # discord.py, python-dotenv
```

## Run

```bash
pip install -r requirements.txt
cp .env.example .env  # then edit DISCORD_TOKEN
python bot.py
```

`config.py` reads `.env` once at import time. `DISCORD_TOKEN` is required and the process will fail-fast with `KeyError` if missing. `LMS_PATH` and `LMS_MODEL` have defaults but can be overridden in `.env`.

## External runtime dependencies

The bot does **not** call an LLM library directly. It shells out to LM Studio's `lms` CLI for every incoming message (see `lms_client.py:chat`). Two things must be in place outside the repo:

1. `lms` must be installed. Default path is `/usr/local/bin/lms`; override via `LMS_PATH` in `.env` if `which lms` differs (e.g. `/opt/homebrew/bin/lms` on Apple Silicon Homebrew).
2. The model in `LMS_MODEL` must already be available to LM Studio. Changing models means editing `.env`, not Python.

Each Discord message spawns a fresh `subprocess.run([lms, "chat", ...])`; there is no persistent session or conversation memory across messages.

## Trigger logic

The bot only responds when `_should_respond` in `bot.py` returns true. The three conditions: it is `@`-mentioned, its username appears (case-insensitive) in the message, or the message is a reply to one of its own messages. Plain channel chatter is ignored.
