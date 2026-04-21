"""
Command handlers for basic bot commands.
"""

from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import settings
from messages import *
from utils.database import db
from utils.helpers import get_system_stats, format_bytes, format_seconds
from utils.logger import log_action, logger
from datetime import datetime
from utils.telegram import TelegramUploader
import asyncio


async def on_start(client: Client, message: Message):
    """Handle /start command."""
    user = message.from_user
    # Add user to database
    db.add_user(user.id, user.username or "", user.first_name or "", user.last_name or "")

    # Handle deep-link: /start video_<id>
    args = (message.text or "").split()
    if len(args) > 1 and args[1].startswith("video_"):
        try:
            record_id = int(args[1].split("video_")[1])
        except Exception:
            await message.reply_text(WELCOME_MESSAGE)
            log_action(user.id, "command_start")
            return

        # Try both cached_backups (channel_forwarder) and cached_videos (group_processor)
        record = db.get_cached_by_id(record_id)
        if not record:
            record = db.get_cached_video_by_id(record_id)

        if not record:
            await message.reply_text("❌ Video not found or not available.")
            log_action(user.id, "deep_link_missing", str(record_id))
            return

        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # Try server-side copy from available backup location(s)
        uploader = TelegramUploader(client)
        backup_channel_id = record.get("backup_channel_id")
        backup_message_id = record.get("backup_message_id")

        copied = None
        source_location = "unknown"

        # Build list of candidate source channels where the backup message may reside
        candidate_sources = []
        if backup_channel_id:
            candidate_sources.append(int(backup_channel_id))
        if settings.database_channel and int(settings.database_channel) not in candidate_sources:
            candidate_sources.append(int(settings.database_channel))

        # Attempt to copy from each candidate using the stored backup_message_id
        for source_ch in candidate_sources:
            if not source_ch or not backup_message_id:
                continue
            try:
                logger.info(f"[/start] Attempting to copy from channel {source_ch} (msg {backup_message_id})...")
                copied = await uploader.copy_message_to_channel(
                    from_chat_id=source_ch,
                    message_id=backup_message_id,
                    channel_id=chat_id
                )
                if copied:
                    if source_ch == int(settings.database_channel):
                        source_location = "Database"
                    else:
                        source_location = f"Channel {source_ch}"
                    logger.info(f"[/start] ✅ Copied from {source_location}")
                    break
            except Exception as e:
                logger.debug(f"[/start] Failed to copy from {source_ch}: {e}")
                continue
        
        if copied:
            # Schedule deletion after 30 minutes (1800s) - ONLY delete bot's response
            async def _delete_later(del_chat_id: int, del_msg_id: int, delay: int = 1800):
                await asyncio.sleep(delay)
                try:
                    await client.delete_messages(del_chat_id, del_msg_id)
                    logger.info(f"[/start] ✅ Auto-deleted message {del_msg_id} after {delay}s")
                except Exception as e:
                    logger.debug(f"[/start] Failed to delete message: {e}")

            # Schedule both the response message AND the video message for deletion
            asyncio.create_task(_delete_later(chat_id, copied.id, 1800))
            
            response_msg = await message.reply_text(
                f"✅ Video delivered from {source_location}.\n\n⏰ Message will auto-delete in 30 minutes.",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            # Also schedule the response message for deletion
            asyncio.create_task(_delete_later(chat_id, response_msg.id, 1800))
            
            log_action(user_id, "deep_link_served", f"record_id={record_id} from={source_location}")
            return
        else:
            error_msg = await message.reply_text("❌ Failed to deliver video. It may no longer be available in archive.")
            log_action(user.id, "deep_link_copy_failed", str(record_id))
            # Also schedule this error message for deletion
            asyncio.create_task(
                (lambda: None).__code__.co_consts[1] or asyncio.sleep(1800)
                if False else asyncio.sleep(1800)
            )
            # Actually schedule it properly
            async def _delete_error():
                await asyncio.sleep(1800)
                try:
                    await client.delete_messages(chat_id, error_msg.id)
                except Exception:
                    pass
            asyncio.create_task(_delete_error())
            return

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
    # If debug mode is enabled, register a catch-all message logger to help
    # diagnose why commands may not be reaching handlers (only for debugging).
    if settings.debug:
        async def _debug_log_message(client: Client, message: Message):
            try:
                user_id = getattr(message.from_user, "id", None)
                username = getattr(message.from_user, "username", None)
                chat_id = getattr(message.chat, "id", None)
                chat_type = getattr(message.chat, "type", None)
                text = (message.text or message.caption or "").strip()
                logger.info(f"[DEBUG] Incoming message: user={user_id} username={username} chat={chat_id} type={chat_type} text={text}")
            except Exception as e:
                logger.debug(f"[DEBUG] Error logging incoming message: {e}")

        app.on_message()( _debug_log_message )
        logger.info("[DEBUG] Registered debug message logger (settings.debug=True)")
