import subprocess

from config import LMS_PATH, MODEL_NAME, SYSTEM_PROMPT


def chat(user_input: str) -> str:
    command = [
        LMS_PATH, "chat", MODEL_NAME,
        "-s", SYSTEM_PROMPT,
        "-p", user_input,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception as e:
        return f"Shell'den bağlanırken patladık aga: {e}"
