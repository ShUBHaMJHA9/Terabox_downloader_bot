"""
Advanced admin panel with inline buttons and detailed controls.
"""

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from datetime import datetime, timedelta
from config import settings
from messages import *
from utils.database import db
from utils.logger import logger, log_action, log_error
from utils.helpers import format_bytes
import json


def is_admin(func):
    """Decorator to check admin access."""
    async def wrapper(client: Client, message: Message):
        if message.from_user.id not in [int(aid) for aid in settings.admin_ids.split(",") if aid.strip()]:
            await message.reply_text(
                "❌ *Access Denied*\n\nYou don't have permission to use this command.",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        return await func(client, message)
    return wrapper


async def admin_menu(client: Client, message: Message):
    """Send admin control panel."""
    user = message.from_user
    
    # Get bot stats
    total_users = db.get_total_users()
    total_downloads = db.get_total_downloads()
    active_downloads = db.get_active_downloads()
    
    stats_text = f"""🛡️ *Admin Control Panel*

📊 *Bot Statistics:*
• Total Users: {total_users}
• Total Downloads: {total_downloads}
• Active Downloads: {active_downloads}

*Select an option below:*"""

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Detailed Stats", callback_data="admin_stats_detailed"),
            InlineKeyboardButton("📋 Recent Downloads", callback_data="admin_downloads_list")
        ],
        [
            InlineKeyboardButton("👥 Active Users", callback_data="admin_users_list"),
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton("🗑️ Clear Queue", callback_data="admin_clear_queue"),
            InlineKeyboardButton("📁 Database Info", callback_data="admin_db_info")
        ],
        [
            InlineKeyboardButton("⚙️ Bot Settings", callback_data="admin_settings"),
            InlineKeyboardButton("🔍 User Lookup", callback_data="admin_user_lookup")
        ],
        [
            InlineKeyboardButton("🔄 System Status", callback_data="admin_system_status"),
            InlineKeyboardButton("❌ Close", callback_data="admin_close")
        ]
    ])
    
    await message.reply_text(
        stats_text,
        parse_mode=enums.ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    
    log_action(user.id, "admin_panel_opened")


async def handle_admin_callback(client: Client, callback_query: CallbackQuery):
    """Handle admin panel button callbacks."""
    user = callback_query.from_user
    admin_ids = [int(aid) for aid in settings.admin_ids.split(",") if aid.strip()]
    
    if user.id not in admin_ids:
        await callback_query.answer("❌ Access Denied", show_alert=True)
        return
    
    action = callback_query.data
    
    try:
        if action == "admin_stats_detailed":
            await show_detailed_stats(client, callback_query, user)
        
        elif action == "admin_downloads_list":
            await show_downloads_list(client, callback_query)
        
        elif action == "admin_users_list":
            await show_users_list(client, callback_query)
        
        elif action == "admin_broadcast":
            await start_broadcast(client, callback_query)
        
        elif action == "admin_clear_queue":
            await clear_queue(client, callback_query, user)
        
        elif action == "admin_db_info":
            await show_db_info(client, callback_query)
        
        elif action == "admin_settings":
            await show_bot_settings(client, callback_query)
        
        elif action == "admin_system_status":
            await show_system_status(client, callback_query)
        
        elif action == "admin_close":
            await callback_query.message.delete()
        
        elif action.startswith("admin_user_"):
            user_id = int(action.split("_")[-1])
            await show_user_details(client, callback_query, user_id)
        
    except Exception as e:
        logger.error(f"Admin callback error: {e}")
        await callback_query.answer(f"Error: {str(e)}", show_alert=True)


async def show_detailed_stats(client: Client, callback_query: CallbackQuery, user):
    """Show detailed statistics."""
    stats = db.get_detailed_stats()
    
    text = """📊 *Detailed Statistics*

*User Stats:*"""
    
    if stats.get("total_users"):
        text += f"\n• Total Users: {stats['total_users']}"
        text += f"\n• Users Today: {stats.get('users_today', 0)}"
        text += f"\n• Users This Week: {stats.get('users_this_week', 0)}"
    
    if stats.get("total_downloads"):
        text += f"\n\n*Download Stats:*"
        text += f"\n• Total Downloads: {stats['total_downloads']}"
        text += f"\n• Downloads Today: {stats.get('downloads_today', 0)}"
        text += f"\n• Average File Size: {format_bytes(stats.get('avg_file_size', 0))}"
        text += f"\n• Total Data Transferred: {format_bytes(stats.get('total_size', 0))}"
    
    if stats.get("total_errors"):
        text += f"\n\n*Error Stats:*"
        text += f"\n• Total Errors: {stats['total_errors']}"
        text += f"\n• Errors Today: {stats.get('errors_today', 0)}"
    
    text += "\n\n• System Uptime: (Live tracking)"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Back", callback_data="admin_back")]
    ])
    
    await callback_query.message.edit_text(
        text,
        parse_mode=enums.ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


async def show_downloads_list(client: Client, callback_query: CallbackQuery):
    """Show recent downloads."""
    downloads = db.get_recent_downloads(limit=10)
    
    text = """📋 *Recent Downloads*

"""
    
    if downloads:
        for i, download in enumerate(downloads, 1):
            text += f"{i}. `{download['filename']}`\n"
            text += f"   User: {download['user_id']}\n"
            text += f"   Size: {format_bytes(download['file_size'])}\n"
            text += f"   Status: {download['status']}\n\n"
    else:
        text += "No downloads recorded yet."
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Back", callback_data="admin_back")]
    ])
    
    await callback_query.message.edit_text(
        text,
        parse_mode=enums.ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


async def show_users_list(client: Client, callback_query: CallbackQuery):
    """Show active users."""
    users = db.get_active_users(limit=10)
    
    text = """👥 *Active Users*

"""
    
    if users:
        for user in users:
            text += f"• User ID: `{user['user_id']}`\n"
            text += f"  Downloads: {user['download_count']}\n"
            text += f"  Last Active: {user['last_active']}\n\n"
    else:
        text += "No active users."
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Back", callback_data="admin_back")]
    ])
    
    await callback_query.message.edit_text(
        text,
        parse_mode=enums.ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


async def start_broadcast(client: Client, callback_query: CallbackQuery):
    """Start broadcast message setup."""
    text = """📢 *Broadcast Message*

Send the message you want to broadcast to all users.
Type `/cancel` to abort."""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="admin_back")]
    ])
    
    await callback_query.message.edit_text(
        text,
        parse_mode=enums.ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


async def clear_queue(client: Client, callback_query: CallbackQuery, user):
    """Clear download queue."""
    count = db.clear_failed_downloads()
    
    text = f"""🗑️ *Queue Cleared*

Cleared {count} failed downloads from the queue.

*Queue Status:*
• Active Downloads: {db.get_active_downloads()}
• Failed Downloads: 0"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Back", callback_data="admin_back")]
    ])
    
    await callback_query.message.edit_text(
        text,
        parse_mode=enums.ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    
    log_action(user.id, "admin_clear_queue", f"Cleared {count} downloads")


async def show_db_info(client: Client, callback_query: CallbackQuery):
    """Show database information."""
    db_info = db.get_db_info()
    
    text = """📁 *Database Information*

*Tables:*
• Users: {users_count}
• Downloads: {downloads_count}
• Logs: {logs_count}
• Cache: {cache_count}

*Database Size:* {db_size}

*Last Backup:* {last_backup}""".format(
        users_count=db_info.get("users", 0),
        downloads_count=db_info.get("downloads", 0),
        logs_count=db_info.get("logs", 0),
        cache_count=db_info.get("cache", 0),
        db_size=format_bytes(db_info.get("size", 0)),
        last_backup="N/A"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Back", callback_data="admin_back")]
    ])
    
    await callback_query.message.edit_text(
        text,
        parse_mode=enums.ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


async def show_bot_settings(client: Client, callback_query: CallbackQuery):
    """Show bot settings."""
    text = """⚙️ *Bot Settings*

*Current Configuration:*

*Download Settings:*
• Max File Size: {max_size}
• Stream Worker: {stream_worker}

*Upload Settings:*
• Auto-Delete: {auto_delete}
• Delete Delay: {delete_delay}s
• Chunk Size: {chunk_size}

*Channel Settings:*
• Forwarding Enabled: {forwarding}
• Channel ID: {channel_id}""".format(
        max_size=format_bytes(settings.max_file_size),
        stream_worker=settings.stream_worker[:40] + "...",
        auto_delete="Yes" if settings.auto_delete_after_upload else "No",
        delete_delay=settings.auto_delete_delay,
        chunk_size=format_bytes(settings.upload_chunk_size),
        forwarding="Yes" if settings.enable_channel_forwarding else "No",
        channel_id=settings.forward_channel_id or "N/A"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Back", callback_data="admin_back")]
    ])
    
    await callback_query.message.edit_text(
        text,
        parse_mode=enums.ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


async def show_system_status(client: Client, callback_query: CallbackQuery):
    """Show system status."""
    import psutil
    import platform
    
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    
    text = """🔄 *System Status*

*System Info:*
• OS: {os}
• Python: {python}

*Resource Usage:*
• CPU: {cpu}%
• Memory: {memory}%
• Disk: {disk}%

*Bot Status:*
• Status: ✅ Running
• Uptime: (tracking)
• Handlers: Registered""".format(
        os=platform.system(),
        python=platform.python_version(),
        cpu=cpu_percent,
        memory=memory.percent,
        disk=disk.percent
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_system_status"),
         InlineKeyboardButton("🔄 Back", callback_data="admin_back")]
    ])
    
    await callback_query.message.edit_text(
        text,
        parse_mode=enums.ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


async def show_user_details(client: Client, callback_query: CallbackQuery, user_id: int):
    """Show detailed user information."""
    user_info = db.get_user_info(user_id)
    
    if not user_info:
        await callback_query.answer("User not found", show_alert=True)
        return
    
    text = f"""👤 *User Details*

*User ID:* `{user_id}`
*First Download:* {user_info.get('first_seen', 'N/A')}
*Last Active:* {user_info.get('last_seen', 'N/A')}
*Total Downloads:* {user_info.get('download_count', 0)}
*Total Data:* {format_bytes(user_info.get('total_size', 0))}

*Ban Status:* {'🚫 Banned' if user_info.get('banned') else '✅ Active'}"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Back", callback_data="admin_users_list")]
    ])
    
    await callback_query.message.edit_text(
        text,
        parse_mode=enums.ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


def register_admin_panel(app: Client):
    """Register admin panel handlers."""
    
    @app.on_message(filters.command("admin") & filters.private)
    async def admin_command(client: Client, message: Message):
        """Admin panel command - show verification button first."""
        # If user sent '/admin verify' (text) attempt backend verification immediately
        parts = (message.text or "").split()
        admin_ids = [int(aid) for aid in settings.admin_ids.split(",") if aid.strip()]
        admin_username = (settings.admin_username or "").lstrip("@")

        if len(parts) > 1 and parts[1].lower() in ("verify", "verify_admin"):
            user = message.from_user
            if user.id in admin_ids or (admin_username and user.username and user.username.lower() == admin_username.lower()):
                await admin_menu(client, message)
                return
            else:
                await message.reply_text("❌ Access Denied — You are not an admin.", parse_mode=enums.ParseMode.MARKDOWN)
                return

        # Otherwise show a verification prompt with a stylish button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔐 Verify Admin", callback_data="admin_verify")],
            [InlineKeyboardButton("❌ Cancel", callback_data="admin_close")]
        ])

        verify_text = "🛡️ *Admin Access Required*\n\nTap the button below to verify your admin identity and open the control panel.\n\nOr send `/admin verify` to verify via command."

        await message.reply_text(
            verify_text,
            parse_mode=enums.ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
    
    @app.on_callback_query()
    async def admin_callback(client: Client, callback_query: CallbackQuery):
        """Handle all admin callbacks."""
        if callback_query.data.startswith("admin_"):
            # special case: verify
            if callback_query.data == "admin_verify":
                user = callback_query.from_user
                admin_ids = [int(aid) for aid in settings.admin_ids.split(",") if aid.strip()]
                admin_username = (settings.admin_username or "").lstrip("@")

                if user.id in admin_ids or (admin_username and user.username and user.username.lower() == admin_username.lower()):
                    # delete verification message then show menu
                    try:
                        await callback_query.message.delete()
                    except Exception:
                        pass
                    await admin_menu(client, callback_query.message)
                    await callback_query.answer("✅ Verified — Admin menu opened")
                    return
                else:
                    await callback_query.answer("❌ Access Denied — Not an admin", show_alert=True)
                    return

            await handle_admin_callback(client, callback_query)
