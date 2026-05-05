import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]

LMS_PATH = os.getenv("LMS_PATH", "/usr/local/bin/lms")

MODEL_NAME = os.getenv(
    "LMS_MODEL",
    "TrevorJS/gemma-4-E2B-it-uncensored-GGUF/gemma-4-E2B-it-uncensored-Q4_K_M.gguf",
)

PERSONA_PATH = Path(__file__).parent / "prompts" / "persona.txt"
SYSTEM_PROMPT = PERSONA_PATH.read_text(encoding="utf-8").strip()
