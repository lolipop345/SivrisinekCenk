import discord
import os
import subprocess
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('Token')

# Terminalde 'which lms' yazınca çıkan tam yolu buraya yapıştır
# Genelde şunlardan biridir: /usr/local/bin/lms veya /opt/homebrew/bin/lms
LMS_PATH = "/usr/local/bin/lms" 

MODEL_NAME = "TrevorJS/gemma-4-E2B-it-uncensored-GGUF/gemma-4-E2B-it-uncensored-Q4_K_M.gguf"

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

def lms_shell_chat(user_input):
    try:
        # lms chat komutunu tam yol üzerinden tetikliyoruz
        command = [
            LMS_PATH, "chat", MODEL_NAME,
            "-s", "Senin adın SivrisinekCenk. Giresunlu, fındık sever, 64GB RAM'li bir oyun geliştiricisisin. Kısa ve troll cevap ver.",
            "-p", user_input
        ]
        
        # subprocess ile terminale bağlanıyoruz
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception as e:
        return f"Shell'den bağlanırken patladık aga: {e}"

@client.event
async def on_ready():
    print(f'SivrisinekCenk yayında! Mac M1 ve {MODEL_NAME} hazır.')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # Bot tetikleyicileri (Etiket, Reply, İsim)
    if client.user in message.mentions or client.user.name.lower() in message.content.lower() or (message.reference and message.reference.resolved and message.reference.resolved.author == client.user):
        
        async with message.channel.typing(): # Bot yazıyor... efekti
            cevap = lms_shell_chat(message.content)
            await message.reply(cevap if cevap else "Model cevap vermedi, lms'e bir bak.")

client.run(TOKEN)