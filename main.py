"""
Main bot application - Initializes and runs the Telegram bot.
"""

import asyncio
from pyrogram import Client, idle
from pyrogram.errors import ApiIdInvalid, AccessTokenInvalid

from config import settings
from utils.logger import logger
from handlers.commands import register_commands
from handlers.admin import register_admin_commands
from handlers.admin_panel import register_admin_panel
from handlers.download import register_download_handlers
from handlers.channel_forwarder import register_channel_forwarder_handlers
from downloader.terabox_api import init_terabox_api


class TeraBoxBot:
    """Main bot class."""

    def __init__(self):
        """Initialize bot."""
        self.app = None
        self.setup_client()

    def setup_client(self):
        """Setup Pyrogram client."""
        self.app = Client(
            name="terabox_bot",
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
            bot_token=settings.telegram_bot_token,
            workdir="./sessions"
        )

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
