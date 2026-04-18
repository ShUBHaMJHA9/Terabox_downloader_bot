"""
Handler that processes messages from a dedicated image+link group.
- Extracts all TeraBox links from a single message
- Downloads each video using existing pipeline
- Uploads a backup copy to `settings.database_channel` and stores a cached record
- Publishes a public-channel post with deep-link to the bot for user access

This handler is intentionally separate from `channel_forwarder` per user request.
"""

import asyncio
import tempfile
import json
import requests
from pathlib import Path
import re
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import settings
from utils.logger import logger
from utils.database import db
from utils.telegram import TelegramUploader
from utils.helpers import format_bytes
from downloader.terabox_api import get_terabox_api
from downloader.aria2_downloader import aria2_download
from downloader.parallel_downloader import parallel_download


TERABOX_URL_RE = r"https?://(?:terabox\.com|teraboxlink\.com)/\S+"


def extract_link_labels(text: str, links: list) -> dict:
    """
    Extract labels for each link from text (e.g., 'v1', 'v2', 'Part 1', etc.)
    Returns dict: {link_url: label_text}
    """
    link_labels = {}
    
    for link in links:
        # Look for pattern near the link: v1, v2, Part 1, etc.
        # Search within 50 chars before/after the link
        idx = text.find(link)
        if idx == -1:
            link_labels[link] = "Video"
            continue
        
        # Look backwards for label patterns
        before = text[max(0, idx-50):idx]
        after = text[idx+len(link):min(len(text), idx+len(link)+50)]
        
        context = before + after
        
        # Match patterns: v1, v2, part 1, part 2, version 1, etc.
        match = re.search(r'\b(v|version|part|ep|episode)[\s_-]*(\d+|[a-z])\b', context, re.IGNORECASE)
        if match:
            label = f"{match.group(1).upper()} {match.group(2)}"
            link_labels[link] = label
        else:
            # Default label
            link_labels[link] = f"Video {len(link_labels) + 1}"
    
    return link_labels


async def process_message_links(client: Client, message: Message):
    """Process all TeraBox links in a single message."""
    # Only handle messages from configured group
    if not settings.image_source_group:
        return
    
    # Handle both regular group ID and supergroup ID format
    configured_id = settings.image_source_group
    actual_id = message.chat.id
    
    # Check if this is the right group (handle -100XXXXX format for supergroups)
    if actual_id != configured_id:
        # Try converting: if configured is 123, also accept -100000000123 or -123
        if not (str(actual_id).lstrip('-') == str(configured_id).lstrip('-')):
            return
    
    logger.info(f"[GroupProcessor] Message in group {actual_id}: chat_type={message.chat.type}, msg_id={message.id}")

    text = (message.text or message.caption or "")
    if not text:
        logger.info(f"[GroupProcessor] Message {message.id} has no text/caption, skipping")
        return

    links = re.findall(TERABOX_URL_RE, text)
    if not links:
        logger.info(f"[GroupProcessor] Message {message.id} has no TeraBox links")
        return

    logger.info(f"[GroupProcessor] ✅ Found {len(links)} terabox link(s) in message {message.id}")

    # Extract labels for each link (v1, v2, part 1, etc.)
    link_labels = extract_link_labels(text, links)
    logger.info(f"[GroupProcessor] Link labels: {link_labels}")


    # Determine thumbnail file if photo or thumbnail exists
    thumb_file = None
    try:
        if message.photo:
            thumb_file = Path(tempfile.gettempdir()) / f"thumb_{message.id}.jpg"
            await message.download(file_name=str(thumb_file))
        elif message.document and message.document.mime_type and message.document.mime_type.startswith("image"):
            thumb_file = Path(tempfile.gettempdir()) / f"thumb_{message.id}.jpg"
            await message.download(file_name=str(thumb_file))
    except Exception as e:
        logger.warning(f"[GroupProcessor] Failed to download thumbnail: {e}")
        thumb_file = None

    terabox_api = get_terabox_api()
    uploader = TelegramUploader(client)

    # Dict to track processed records for button creation later
    processed_records = {}  # {link: {label, record_id, filename, filesize}}

    for idx, link in enumerate(links, start=1):
        try:
            # Skip if already processed from this group+message
            is_processed = db.is_group_message_processed(actual_id, message.id, link)
            if is_processed:
                logger.info(f"[GroupProcessor] Link already processed from this message: {link}")
                continue

            logger.info(f"[GroupProcessor] ✅ Processing link ({idx}/{len(links)}): {link}")
            api_data = await terabox_api.get_download_info(link, 0)
            if not api_data or not api_data.get("direct_link"):
                logger.warning(f"[GroupProcessor] Failed to get direct link for {link}")
                continue

            direct_link = api_data.get("direct_link")
            thumbnail_url = api_data.get("thumbnail")
            filename = api_data.get("filename", "download")
            file_size = int(api_data.get("size", 0))
            
            # Get label for this link
            link_label = link_labels.get(link, f"Video {idx}")
            
            # Save to database as processed
            db.save_group_message_processed(
                chat_id=actual_id,
                message_id=message.id,
                terabox_link=link,
                filename=filename,
                filesize=file_size,
                thumb_path=str(thumb_file) if thumb_file else "",
                link_label=link_label
            )

            # Create temp file
            temp_dir = Path(tempfile.gettempdir()) / "terabox_bot_group"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file = temp_dir / f"group_{message.id}_{idx}.tmp"

            # Download using aria2 if available, else parallel
            success = await aria2_download(
                url=direct_link,
                output_path=temp_file,
                progress_callback=None,
                max_connections=settings.aria2_connections,
                split_count=settings.aria2_connections,
                max_conn_per_server=max(1, settings.aria2_connections // 4),
                min_split_size="1M"
            )

            if not success:
                success = await parallel_download(
                    url=direct_link,
                    output_path=temp_file,
                    progress_callback=None,
                    num_threads=settings.parallel_threads
                )

            if not success or not temp_file.exists() or temp_file.stat().st_size == 0:
                logger.warning(f"[GroupProcessor] Download failed for link: {link}")
                continue

            # Upload backup to database channel
            if settings.database_channel:
                caption = f"*{filename}*\n\nSize: {format_bytes(file_size)}\n📦 Backup copy\n\n🔗 Source: {link}"
                backup_msg = await uploader.upload_video(
                    chat_id=settings.database_channel,
                    file_path=str(temp_file),
                    caption=caption,
                    thumbnail_path=str(thumb_file) if thumb_file and thumb_file.exists() else None,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                backup_channel_id = settings.database_channel
                backup_message_id = backup_msg.id if backup_msg else None
            else:
                backup_channel_id = None
                backup_message_id = None

            # Save cached record
            record_id = db.add_cached_video(
                source_chat_id=message.chat.id,
                source_message_id=message.id,
                terabox_link=link,
                filename=filename,
                filesize=file_size,
                thumb_path=str(thumb_file) if thumb_file and thumb_file.exists() else None,
                backup_channel_id=backup_channel_id,
                backup_message_id=backup_message_id
            )

            logger.info(f"[GroupProcessor] Cached link id={record_id} (backup msg={backup_message_id})")
            
            # Track for button creation
            processed_records[link] = {
                "label": link_label,
                "record_id": record_id,
                "thumbnail": thumbnail_url,
                "filename": filename,
                "filesize": file_size
            }

            # Clean up temp file
            try:
                temp_file.unlink()
            except:
                pass

        except Exception as e:
            logger.error(f"[GroupProcessor] Error processing link {link}: {e}", exc_info=True)

    # After all links processed, create ONE public channel post with all buttons
    if processed_records and settings.public_channel_id:
        logger.info(f"[GroupProcessor] Creating public post with {len(processed_records)} videos")
        
        post_text = f"🎬 New video(s) from source\n\n"
        post_text += f"Total videos: {len(processed_records)}\n\n"
        
        # Add details for each video
        for idx, (link, info) in enumerate(processed_records.items(), start=1):
            label = info["label"]
            fname = info["filename"]
            fsize = info["filesize"]
            post_text += f"**{label}**: {fname} — {format_bytes(fsize)}\n"
        
        # Build buttons with labels
        buttons = []
        for link, info in processed_records.items():
            label = info["label"]
            record_id = info["record_id"]
            # Create button with the extracted label
            buttons.append([InlineKeyboardButton(f"▶ {label}", url=f"https://t.me/{settings.bot_username}?start=video_{record_id}")])
        
        # Send post with thumbnail
        try:
            # Build reply_markup as JSON for Bot API
            reply_markup = {"inline_keyboard": []}
            for b in buttons:
                # each b is InlineKeyboardButton; convert to dict
                row = []
                for btn in b:
                    row.append({"text": btn.text, "url": btn.url})
                reply_markup["inline_keyboard"].append(row)

            bot_token = settings.telegram_bot_token
            api_url = f"https://api.telegram.org/bot{bot_token}"

            if thumb_file and thumb_file.exists():
                # sendPhoto using local file: use multipart upload
                files = {"photo": open(str(thumb_file), "rb")}
                data = {
                    "chat_id": settings.public_channel_id,
                    "caption": post_text,
                    "parse_mode": "Markdown",
                    "reply_markup": json.dumps(reply_markup)
                }
                resp = requests.post(f"{api_url}/sendPhoto", data=data, files=files, timeout=30)
            else:
                # use sendPhoto with thumbnail URLs if available in processed_records
                # choose first available thumbnail
                thumb_url = None
                for info in processed_records.values():
                    if info.get("thumbnail"):
                        thumb_url = info.get("thumbnail")
                        break

                if thumb_url:
                    data = {
                        "chat_id": settings.public_channel_id,
                        "photo": thumb_url,
                        "caption": post_text,
                        "parse_mode": "Markdown",
                        "reply_markup": json.dumps(reply_markup)
                    }
                    resp = requests.post(f"{api_url}/sendPhoto", data=data, timeout=30)
                else:
                    data = {
                        "chat_id": settings.public_channel_id,
                        "text": post_text,
                        "parse_mode": "Markdown",
                        "reply_markup": json.dumps(reply_markup)
                    }
                    resp = requests.post(f"{api_url}/sendMessage", data=data, timeout=30)

            if resp.status_code == 200:
                logger.info(f"[GroupProcessor] ✅ Published post to PUBLIC_CHANNEL with {len(buttons)} buttons")
            else:
                logger.warning(f"[GroupProcessor] Failed to publish to public channel: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.warning(f"[GroupProcessor] Failed to publish to public channel: {e}")


def register_group_processor(app: Client):
    """Register handler for configured image source group."""
    
    if not settings.image_source_group:
        logger.warning("[GroupProcessor] IMAGE_SOURCE_GROUP not configured, skipping group processor registration")
        return
    
    logger.info(f"[GroupProcessor] Registering handler for group: {settings.image_source_group}")

    @app.on_message(filters.chat(settings.image_source_group) & (filters.photo | filters.document | filters.text))
    async def _group_handler(client: Client, message: Message):
        logger.info(f"[GroupProcessor] Received message in group {message.chat.id}: type={message.media}, has_text={bool(message.text or message.caption)}")
        asyncio.create_task(process_message_links(client, message))