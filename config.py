import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "not-needed")
OPENAI_MODEL = os.getenv(
    "OPENAI_MODEL",
    "TrevorJS/gemma-4-E2B-it-uncensored-GGUF/gemma-4-E2B-it-uncensored-Q4_K_M.gguf",
)

PERSONA_PATH = Path(__file__).parent / "prompts" / "persona.txt"
SYSTEM_PROMPT = PERSONA_PATH.read_text(encoding="utf-8").strip()

SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "7200"))
HISTORY_MAX_MESSAGES = int(os.getenv("HISTORY_MAX_MESSAGES", "100"))

_guild_id = os.getenv("GUILD_ID", "").strip()
SLASH_COMMAND_GUILD_ID = int(_guild_id) if _guild_id else None

DISCORD_PROXY = os.getenv("DISCORD_PROXY", "").strip() or None

MEMPALACE_PATH = Path(os.getenv(
    "MEMPALACE_PATH",
    str(Path.home() / ".sivrisinekcenk" / "mempalace"),
)).expanduser()
MEMORY_AUTO_EXTRACT = os.getenv("MEMORY_AUTO_EXTRACT", "true").lower() == "true"
MEMORY_EXTRACT_EVERY_N_MESSAGES = int(os.getenv("MEMORY_EXTRACT_EVERY_N_MESSAGES", "8"))
MEMORY_RETRIEVAL_K = int(os.getenv("MEMORY_RETRIEVAL_K", "3"))
MEMORY_MIN_FACT_LEN = int(os.getenv("MEMORY_MIN_FACT_LEN", "6"))

AUDIO_TRANSCRIBE = os.getenv("AUDIO_TRANSCRIBE", "true").lower() == "true"
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "").strip() or None
