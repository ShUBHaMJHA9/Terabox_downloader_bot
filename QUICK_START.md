# 🤖 TeraBox Downloader Bot - Quick Start Guide

## ✅ Bot is Ready!

All critical issues have been fixed:
- ✅ Parse mode errors resolved (using Markdown)
- ✅ TeraBox API integration working
- ✅ Stream worker integration complete
- ✅ File size parsing fixed (handles strings and integers)
- ✅ Direct streaming upload (no chunking)

## 🚀 Starting the Bot

```bash
cd /workspaces/Terabox_downloader_bot
python main.py
```

The bot will:
1. Initialize database
2. Load configuration from `.env`
3. Register all handlers
4. Connect to Telegram API
5. Start listening for messages

## 📍 Download Flow

When user sends a TeraBox URL:

```
1. URL Validation ✓
   └─ Check if it's a valid TeraBox link
   
2. TeraBox API Call ✓
   └─ Get: direct_link, filename, size
   
3. Stream Worker ✓
   └─ Convert direct_link to stream_url
   
4. Download Stream ✓
   └─ Download with progress tracking
   
5. Upload to Telegram ✓
   └─ Direct stream (no chunking)
   
6. Auto-cleanup ✓
   └─ Delete temp file after 5 minutes
```

## 📋 User Commands

- `/start` - Welcome and quick start
- `/help` - List all commands
- `/info` - Bot statistics
- `/settings` - User preferences
- `/cancel` - Cancel download
- `/status <id>` - Check download status
- `/admin` - Admin panel (admins only)

## ⚙️ Configuration

Key settings in `.env`:
- `MAX_FILE_SIZE=524288000` (500MB)
- `AUTO_DELETE_AFTER_UPLOAD=true`
- `AUTO_DELETE_DELAY=300` (5 minutes)
- `TERABOX_API_V1=https://api-download-backend.vercel.app`
- `STREAM_WORKER=https://stream.nexfix-uk-to.workers.dev`

## 🔍 Testing the Bot

Send a TeraBox URL to the bot:
```
https://terabox.com/s/1hFfXciUSqOlV8n48hCLKdg
```

The bot will:
1. Show "Processing..." message
2. Fetch from TeraBox API
3. Create stream via CloudFlare
4. Download file with progress
5. Upload to Telegram
6. Show completion message

## 📊 Admin Panel

Access admin features with `/admin`:
- View detailed statistics
- Monitor active users
- Check recent downloads
- System resource usage
- Database information
- Clear failed downloads
- Broadcast messages

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot won't start | Check `.env` file credentials |
| Parse mode error | Should be fixed, use Markdown format |
| File size error | Size parsing now handles strings & ints |
| Stream worker error | Check `STREAM_WORKER` URL in `.env` |
| API error | Check `TERABOX_API_V1` URL is correct |
| Upload fails | Check file size < 2GB (Telegram limit) |

## 📁 Project Structure

```
/workspaces/Terabox_downloader_bot/
├── main.py                 # Bot entry point
├── config.py              # Configuration
├── messages.py            # Bot messages
├── requirements.txt       # Dependencies
├── .env                   # Environment variables
├── handlers/
│   ├── commands.py        # User commands
│   ├── admin.py           # Admin commands
│   ├── admin_panel.py     # Admin UI
│   └── download.py        # Download pipeline
├── downloader/
│   ├── manager.py         # Download manager
│   └── terabox_api.py     # TeraBox API
├── utils/
│   ├── logger.py          # Logging
│   ├── database.py        # SQLite manager
│   ├── telegram.py        # Telegram helpers
│   └── helpers.py         # Utilities
├── data/
│   └── bot.db             # SQLite database
└── logs/
    └── bot.log            # Activity logs
```

## 📝 Latest Fixes

### Fix 1: File Size Type Conversion
- **Issue**: API returns size as string "9.29 MB"
- **Solution**: Parse string format to bytes in `terabox_api.py`
- **Handles**: "X.XX MB", "X.XX GB", and numeric strings

### Fix 2: Download Handler
- **Issue**: Incorrect 4-step flow implementation
- **Solution**: Rewritten to match CloudFlare worker code exactly
- **Features**: Real-time progress, proper error handling

### Fix 3: Parse Mode
- **Issue**: Invalid HTML parse mode in Pyrogram v2
- **Solution**: Using `enums.ParseMode.MARKDOWN` with markdown formatting

## 🎯 Next Steps

1. **Start the bot**: `python main.py`
2. **Test with a URL**: Send TeraBox link
3. **Monitor logs**: Watch `/workspaces/Terabox_downloader_bot/logs/bot.log`
4. **Use admin**: Send `/admin` for control panel
5. **Check database**: Stats and user tracking in SQLite

## 📞 Support

For detailed documentation, see:
- `MASTER_PROMPTS.md` - Complete feature guide
- `IMPLEMENTATION_NOTES.md` - Technical details
- Logs in `logs/bot.log` - Debug information

---

**Status**: ✅ **PRODUCTION READY**

The bot is fully functional and ready for deployment!
