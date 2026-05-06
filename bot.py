import base64
import json
import sys
import urllib.error
import urllib.request

import discord
from discord.ext import commands

import config
from llm_client import LLMClient
from session_store import SessionStore


def _preflight() -> None:
    base = config.OPENAI_BASE_URL.rstrip("/")
    try:
        with urllib.request.urlopen(base + "/models", timeout=5) as r:
            data = json.loads(r.read())
        ids = [m.get("id") for m in data.get("data", [])]
    except Exception as e:
        print(f"[preflight] LLM server unreachable at {base}: {e}", file=sys.stderr)
        print("[preflight] start the LLM server first (see ./start.sh or run llama-server manually)", file=sys.stderr)
        sys.exit(1)
    if not ids:
        print(f"[preflight] LLM server has no models loaded at {base}", file=sys.stderr)
        sys.exit(1)
    if config.OPENAI_MODEL not in ids:
        print(
            f"[preflight] WARN: OPENAI_MODEL={config.OPENAI_MODEL!r} not in served list {ids}; "
            "first served model will likely be used by single-model servers",
            file=sys.stderr,
        )

    proxy = config.DISCORD_PROXY
    test_url = "https://discord.com/api/v10/gateway"
    test_req = urllib.request.Request(test_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        if proxy:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"https": proxy, "http": proxy})
            )
            with opener.open(test_req, timeout=8) as r:
                ok = r.status == 200
        else:
            with urllib.request.urlopen(test_req, timeout=5) as r:
                ok = r.status == 200
        if not ok:
            raise RuntimeError("non-200")
    except Exception as e:
        print(f"[preflight] discord.com unreachable: {e}", file=sys.stderr)
        if proxy:
            print(f"[preflight] DISCORD_PROXY={proxy} not working — is SpoofDPI running with -window-size 1?", file=sys.stderr)
        else:
            print("[preflight] discord.com may be DPI-blocked on this network. Set DISCORD_PROXY in .env (e.g. http://127.0.0.1:8080 with SpoofDPI)", file=sys.stderr)
        sys.exit(1)

    print(f"[preflight] LLM ({base}) and Discord{' via '+proxy if proxy else ''} OK", flush=True)


_preflight()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, proxy=config.DISCORD_PROXY)

session_store = SessionStore(
    ttl_seconds=config.SESSION_TTL_SECONDS,
    max_messages=config.HISTORY_MAX_MESSAGES,
    system_prompt=config.SYSTEM_PROMPT,
)
llm = LLMClient(
    base_url=config.OPENAI_BASE_URL,
    api_key=config.OPENAI_API_KEY,
    model=config.OPENAI_MODEL,
)


def _should_respond(message: discord.Message) -> bool:
    if bot.user in message.mentions:
        return True
    if bot.user.name.lower() in message.content.lower():
        return True
    ref = message.reference
    return bool(ref and ref.resolved and ref.resolved.author == bot.user)


IMAGE_MIME_PREFIX = "image/"


def _image_attachments(message: discord.Message) -> list[discord.Attachment]:
    return [
        a for a in message.attachments
        if (a.content_type or "").startswith(IMAGE_MIME_PREFIX)
    ]


async def _build_user_content(message: discord.Message) -> str | list[dict]:
    author = message.author.display_name
    text = f"{author}: {message.content}".strip()
    images = _image_attachments(message)
    if not images:
        return text
    parts: list[dict] = [{"type": "text", "text": text}]
    for a in images:
        try:
            data = await a.read()
        except Exception:
            continue
        mime = a.content_type or "image/jpeg"
        b64 = base64.b64encode(data).decode("ascii")
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })
    return parts


def _format_for_history(message: discord.Message) -> str:
    author = message.author.display_name
    base = f"{author}: {message.content}"
    images = _image_attachments(message)
    if not images:
        return base
    tags = " ".join(f"[resim: {a.filename}]" for a in images)
    return f"{base} {tags}".strip()


async def _setup_hook():
    if config.SLASH_COMMAND_GUILD_ID:
        guild = discord.Object(id=config.SLASH_COMMAND_GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
    else:
        await bot.tree.sync()


bot.setup_hook = _setup_hook


@bot.event
async def on_ready():
    print(f"SivrisinekCenk yayında! {config.OPENAI_MODEL} hazır.")


@bot.tree.command(name="clear", description="Bu kanaldaki konuşma context'ini sıfırla")
async def clear_cmd(interaction: discord.Interaction):
    await session_store.clear(interaction.channel_id)
    await interaction.response.send_message("Yeni context açıldı, hafıza sıfır.", ephemeral=True)


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    history_content = _format_for_history(message)
    llm_content = await _build_user_content(message)
    channel_id = message.channel.id

    session = await session_store.get_or_create(channel_id)
    async with session.lock:
        await session_store.append(channel_id, "user", history_content)
        if not _should_respond(message):
            return
        snapshot = list(session.messages)
        if isinstance(llm_content, list):
            snapshot[-1] = {"role": "user", "content": llm_content}

    async with message.channel.typing():
        try:
            cevap = await llm.complete(snapshot)
        except Exception as e:
            await message.reply(f"OpenAI tarafına bağlanırken patladık aga: {e}")
            return

    if not cevap:
        await message.reply("Model cevap vermedi, sunucuya bir bak.")
        return

    async with session.lock:
        await session_store.append(channel_id, "assistant", cevap)
    await message.reply(cevap)


bot.run(config.DISCORD_TOKEN)
