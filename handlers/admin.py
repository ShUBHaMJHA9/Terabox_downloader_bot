"""
Admin command handlers - Restricted to bot administrators only.
"""

from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import settings
from messages import *
from utils.database import db
from utils.logger import logger, get_recent_logs, log_action
from utils.helpers import get_system_stats
from datetime import datetime


def is_admin(user_id: int) -> bool:
    """Check if user is bot admin."""
    return user_id in settings.admin_ids_list


def admin_only(func):
    """Decorator to restrict command to admins only."""
    async def wrapper(client: Client, message: Message):
        if not is_admin(message.from_user.id):
            await message.reply_text(ADMIN_ONLY, )
            log_action(message.from_user.id, "unauthorized_admin_access")
            return
        return await func(client, message)
    return wrapper


@admin_only
async def on_admin_panel(client: Client, message: Message):
    """Handle /admin command - Show admin panel."""
    user = message.from_user
    await message.reply_text(ADMIN_PANEL, )
    log_action(user.id, "admin_panel_accessed")


@admin_only
async def on_admin_broadcast(client: Client, message: Message):
    """
    Handle /admin broadcast <message> - Broadcast message to all users.
    
    Usage: /admin broadcast Hello everyone!
    """
    user = message.from_user
    
    # Parse command
    text_parts = message.text.split(maxsplit=2)
    if len(text_parts) < 3:
        await message.reply_text("Usage: `/admin broadcast <message>`", )
        return
    
    broadcast_msg = text_parts[2]
    
    try:
        # Get all users from database
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        conn.close()
        
        sent = 0
        failed = 0
        
        for row in users:
            user_id = row[0]
            try:
                await client.send_message(
                    chat_id=user_id,
                    text=f"📢 ##DOUBLE_STAR##Broadcast from Admin##DOUBLE_STAR##\n\n{broadcast_msg}",
                    
                )
                sent += 1
            except Exception as e:
                logger.debug(f"Failed to send broadcast to {user_id}: {e}")
                failed += 1
        
        await message.reply_text(
            f"✅ Broadcast complete!\n\nSent: {sent}\nFailed: {failed}",
            
        )
        log_action(user.id, "broadcast_sent", f"To {sent} users")
    except Exception as e:
        await message.reply_text(f"❌ Broadcast error: {str(e)}")
        log_action(user.id, "broadcast_error", str(e), "ERROR")


@admin_only
async def on_admin_stats(client: Client, message: Message):
    """Handle /admin stats - Show detailed statistics."""
    user = message.from_user
    
    try:
        stats = db.get_stats()
        memory_percent, disk_percent, uptime = get_system_stats()
        
        stats_text = f"""
##DOUBLE_STAR##📊 Detailed Bot Statistics##DOUBLE_STAR##

##DOUBLE_STAR##Users:##DOUBLE_STAR##
  Total Users: {stats.get('total_users', 0)}
  
##DOUBLE_STAR##Downloads:##DOUBLE_STAR##
  Total Downloads: {stats.get('total_downloads', 0)}
  Active Streams: {stats.get('active_streams', 0)}
  Failed: {stats.get('failed_downloads', 0)}
  
##DOUBLE_STAR##Storage:##DOUBLE_STAR##
  Total Downloaded: {format_bytes(stats.get('total_bytes_downloaded', 0))}
  
##DOUBLE_STAR##System:##DOUBLE_STAR##
  Memory: {memory_percent:.1f}%
  Disk: {disk_percent:.1f}%
  Uptime: {uptime}
  
Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        await message.reply_text(stats_text, )
        log_action(user.id, "admin_stats_viewed")
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")
        log_action(user.id, "admin_stats_error", str(e), "ERROR")


@admin_only
async def on_admin_log(client: Client, message: Message):
    """
    Handle /admin log [lines] - View recent logs.
    
    Usage: /admin log 50
    """
    user = message.from_user
    
    # Parse number of lines (default 50)
    text_parts = message.text.split()
    lines = 50
    if len(text_parts) > 2:
        try:
            lines = int(text_parts[2])
        except ValueError:
            await message.reply_text("Usage: `/admin log [number_of_lines]`", )
            return
    
    try:
        log_content = get_recent_logs(lines)
        
        # Split long logs into multiple messages (Telegram limit)
        if len(log_content) > 4096:
            # Send as file instead
            from pathlib import Path
            import tempfile
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
                f.write(log_content)
                temp_path = f.name
            
            await client.send_document(
                chat_id=user.id,
                document=temp_path,
                caption=f"📋 Recent Logs ({lines} lines)"
            )
            
            # Clean up
            Path(temp_path).unlink()
        else:
            log_text = f"```\n{log_content}\n```"
            await message.reply_text(log_text, )
        
        log_action(user.id, "admin_logs_viewed", f"{lines} lines")
    except Exception as e:
        await message.reply_text(f"❌ Error retrieving logs: {str(e)}")
        log_action(user.id, "admin_log_error", str(e), "ERROR")


@admin_only
async def on_admin_clear_queue(client: Client, message: Message):
    """Handle /admin clear_queue - Clear pending downloads."""
    user = message.from_user
    
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Count pending downloads
        cursor.execute("SELECT COUNT(*) as count FROM downloads WHERE status = 'pending'")
        count = cursor.fetchone()[0]
        
        # Clear pending downloads
        cursor.execute("UPDATE downloads SET status = 'cancelled' WHERE status = 'pending'")
        conn.commit()
        conn.close()
        
        await message.reply_text(
            f"✅ Cleared {count} pending downloads from queue.",
            
        )
        log_action(user.id, "queue_cleared", f"{count} downloads")
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")
        log_action(user.id, "clear_queue_error", str(e), "ERROR")


@admin_only
async def on_admin_restart(client: Client, message: Message):
    """Handle /admin restart - Restart bot (requires system support)."""
    user = message.from_user
    
    await message.reply_text(
        "🔄 ##DOUBLE_STAR##Restart request received##DOUBLE_STAR##\n\n"
        "The bot will restart shortly. This command requires manual intervention on the server.\n"
        "Contact your system administrator.",
        
    )
    log_action(user.id, "restart_requested")
    
    # TODO: Implement graceful shutdown and restart logic
    # This would require process manager support (systemd, supervisor, etc.)


def register_admin_commands(app: Client):
    """Register all admin commands."""
    app.on_message(filters.command("admin") & filters.private)(on_admin_panel)
    # Note: Subcommands can be handled by parsing message.text in handlers


# Helper function for formatting bytes (imported from helpers would be better)
def format_bytes(bytes_size: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.2f} PB"
