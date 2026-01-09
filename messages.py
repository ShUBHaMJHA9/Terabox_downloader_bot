"""
User-facing messages and strings for the bot.
Centralized management of all bot messages for easy maintenance and localization.
"""

WELCOME_MESSAGE = """
*🤖 Welcome to TeraBox Downloader Bot!*

I can help you download files from TeraBox and similar file-hosting services.

*Quick Start:*
• Send me a TeraBox link
• I'll download and upload it to Telegram
• Progress updates will be sent in real-time

📖 Use /help for all commands.
⚙️ Use /settings to configure preferences."""

HELP_MESSAGE = """
📚 *Available Commands*

*Basic Commands:*
`/start` - Welcome message and quick start guide
`/help` - Show this help message
`/info` - View bot status and statistics
`/cancel` - Cancel an ongoing download/upload
`/status <id>` - Check progress of a specific download

*Settings:*
`/settings` - Configure your preferences

*Admin Commands:*
`/admin` - Admin control panel (admins only)
`/log [lines]` - View recent logs (admins only)

*How to Use:*
1. Send a TeraBox URL (or paste directly)
2. Wait for processing and download
3. File will be uploaded to Telegram
4. Optionally forwarded to configured channel

*File Size Limits:*
Telegram has a 2GB limit for document uploads.
"""

INFO_MESSAGE = """
ℹ️ *Bot Information*

*Status:* 🟢 Online
*Uptime:* {uptime}

*Statistics:*
Total Users: {total_users}
Total Downloads: {total_downloads}
System Memory: {memory}%
System Disk: {disk}%"""

ADMIN_PANEL = """
🔧 *Admin Control Panel*

*Available Actions:*
`/admin broadcast <message>` - Send message to all users
`/admin restart` - Restart the bot
`/admin clear_queue` - Clear pending tasks
`/admin stats` - Detailed statistics
`/admin users` - List active users

Use: `/admin <command> [args]`
"""

DOWNLOAD_START = """
📥 *Download Started*

*File:* {filename}
*Size:* {filesize}
*Source:* TeraBox

Processing... Please wait.
"""

DOWNLOAD_PROGRESS = """
📊 *Download Progress*

*Progress:* {progress}% ({current}/{total})
⏱️ *ETA:* {eta}
*Speed:* {speed}

[{'█' * int(progress/10)}{' ' * (10 - int(progress/10))}]
"""

UPLOAD_PROGRESS = """
📤 *Upload to Telegram*

*Progress:* {progress}% ({current}/{total})
⏱️ *ETA:* {eta}
*Speed:* {speed}
"""

DOWNLOAD_COMPLETE = """
✅ *Download & Upload Complete!*

*File:* {filename}
*Size:* {filesize}
*Time Taken:* {time_taken}

📌 Your file is ready to download from Telegram!
"""

ERROR_INVALID_URL = """
❌ *Invalid URL*

Please send a valid TeraBox or supported file-hosting URL.

Supported services:
• TeraBox
• Mega (coming soon)
• Google Drive (coming soon)

Try again with a valid link.
"""

ERROR_DOWNLOAD_FAILED = """
❌ *Download Failed*

*Error:* {error_message}

Possible reasons:
• URL expired or removed
• File deleted by owner
• Network connectivity issue
• File too large (>2GB for Telegram)

Use `/help` for more information.
"""

ERROR_UPLOAD_FAILED = """
❌ *Upload to Telegram Failed*

*Error:* {error_message}

The file was downloaded but couldn't be uploaded to Telegram.

Possible reasons:
• File too large (>2GB)
• Telegram server issues
• Network disconnection

Try again later or contact admins.
"""

ADMIN_ONLY = """
🔒 *Admin Access Required*

This command is restricted to bot administrators only.

If you need admin access, contact the bot owner.
"""

SETTINGS_MESSAGE = """
⚙️ *User Settings*

*Current Preferences:*
🔔 Notifications: {notifications}
📺 Quality: {quality}
📝 Auto-Archive: {auto_archive}

*Change Settings:*
`/settings notifications on/off`
`/settings quality high/medium/low`
`/settings archive on/off`

_More options coming soon!_
"""

CANCEL_CONFIRMED = """
✅ *Download Cancelled*

The current download/upload has been cancelled.
"""

CANCEL_NOT_FOUND = """
❌ *No Active Download*

There's no ongoing download to cancel.
"""

RATE_LIMIT_WARNING = """
⚠️ *Rate Limit Warning*

You've reached your download limit for this hour.

Limit: {limit} downloads/hour
Current: {current} downloads

Please wait: {wait_time} seconds
"""

FORWARDING_NOTICE = """
📢 This file has also been forwarded to the channel: {channel_name}
"""

SETTINGS_SAVED = """
✅ *Settings Saved*

Your preferences have been updated successfully.
"""

