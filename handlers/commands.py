"""
Command handlers for basic bot commands.
"""

from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import settings
from messages import *
from utils.database import db
from utils.helpers import get_system_stats, format_bytes, format_seconds
from utils.logger import log_action


async def on_start(client: Client, message: Message):
    """Handle /start command."""
    user = message.from_user
    
    # Add user to database
    db.add_user(user.id, user.username or "", user.first_name or "", user.last_name or "")
    
    await message.reply_text(WELCOME_MESSAGE, )
    log_action(user.id, "command_start")


async def on_help(client: Client, message: Message):
    """Handle /help command."""
    user = message.from_user
    await message.reply_text(HELP_MESSAGE, )
    log_action(user.id, "command_help")


async def on_info(client: Client, message: Message):
    """Handle /info command - Show bot statistics."""
    user = message.from_user
    
    try:
        stats = db.get_stats()
        memory_percent, disk_percent, uptime = get_system_stats()
        
        info_text = INFO_MESSAGE.format(
            uptime=uptime,
            total_downloads=stats.get("total_downloads", 0),
            active_streams=stats.get("active_streams", 0),
            storage_used=format_bytes(stats.get("total_bytes_downloaded", 0)),
            memory_usage=f"{memory_percent:.1f}",
            disk_space=f"{disk_percent:.1f}",
            last_updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
        await message.reply_text(info_text, )
        log_action(user.id, "command_info")
    except Exception as e:
        await message.reply_text(f"❌ Error retrieving info: {str(e)}")
        log_action(user.id, "command_info_error", str(e), "ERROR")


async def on_settings(client: Client, message: Message):
    """Handle /settings command - User preferences."""
    user = message.from_user
    
    user_data = db.get_user(user.id)
    if not user_data:
        await message.reply_text("User not found. Use /start first.")
        return
    
    settings_text = SETTINGS_MESSAGE.format(
        notifications="Enabled",
        quality="Medium",
        auto_archive="Disabled"
    )
    
    await message.reply_text(settings_text, )
    log_action(user.id, "command_settings")


async def on_cancel(client: Client, message: Message):
    """Handle /cancel command - Cancel ongoing download."""
    user = message.from_user
    
    # TODO: Implement cancellation logic
    # This will be connected to download manager
    
    await message.reply_text(CANCEL_NOT_FOUND, )
    log_action(user.id, "command_cancel")


async def on_status(client: Client, message: Message):
    """Handle /status command - Check download progress."""
    user = message.from_user
    
    # Parse command: /status <download_id>
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("Usage: `/status <download_id>`", )
        return
    
    download_id = args[1]
    
    try:
        download = db.get_download(download_id)
        if not download:
            await message.reply_text("❌ Download not found.")
            return
        
        status_text = f"""
##DOUBLE_STAR##Download Status##DOUBLE_STAR##

##DOUBLE_STAR##ID:##DOUBLE_STAR## `{download['download_id']}`
##DOUBLE_STAR##Status:##DOUBLE_STAR## {download['status'].upper()}
##DOUBLE_STAR##Progress:##DOUBLE_STAR## {download['progress']}%
##DOUBLE_STAR##File:##DOUBLE_STAR## {download['filename'] or 'Unknown'}
##DOUBLE_STAR##Size:##DOUBLE_STAR## {format_bytes(download['filesize'] or 0)}
##DOUBLE_STAR##Started:##DOUBLE_STAR## {download['started_at']}
"""
        
        await message.reply_text(status_text, )
        log_action(user.id, "command_status", download_id)
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")
        log_action(user.id, "command_status_error", str(e), "ERROR")


def register_commands(app: Client):
    """Register all basic commands."""
    app.on_message(filters.command("start"))(on_start)
    app.on_message(filters.command("help"))(on_help)
    app.on_message(filters.command("info"))(on_info)
    app.on_message(filters.command("settings"))(on_settings)
    app.on_message(filters.command("cancel"))(on_cancel)
    app.on_message(filters.command("status"))(on_status)
