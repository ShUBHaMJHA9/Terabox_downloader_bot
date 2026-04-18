import json
import requests
import sys
from pathlib import Path

# Ensure project root is on sys.path when running this script directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import settings

def main():
    token = settings.telegram_bot_token
    if not token:
        print("No bot token found in settings")
        return
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"Error calling getUpdates: {e}")

if __name__ == '__main__':
    main()
