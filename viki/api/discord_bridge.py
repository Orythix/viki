import os
import discord
from viki.config.logger import viki_logger

class DiscordBridge(discord.Client):
    def __init__(self, nexus):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.nexus = nexus

    async def on_ready(self):
        viki_logger.info(f"Discord Bridge: Logged in as {self.user}")

    async def on_message(self, message):
        if message.author == self.user:
            return

        async def reply_callback(text: str):
            await message.channel.send(text)

        await self.nexus.ingest(
            source="Discord",
            user_id=str(message.author.id),
            text=message.content,
            callback=reply_callback
        )

class DiscordModule:
    def __init__(self, nexus):
        self.nexus = nexus
        self.token = os.getenv("DISCORD_TOKEN")
        self.client = None

    async def start(self):
        if not self.token:
            viki_logger.warning("Discord token missing. Bridge disabled.")
            return

        self.client = DiscordBridge(self.nexus)
        # We run this in a task to avoid blocking mainstream
        asyncio.create_task(self.client.start(self.token))
        viki_logger.info("Discord Bridge task initiated.")

    async def stop(self):
        if self.client:
            await self.client.close()
