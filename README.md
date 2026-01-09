"""
README - TeraBox Downloader Bot
Professional Telegram bot for downloading files from TeraBox and similar services.
"""

# 🤖 TeraBox Downloader Bot

A professional, modular, and scalable Telegram bot for downloading files from TeraBox and similar file-hosting services with real-time progress tracking, admin controls, and comprehensive logging.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Telegram](https://img.shields.io/badge/Telegram-Bot-blue)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Features

### 🎯 Core Functionality
- ✅ Accept TeraBox URLs from Telegram users
- ✅ Real-time progress tracking for downloads and uploads
- ✅ Direct streaming via CloudFlare Workers
- ✅ Error handling and validation
- ✅ Optional channel forwarding
- ✅ File caching for repeated downloads

### 📊 Commands
- `/start` – Welcome & quick start
- `/help` – Command list
- `/info` – Bot statistics
- `/settings` – User preferences
- `/cancel` – Cancel download
- `/status` – Check progress
- `/admin` – Admin panel (restricted)
- `/log` – View logs (admin only)

### 🔐 Admin Features
- Broadcast messages to all users
- View detailed statistics
- Manage download queue
- Access system logs
- Restart bot

### 📝 Logging & Monitoring
- Dual output (file + console with colors)
- SQLite database for tracking
- User activity logging
- Error tracking and reporting

### 🏗️ Architecture
- **Modular design** – Easy to extend and maintain
- **Async/await** – High performance with asyncio
- **Type hints** – Better code clarity
- **Configurable** – Environment variables for all settings
- **Production-ready** – Ready for deployment

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Telegram Bot Token (from @BotFather)
- Telegram API ID & Hash (from https://my.telegram.org)
- CloudFlare Worker (for streaming)

### Installation

```bash
# Clone repository
git clone <your-repo>
cd Terabox_downloader_bot

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
nano .env  # Add your credentials

# Run bot
python main.py
```

### Configuration

Edit `.env`:

```env
# Required
TELEGRAM_API_ID=123456789
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_BOT_TOKEN=your_bot_token
CLOUDFLARE_WORKER_URL=https://your-worker.workers.dev

# Admin
ADMIN_IDS=123456789,987654321

# Optional
ENABLE_CHANNEL_FORWARDING=true
FORWARD_CHANNEL_ID=-1001234567890
ENABLE_FILE_CACHING=true
LOG_LEVEL=INFO
```

---

## 📁 Project Structure

```
Terabox_downloader_bot/
├── main.py                    # Bot entry point
├── config.py                  # Configuration
├── messages.py                # All bot messages
├── requirements.txt           # Dependencies
├── .env.example               # Example env vars
├── cloudflare_worker.js       # Worker script
├── DEPLOYMENT.md              # Deployment guide
├── handlers/
│   ├── commands.py            # User commands
│   ├── admin.py               # Admin commands
│   └── download.py            # Download handler
├── downloader/
│   └── manager.py             # TeraBox downloader
├── utils/
│   ├── logger.py              # Logging
│   ├── database.py            # SQLite manager
│   ├── telegram.py            # Telegram utilities
│   └── helpers.py             # Helper functions
└── data/
    └── bot.db                 # Database
```

---

## 🎮 Usage

### As a User

1. **Start** – Send `/start` to get welcome message
2. **Send URL** – Paste a TeraBox link in chat
3. **Wait** – Bot downloads and uploads to Telegram
4. **Download** – Get file from Telegram

### As an Admin

1. **Broadcast** – `/admin broadcast Hello everyone!`
2. **Stats** – `/admin stats` to view statistics
3. **Logs** – `/admin log 100` to see last 100 log lines
4. **Queue** – `/admin clear_queue` to clear pending tasks

---

## 🔧 Deployment

### PythonAnywhere
```bash
# Upload code, create scheduled task
python main.py
```

### Heroku
```bash
git push heroku main
heroku logs --tail
```

### Docker
```bash
docker build -t terabox-bot .
docker run -e TELEGRAM_BOT_TOKEN="..." terabox-bot
```

### Linux (Systemd)
```bash
sudo systemctl enable terabox-bot
sudo systemctl start terabox-bot
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions.

---

## 📊 Database Schema

### Users Table
```sql
- user_id (PRIMARY KEY)
- username, first_name, last_name
- joined_at, last_active
- total_downloads
- settings (JSON)
```

### Downloads Table
```sql
- download_id (PRIMARY KEY)
- user_id (FK)
- url, filename, filesize
- status (pending/downloading/uploading/completed/failed)
- progress (0-100)
- started_at, completed_at
- error_message
```

### Activity Logs Table
```sql
- log_id (PRIMARY KEY AUTOINCREMENT)
- user_id (FK), action, details, level
- created_at
```

---

## 🛡️ Security

- ✅ URL validation (TeraBox only by default)
- ✅ Admin-only commands with access control
- ✅ Secure credential storage (environment variables)
- ✅ Error handling without exposing sensitive info
- ✅ User input validation

---

## 🔮 Future Enhancements

- [ ] Multi-host support (Google Drive, Mega, MediaFire)
- [ ] Video compression/conversion
- [ ] User quotas & rate limiting
- [ ] Download retry with exponential backoff
- [ ] Inline buttons for quick actions
- [ ] Multi-language support
- [ ] PostgreSQL for production
- [ ] Advanced analytics
- [ ] Webhook support for scalability

---

## 📝 Code Quality

- **Python 3.11+** with modern async patterns
- **Type hints** throughout
- **Docstrings** for all functions and classes
- **Modular design** for easy extension
- **Error handling** with clear messages
- **Logging** at appropriate levels

---

## 🐛 Troubleshooting

### Bot won't start
```bash
# Check credentials
python -c "from config import settings; print(settings.telegram_api_id)"

# Check logs
tail -f logs/bot.log
```

### Downloads fail
- Verify CloudFlare Worker is running
- Check worker URL in `.env`
- Test: `curl https://your-worker.workers.dev/status`

### Database issues
```bash
rm data/bot.db  # Reset (bot recreates on start)
```

---

## 📚 Additional Resources

- [Pyrogram Documentation](https://docs.pyrogram.org)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [CloudFlare Workers](https://workers.cloudflare.com)

---

## 📄 License

MIT License – See LICENSE file for details

---

## 🤝 Contributing

Contributions are welcome! Feel free to:
- Report bugs
- Suggest features
- Submit pull requests
- Improve documentation

---

## 📧 Support

For issues:
1. Check logs: `tail logs/bot.log`
2. Verify `.env` configuration
3. Check CloudFlare Worker status
4. Review error messages

---

**Made with ❤️ by TeraBox Bot Team**

⭐ If you find this useful, please star the repo!
