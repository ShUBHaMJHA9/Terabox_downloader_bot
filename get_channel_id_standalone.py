#!/usr/bin/env python3
"""
Get the numeric ID of a private channel by username.
Standalone version - doesn't import config.
"""

import asyncio
from pyrogram import Client

async def get_channel_id(channel_username: str):
    """Get numeric ID from channel username."""
    
    app = Client(
        name="terabox_bot",
        api_id=11468953,
        api_hash="99f7513ef4889752f6278af3286a929c",
        bot_token="8308271074:AAGCKnj8fgHtQU49WqMbT1w20oz0mXyZIuI",
        workdir="./sessions"
    )
    
    async with app:
        print(f"🔍 Looking up channel: {channel_username}")
        
        try:
            # Try with @ prefix
            if not channel_username.startswith("@"):
                channel_username = "@" + channel_username
            
            chat = await app.get_chat(channel_username)
            print(f"✅ Found: {chat.title or chat.username}")
            print(f"📱 Numeric ID: {chat.id}")
            print(f"\n✏️  Update your .env file:")
            print(f"SOURCE_CHANNELS={chat.id}")
            
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    channel = input("Enter channel username (e.g., teraboxlinksisherer): ").strip()
    asyncio.run(get_channel_id(channel))
