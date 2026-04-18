import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
BOT_USERNAME = os.getenv("BOT_USERNAME", "TeraBoX_dlFree_bot")

VIDEO_ID = 41

IMAGE_URL = "https://data.1024tera.com/thumbnail/df651c6eb606f09c0d7c01bcf87f3481?fid=4398797378060-250528-206447717977347&time=1776535200&rt=sh&sign=FDTAER-DCb740ccc5511e5e8fedcff06b081203-P%2FZIyCPmic%2B%2BK6x3ubwztivAJSY%3D&expires=8h&chkv=0&chkbd=0&chkpc=&dp-logid=201655383753334861&dp-callid=0&size=c360_u270&quality=100&vuk=-&ft=video"

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

payload = {
    "chat_id": CHANNEL_ID,
    "caption": "🔥 Test Post (Terabox)",
    "reply_markup": json.dumps({
        "inline_keyboard": [[
            {
                "text": "📥 Get Video",
                "url": f"https://t.me/{BOT_USERNAME}?start=video_{VIDEO_ID}"
            }
        ]]
    }),
    "photo": IMAGE_URL
}

response = requests.post(url, data=payload)

print("Status:", response.status_code)
print("Response:", response.text)