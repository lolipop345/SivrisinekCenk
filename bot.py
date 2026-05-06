import asyncio
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

import config
from llm_client import LLMClient
from memory_manager import MemoryManager
from session_store import SessionStore
from tools import TOOLS


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

    try:
        config.MEMPALACE_PATH.mkdir(parents=True, exist_ok=True)
        if not os.access(config.MEMPALACE_PATH, os.W_OK):
            raise PermissionError(f"{config.MEMPALACE_PATH} not writable")
        os.environ.setdefault("MEMPALACE_PALACE_PATH", str(config.MEMPALACE_PATH))
        import mempalace  # noqa: F401  (triggers chromadb + onnx model first-run download)
    except Exception as e:
        print(f"[preflight] memory backend init failed: {e}", file=sys.stderr)
        print(f"[preflight] check {config.MEMPALACE_PATH} or run 'pip install mempalace'", file=sys.stderr)
        print("[preflight] embedding model download issue? chroma uses S3 (not HF), so DPI usually OK", file=sys.stderr)
        sys.exit(1)
    print(f"[preflight] memory palace at {config.MEMPALACE_PATH} OK", flush=True)


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

EXTRACT_PROMPT = (Path(__file__).parent / "prompts" / "extract_facts.txt") \
    .read_text(encoding="utf-8").strip()
memory = MemoryManager(
    palace_path=config.MEMPALACE_PATH,
    llm=llm,
    extract_prompt=EXTRACT_PROMPT,
    retrieval_k=config.MEMORY_RETRIEVAL_K,
    min_fact_len=config.MEMORY_MIN_FACT_LEN,
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


@bot.tree.command(name="clear", description="Bu kanaldaki kısa hafızayı sıfırla")
async def clear_cmd(interaction: discord.Interaction):
    await session_store.clear(interaction.channel_id)
    await interaction.response.send_message(
        "Yeni context açıldı, kısa hafıza sıfır. (Kalıcı hafıza dokunulmadı — silmek için /forget)",
        ephemeral=True,
    )


_SCOPE_CHOICES = [
    app_commands.Choice(name="user (sana özel)", value="user"),
    app_commands.Choice(name="channel (kanal ortak)", value="channel"),
]


@bot.tree.command(name="remember", description="Kalıcı hafızaya not ekle")
@app_commands.choices(scope=_SCOPE_CHOICES)
async def remember_cmd(
    interaction: discord.Interaction,
    scope: app_commands.Choice[str],
    text: str,
):
    await interaction.response.defer(ephemeral=True, thinking=True)
    if scope.value == "user":
        await memory.add_user_fact(interaction.user.id, text, source="slash")
    else:
        await memory.add_channel_fact(interaction.channel_id, text, source="slash")
    await interaction.followup.send(
        f"Hafızaya yazıldı ({scope.value}): {text[:200]}",
        ephemeral=True,
    )


@bot.tree.command(name="forget", description="Kalıcı hafızayı sil (geri alınamaz)")
@app_commands.choices(scope=_SCOPE_CHOICES)
async def forget_cmd(
    interaction: discord.Interaction,
    scope: app_commands.Choice[str],
    confirm: str,
):
    if confirm.strip().lower() not in ("evet sil", "yes delete"):
        await interaction.response.send_message(
            "İptal — silmek için confirm parametresine `evet sil` yaz.",
            ephemeral=True,
        )
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    if scope.value == "user":
        deleted = await memory.forget_user(interaction.user.id)
    else:
        deleted = await memory.forget_channel(interaction.channel_id)
    await interaction.followup.send(
        f"Persistent hafıza silindi ({scope.value}): {deleted} not.",
        ephemeral=True,
    )


@bot.tree.command(name="memory_list", description="Kalıcı hafızadaki notları listele")
@app_commands.choices(scope=_SCOPE_CHOICES)
async def memory_list_cmd(
    interaction: discord.Interaction,
    scope: app_commands.Choice[str],
):
    await interaction.response.defer(ephemeral=True, thinking=True)
    if scope.value == "user":
        items = await memory.list_user_facts(interaction.user.id)
    else:
        items = await memory.list_channel_facts(interaction.channel_id)
    if not items:
        await interaction.followup.send("Hafıza boş.", ephemeral=True)
        return
    body = "\n".join(f"- {x}" for x in items[:30])
    msg = f"```\n{body}\n```"
    if len(msg) > 1990:
        msg = msg[:1985] + "\n```"
    await interaction.followup.send(msg, ephemeral=True)


MAX_TOOL_ITERS = 4


async def _dispatch_tool_call(tool_call, user_id: int, channel_id: int) -> str:
    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments or "{}")
    except json.JSONDecodeError as e:
        return json.dumps({"ok": False, "error": f"invalid args JSON: {e}"})

    if name == "save_memory":
        scope = args.get("scope")
        fact = (args.get("fact") or "").strip()
        if scope not in ("user", "channel") or not fact:
            return json.dumps({
                "ok": False,
                "error": "scope must be 'user' or 'channel' and fact must be non-empty",
            })
        try:
            if scope == "user":
                await memory.add_user_fact(user_id, fact, source="tool")
            else:
                await memory.add_channel_fact(channel_id, fact, source="tool")
            return json.dumps({"ok": True, "scope": scope, "fact": fact})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    return json.dumps({"ok": False, "error": f"unknown tool: {name}"})


async def _run_with_tools(
    snapshot: list[dict], user_id: int, channel_id: int
) -> str:
    msg = None
    for _ in range(MAX_TOOL_ITERS):
        msg = await llm.complete(snapshot, tools=TOOLS, return_message=True)
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            return (msg.content or "").strip()

        snapshot.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:
            result = await _dispatch_tool_call(tc, user_id, channel_id)
            snapshot.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return (
        (msg.content or "").strip()
        if msg is not None
        else "Çok fazla tool çağrısı, vazgeçtim."
    )


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

    try:
        notes = await memory.query_relevant(
            user_id=message.author.id,
            channel_id=channel_id,
            query=message.content or "",
        )
    except Exception as e:
        print(f"[memory] retrieval failed: {e}", file=sys.stderr)
        notes = []
    if notes:
        bullet = "\n".join(f"- {n}" for n in notes)
        snapshot.insert(1, {
            "role": "system",
            "content": (
                "## Kalıcı hafızadaki ilgili notlar\n"
                "(önceki konuşmalardan damıtılmış kalıcı bilgiler — bağlam olarak kullan, "
                "gerek olmadıkça aynen tekrar etme)\n" + bullet
            ),
        })

    async with message.channel.typing():
        try:
            cevap = await _run_with_tools(snapshot, message.author.id, channel_id)
        except Exception as e:
            await message.reply(f"OpenAI tarafına bağlanırken patladık aga: {e}")
            return

    if not cevap:
        await message.reply("Model cevap vermedi, sunucuya bir bak.")
        return

    async with session.lock:
        await session_store.append(channel_id, "assistant", cevap)
    await message.reply(cevap)

    if config.MEMORY_AUTO_EXTRACT:
        async with session.lock:
            post_snapshot = list(session.messages)
        asyncio.create_task(memory.maybe_auto_extract(
            channel_id=channel_id,
            author_id=message.author.id,
            snapshot=post_snapshot,
            every_n=config.MEMORY_EXTRACT_EVERY_N_MESSAGES,
        ))


@bot.tree.command(
    name="memory",
    description="Kalıcı hafızanın tüm özetini göster (sana özel + bu kanal)",
)
async def memory_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    user_facts, chan_facts = await asyncio.gather(
        memory.list_user_facts(interaction.user.id, limit=50),
        memory.list_channel_facts(interaction.channel_id, limit=50),
    )

    if not user_facts and not chan_facts:
        await interaction.followup.send(
            "Hafıza tamamen boş — `/remember` ile başlayabilirsin.",
            ephemeral=True,
        )
        return

    parts: list[str] = ["## Sana özel hatırladıklarım"]
    if user_facts:
        parts.extend(f"- {f}" for f in user_facts)
    else:
        parts.append("(yok)")
    parts.append("")
    parts.append("## Bu kanalda hatırladıklarım")
    if chan_facts:
        parts.extend(f"- {f}" for f in chan_facts)
    else:
        parts.append("(yok)")
    parts.append("")
    parts.append(
        f"[user: {len(user_facts)} not • channel: {len(chan_facts)} not • "
        f"palace: {config.MEMPALACE_PATH}]"
    )

    body = "\n".join(parts)
    msg = f"```\n{body}\n```"
    if len(msg) > 1990:
        msg = msg[:1970] + "\n... (kesildi, /memory_list ile gör)\n```"
    await interaction.followup.send(msg, ephemeral=True)


bot.run(config.DISCORD_TOKEN)
