import os
import asyncio
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from viki.config.logger import viki_logger

class TelegramBridge:
    def __init__(self, controller):
        self.controller = controller
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.application = None

    async def start(self):
        if not self.token:
            viki_logger.warning("Telegram token missing. Bridge disabled.")
            return

        self.application = ApplicationBuilder().token(self.token).build()
        
        # Handlers
        start_handler = CommandHandler('start', self._start_cmd)
        msg_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), self._handle_msg)
        
        self.application.add_handler(start_handler)
        self.application.add_handler(msg_handler)
        
        viki_logger.info("Telegram Bridge initialized.")
        await self.application.initialize()
        await self.application.start()
        # Start polling in background
        if self.application.updater:
            await self.application.updater.start_polling()

    async def _start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("VIKI Digital Partner: ONLINE. How can I help you today?")

    async def _handle_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_text = update.message.text
        viki_logger.info(f"Telegram Interface: Received '{user_text}'")
        
        async def reply_callback(text: str):
            await update.message.reply_text(text)

        # Ingest into Unified Nexus
        if hasattr(self.controller, 'nexus'):
            await self.controller.nexus.ingest(
                source="Telegram",
                user_id=str(update.effective_user.id),
                text=user_text,
                callback=reply_callback
            )
        else:
            # Fallback
            response = await self.controller.process_request(user_text)
            await update.message.reply_text(response)

    async def stop(self):
        if self.application:
            await self.application.stop()
            await self.application.shutdown()
