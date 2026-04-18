"""
Main bot application - Initializes and runs the Telegram bot.
"""

import asyncio
from pathlib import Path
from pyrogram import Client, idle
from pyrogram.errors import ApiIdInvalid, AccessTokenInvalid

from config import settings
from utils.logger import logger
from handlers.commands import register_commands
from handlers.admin import register_admin_commands
from handlers.admin_panel import register_admin_panel
from handlers.download import register_download_handlers
from handlers.channel_forwarder import register_channel_forwarder_handlers
from handlers.group_processor import register_group_processor
from downloader.terabox_api import init_terabox_api


class TeraBoxBot:
    """Main bot class."""

    def __init__(self):
        """Initialize bot."""
        self.app = None
        self.user_app = None  # User account for accessing message history
        self.setup_client()

    def setup_client(self):
        """Setup Pyrogram client."""
        sessions_dir = Path(__file__).resolve().parent / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        self.app = Client(
            name="terabox_bot",
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
            bot_token=settings.telegram_bot_token,
            workdir=str(sessions_dir)
        )
        
        # Create user account client if enabled (needed for accessing message history)
        if settings.use_user_account and settings.user_phone:
            self.user_app = Client(
                name="terabox_user",
                api_id=settings.telegram_api_id,
                api_hash=settings.telegram_api_hash,
                phone_number=settings.user_phone,
                workdir=str(sessions_dir)
            )
            logger.info("✅ User account client configured for accessing message history")

    def register_handlers(self):
        """Register all command and message handlers."""
        logger.info("Registering command handlers...")
        register_commands(self.app)
        
        logger.info("Registering admin handlers...")
        register_admin_commands(self.app)
        
        logger.info("Registering admin panel handlers...")
        register_admin_panel(self.app)
        
        logger.info("Registering download handlers...")
        register_download_handlers(self.app)
        
        logger.info("Registering channel forwarder handlers...")
        register_channel_forwarder_handlers(self.app)
        logger.info("Registering group processor handlers...")
        register_group_processor(self.app)
        
        logger.info("All handlers registered successfully")

    async def start(self):
        """Start the bot."""
        try:
            # Initialize TeraBox API
            logger.info("Initializing TeraBox API...")
            init_terabox_api(settings.terabox_api_v1)
            
            await self.app.start()
            bot_info = await self.app.get_me()
            
            logger.info(f"✅ Bot started successfully!")
            logger.info(f"Bot username: @{bot_info.username}")
            logger.info(f"Bot ID: {bot_info.id}")
            logger.info(f"Admins: {settings.admin_ids}")
            
            # Optionally process existing messages from source channels after bot is running
            # This can be CPU/IO intensive; disable by default to keep bot responsive.
            if settings.enable_startup_processing:
                asyncio.create_task(self.process_existing_messages_on_startup())
            else:
                logger.info("[StartupProcessor] STARTUP historical processing disabled (set ENABLE_STARTUP_PROCESSING=True to enable)")
            
            # Keep bot running
            await idle()
            
        except ApiIdInvalid:
            logger.error("❌ Invalid API ID. Check your Telegram credentials.")
            raise
        except AccessTokenInvalid:
            logger.error("❌ Invalid bot token. Check your TELEGRAM_BOT_TOKEN.")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to start bot: {e}")
            raise

    async def process_existing_messages_on_startup(self):
        """Process ALL existing messages from source channels after bot startup."""
        try:
            # Give bot a moment to fully initialize
            await asyncio.sleep(2)
            
            from handlers.channel_forwarder import process_existing_messages
            from config import settings
            
            # Check if we can access message history
            if not settings.use_user_account or not self.user_app:
                logger.warning("[StartupProcessor] ⚠️  User account not configured - cannot fetch message history")
                logger.warning("[StartupProcessor] ⚠️  To process existing messages, enable USE_USER_ACCOUNT=True and USER_PHONE in .env")
                return
            
            # Start user account client
            logger.info("[StartupProcessor] 🔐 Starting user account to access message history...")
            await self.user_app.start()
            logger.info("[StartupProcessor] ✅ User account connected")
            
            logger.info(f"[StartupProcessor] 🔍 Processing ALL historical messages from source channels...\n")
            
            if settings.source_channels_list:
                for chat_id in settings.source_channels_list:
                    logger.info(f"[StartupProcessor] 📚 Starting to fetch ALL messages from {chat_id}...")
                    logger.info(f"[StartupProcessor] ⏳ This may take a while if there are many messages...")
                    # Use user account to fetch history, but bot to process/post
                    await process_existing_messages(self.user_app, chat_id, limit=None)
                    await asyncio.sleep(1)  # Rate limit between channels
            
            logger.info(f"[StartupProcessor] ✅ ALL historical messages processed!\n")
            logger.info(f"[StartupProcessor] 🎯 Now listening for NEW messages...\n")
            
        except Exception as e:
            logger.warning(f"[StartupProcessor] ⚠️  Error processing historical messages: {e}")

    async def stop(self):
        """Stop the bot gracefully."""
        logger.info("Stopping bot...")
        try:
            await self.app.stop()
            logger.info("✅ Bot stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")

    async def run(self):
        """Run the bot."""
        self.register_handlers()
        await self.start()


async def main():
    """Main entry point."""
    logger.info("=" * 50)
    logger.info("TeraBox Downloader Bot v1.0.0")
    logger.info("=" * 50)
    
    bot = TeraBoxBot()
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("\nKeyboard interrupt received, shutting down...")
        await bot.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    """Bot entry point."""
    asyncio.run(main())
