#!/usr/bin/env python3
"""
Get the numeric ID of a private channel by username.
"""

import asyncio
from pyrogram import Client
from utils.logger import logger

async def get_channel_id(channel_username: str):
    """Get numeric ID from channel username."""
    
    # Temporarily use valid settings just to connect
    app = Client(
        name="terabox_bot",
        api_id=11468953,
        api_hash="99f7513ef4889752f6278af3286a929c",
        bot_token="8308271074:AAGCKnj8fgHtQU49WqMbT1w20oz0mXyZIuI",
        workdir="./sessions"
    )
    
    async with app:
        logger.info(f"🔍 Looking up channel: {channel_username}")
        
        try:
            # Try with @ prefix
            if not channel_username.startswith("@"):
                channel_username = "@" + channel_username
            
            chat = await app.get_chat(channel_username)
            logger.info(f"✅ Found: {chat.title or chat.username}")
            logger.info(f"📱 Numeric ID: {chat.id}")
            
        except Exception as e:
            logger.error(f"❌ Error: {e}")

if __name__ == "__main__":
    channel = input("Enter channel username (e.g., teraboxlinksisherer): ").strip()
    asyncio.run(get_channel_id(channel))
