import discord

import config
import lms_client

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


def _should_respond(message: discord.Message) -> bool:
    if client.user in message.mentions:
        return True
    if client.user.name.lower() in message.content.lower():
        return True
    ref = message.reference
    return bool(ref and ref.resolved and ref.resolved.author == client.user)


@client.event
async def on_ready():
    print(f"SivrisinekCenk yayında! Mac M1 ve {config.MODEL_NAME} hazır.")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if not _should_respond(message):
        return

    async with message.channel.typing():
        cevap = lms_client.chat(message.content)
        await message.reply(cevap if cevap else "Model cevap vermedi, lms'e bir bak.")


client.run(config.DISCORD_TOKEN)
