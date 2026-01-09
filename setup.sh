#!/bin/bash

# TeraBox Downloader Bot - Quick Setup Script

echo "🤖 TeraBox Downloader Bot - Setup"
echo "=================================="
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $PYTHON_VERSION"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3.11 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate 2>/dev/null || . venv/Scripts/activate

echo "✓ Virtual environment activated"

# Install dependencies
echo "📥 Installing dependencies..."
pip install -q -r requirements.txt

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚙️ Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env with your credentials:"
    echo "   - TELEGRAM_API_ID"
    echo "   - TELEGRAM_API_HASH"
    echo "   - TELEGRAM_BOT_TOKEN"
    echo "   - CLOUDFLARE_WORKER_URL"
    echo ""
    echo "🔗 Get credentials from:"
    echo "   - Bot token: @BotFather on Telegram"
    echo "   - API ID/Hash: https://my.telegram.org"
    echo ""
    echo "Exit and edit .env, then run: python main.py"
else
    echo "✓ .env file already exists"
fi

# Create required directories
echo "📁 Creating required directories..."
mkdir -p data logs cache sessions

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env with your credentials"
echo "2. Deploy CloudFlare Worker (see cloudflare_worker.js)"
echo "3. Update CLOUDFLARE_WORKER_URL in .env"
echo "4. Run: python main.py"
echo ""
echo "For more help, see: README.md or DEPLOYMENT.md"
