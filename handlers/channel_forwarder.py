"""
Channel forwarder handler - Auto-forwards messages from source channels to target channels.
Extracts TeraBox links, auto-downloads, and stores in database channel.

Flow:
1. Listen to SOURCE_CHANNELS for new messages
2. Extract TeraBox links from message text
3. Forward message to TARGET_CHANNEL
4. If TeraBox link found:
   - Auto-download the video
   - Upload to TARGET_CHANNEL (if not document)
   - Store backup in DATABASE_CHANNEL
"""

import re
import asyncio
import tempfile
import shutil
import gc
from pathlib import Path
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import os
import requests
import json
from config import settings
from utils.logger import logger, log_action, log_error
from utils.telegram import TelegramUploader
from utils.helpers import format_bytes, extract_url_from_text
from downloader.manager import downloader
from downloader.terabox_api import get_terabox_api
from utils.database import db


def cleanup_temp_files(temp_dir: Path = None):
    """
    Aggressively cleanup temporary files and force garbage collection.
    
    Args:
        temp_dir: If specified, cleanup this directory. Otherwise cleanup default temp.
    """
    try:
        if temp_dir is None:
            temp_dir = Path(tempfile.gettempdir()) / "terabox_bot"
        
        if temp_dir.exists():
            for file in temp_dir.glob("*"):
                try:
                    if file.is_file():
                        file.unlink()
                        logger.debug(f"[Cleanup] Deleted: {file}")
                    elif file.is_dir():
                        shutil.rmtree(file)
                        logger.debug(f"[Cleanup] Deleted dir: {file}")
                except Exception as e:
                    logger.debug(f"[Cleanup] Failed to delete {file}: {e}")
        
        # Force garbage collection
        gc.collect()
        logger.debug(f"[Cleanup] ✅ Temp files cleaned and garbage collected")
    except Exception as e:
        logger.warning(f"[Cleanup] ⚠️  Error during cleanup: {e}")


# Comprehensive list of TeraBox domains and mirrors (2024-2025)
# Includes official domains, mirrors, and regional variants
TERABOX_DOMAINS = [
    # Official & primary domains
    'terabox.com',
    'terabox.app',
    'teraboxshare.com',
    'teraboxlink.com',
    'teraboxurl.com',
    'teraboxapp.com',

    # Known mirrors / alternates
    'nephobox.com',
    'mirrobox.com',
    '4funbox.com',
    'momerybox.com',
    'memoryboxcloud.com',
    'cloudbox.com',
    'gibibox.com',
    'goaibox.com',
    'hugebox.com',
    'tbcloudstorage.com',
    'gobigcloud.com',
    'terafileshare.com',
    'terasharefile.com',
    'terasharelink.com',

    # 1024 / CN based mirrors
    '1024tera.com',
    '1024terabox.com',
    '1024tb.com',
    '1024box.com',
    '1024share.com',

    # Recent short or regional mirrors (found 2024–2025)
    'gobigbox.com',
    'myterabox.com',
    'teradisk.com',
    'terafilelink.com',
    'terastoragebox.com',
    'bigterabox.com',
    'teraboxcdn.com',
    'teraboxshare.net',
    'teraboxmirror.com',
    'teraboxstorage.com',
    'teraboxfiles.com',
    
    # Additional variants with subdomains
    'smart.terabox.com',
    'pan.terabox.com',
    'dl.terabox.com',
    'share.terabox.com',
]

# Build regex patterns dynamically from domain list
def _build_terabox_patterns():
    """Build regex patterns from domain list."""
    patterns = []
    for domain in TERABOX_DOMAINS:
        # Handle subdomains (smart.terabox.com -> smart\.terabox\.com)
        # and top-level domains
        domain_escaped = domain.replace('.', r'\.')
        # Match: https://[www.]domain/[s/][share-id] or just the domain for validation
        patterns.append(rf'https?://(?:www\.)?{domain_escaped}/s/[a-zA-Z0-9\-_]+')
    return patterns

# Regex patterns for TeraBox URLs - all known domains
TERABOX_URL_PATTERNS = _build_terabox_patterns()

# For URL validation (checking if domain is TeraBox)
TERABOX_DOMAIN_PATTERNS = [rf'https?://(?:www\.)?{domain.replace(".", r"\.")}/' for domain in TERABOX_DOMAINS]


def is_terabox_link(url: str) -> bool:
    """
    Check if URL is a valid TeraBox link (any domain).
    Supports all known TeraBox domains and mirrors.
    
    Args:
        url: URL to check
        
    Returns:
        True if URL is a TeraBox link, False otherwise
    """
    if not url:
        return False
    
    # Check against link patterns (with /s/ path)
    for pattern in TERABOX_URL_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    
    # Also check domain patterns (for other paths)
    for pattern in TERABOX_DOMAIN_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    
    return False


def botapi_send_photo(chat_id: int, photo: str, caption: str = None, reply_markup: dict = None):
    """Send photo via Telegram Bot HTTP API. Returns result dict or None."""
    try:
        bot_token = settings.telegram_bot_token
        api_url = f"https://api.telegram.org/bot{bot_token}"

        if photo and os.path.exists(photo):
            with open(photo, 'rb') as f:
                files = {"photo": f}
                data = {
                    "chat_id": chat_id,
                    "caption": caption,
                    "parse_mode": "Markdown",
                }
                if reply_markup:
                    data["reply_markup"] = json.dumps(reply_markup)
                resp = requests.post(f"{api_url}/sendPhoto", data={k: v for k, v in data.items() if v is not None}, files=files, timeout=60)
        else:
            data = {
                "chat_id": chat_id,
                "photo": photo,
                "caption": caption,
                "parse_mode": "Markdown",
            }
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup)
            resp = requests.post(f"{api_url}/sendPhoto", data={k: v for k, v in data.items() if v is not None}, timeout=60)

        if resp.status_code == 200:
            return resp.json().get("result")
        else:
            logger.warning(f"[BotAPI] sendPhoto failed: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.warning(f"[BotAPI] sendPhoto exception: {e}")
    return None


def botapi_send_message(chat_id: int, text: str, reply_markup: dict = None):
    try:
        bot_token = settings.telegram_bot_token
        api_url = f"https://api.telegram.org/bot{bot_token}"
        data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        resp = requests.post(f"{api_url}/sendMessage", data=data, timeout=60)
        if resp.status_code == 200:
            return resp.json().get("result")
        else:
            logger.warning(f"[BotAPI] sendMessage failed: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.warning(f"[BotAPI] sendMessage exception: {e}")
    return None


def extract_terabox_links(text: str) -> list:
    """
    Extract all TeraBox links from text.
    
    Args:
        text: Text to search
        
    Returns:
        List of unique TeraBox URLs found
    """
    if not text:
        return []
    
    found_links = []
    
    # Search with all patterns
    for pattern in TERABOX_URL_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        found_links.extend(matches)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_links = []
    for link in found_links:
        link_lower = link.lower()
        if link_lower not in seen:
            seen.add(link_lower)
            unique_links.append(link)
    
    return unique_links


async def process_terabox_link(client: Client, link: str, source_message: Message, target_chat_id: int, db_channel_id: int) -> bool:
    """
    Process a TeraBox link: download, backup, and upload with source link button.
    
    Args:
        client: Pyrogram client
        link: TeraBox URL
        source_message: Original message from source channel
        target_chat_id: Target channel to upload to
        db_channel_id: Database channel for backup
    
    Returns:
        True if link was successfully downloaded and uploaded, False otherwise
    """
    try:
        download_id = re.sub(r'[^a-zA-Z0-9]', '', link[-20:])  # Generate ID from URL
        logger.info(f"[Channel Forwarder] Processing TeraBox link: {link}")
        logger.info(f"[Channel Forwarder] Source message ID: {source_message.id}, Chat: {source_message.chat.id}")
        
        # Step 1: Get download info from TeraBox API
        terabox_api = get_terabox_api()
        api_data = await terabox_api.get_download_info(link, 0)  # user_id=0 for channel forwarding
        
        if not api_data or not api_data.get("direct_link"):
            logger.warning(f"[Channel Forwarder] Failed to fetch info from TeraBox API")
            return False
        
        direct_link = api_data.get("direct_link")
        filename = api_data.get("filename", "download")
        file_size = int(api_data.get("size", 0))
        thumbnail_url = api_data.get("thumbnail")
        title = api_data.get("title", filename)
        
        logger.info(f"[Channel Forwarder] Got info: {filename}, size={file_size}")
        
        # Check file size limit
        if file_size > settings.max_file_size:
            logger.warning(f"[Channel Forwarder] File too large: {file_size} > {settings.max_file_size}")
            return False
        
        # Step 2-3: Download directly from API's direct_link (it's already valid)
        # Don't waste time creating a stream - the API link is ready to use!
        logger.info(f"[Channel Forwarder] Downloading directly from API link (expires in ~8h)...")
        
        temp_dir = Path(tempfile.gettempdir()) / "terabox_bot"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = temp_dir / f"{download_id}.tmp"
        
        # Just try to download directly - the direct_link from API is valid!
        download_succeeded = False
        try:
            success = await downloader.download(
                download_id=download_id,
                stream_url=direct_link,  # Use the direct API link directly!
                output_path=temp_file,
                user_id=0
            )
            
            if success and temp_file.exists() and temp_file.stat().st_size > 0:
                logger.info(f"[Channel Forwarder] ✅ Downloaded {format_bytes(temp_file.stat().st_size)}")
                download_succeeded = True
                    
        except Exception as e:
            logger.warning(f"[Channel Forwarder] Download error: {e}")
        
        if not download_succeeded:
            logger.warning(f"[Channel Forwarder] ⚠️  Download failed")
            logger.info(f"[Channel Forwarder] 💡 Creating stub message with link instead...")
            
            # Resolve target channel entity before sending
            try:
                await client.get_chat(settings.target_channel)
            except Exception:
                logger.debug(f"[Channel Forwarder] Resolving target channel via dialogs...")
                async for dialog in client.get_dialogs():
                    if dialog.chat.id == settings.target_channel:
                        break
            
            # Don't upload the video, but send a message with the link so user can try manually
            try:
                stub_caption = f"*{filename}*\n\n📊 Size: {format_bytes(file_size)}\n\n⚠️ Auto-download failed\n🔗 [Open in TeraBox]({link})\n\n🤖 Auto message from TeraBox downloader"
                stub_msg = await client.send_message(
                    chat_id=settings.target_channel,
                    text=stub_caption,
                    parse_mode=enums.ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(text="🔗 Open Link", url=link)
                    ]])
                )
                if stub_msg:
                    logger.info(f"[Channel Forwarder] ✅ Sent stub message with link: msg_id={stub_msg.id}")
            except Exception as e:
                logger.warning(f"[Channel Forwarder] Failed to send stub message: {e}")
            
            # ❌ Return False: message should retry on next restart
            logger.warning(f"[Channel Forwarder] Download failed, will retry on next bot restart")
            return False
        
        # Determine image source and prepare thumbnail file if possible.
        thumb_file = None
        image_src = None
        
        logger.info(f"[ChannelForwarder] 🖼️ Fetching thumbnail/image...")

        # Prefer thumbnail URL provided by TeraBox API
        if thumbnail_url:
            image_src = thumbnail_url
            logger.info(f"[ChannelForwarder] Trying API thumbnail URL: {thumbnail_url}")
            try:
                thumb_file = Path(tempfile.gettempdir()) / f"{download_id}_thumb.jpg"
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(thumbnail_url, timeout=30) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            with open(thumb_file, 'wb') as f:
                                f.write(data)
                            logger.info(f"[ChannelForwarder] ✅ API thumbnail downloaded ({len(data)} bytes)")
                        else:
                            logger.warning(f"[ChannelForwarder] API thumbnail returned {resp.status}")
                            thumb_file = None
            except Exception as e:
                logger.warning(f"[ChannelForwarder] ❌ API thumbnail download failed: {e}")
                thumb_file = None

        # If no thumbnail URL, try to use source message's photo/document/video thumb
        if not thumb_file and source_message:
            logger.info(f"[ChannelForwarder] Trying source message media...")
            try:
                # Photos: download the photo media
                if source_message.photo:
                    logger.info(f"[ChannelForwarder] Source has photo media, downloading...")
                    image_src = source_message.photo.file_id if getattr(source_message.photo, 'file_id', None) else None
                    try:
                        thumb_file = Path(tempfile.gettempdir()) / f"{download_id}_source_photo.jpg"
                        downloaded = await client.download_media(source_message.photo, file_name=str(thumb_file))
                        if not downloaded:
                            thumb_file = None
                            logger.warning("[ChannelForwarder] ❌ Failed to download source photo")
                        else:
                            logger.info(f"[ChannelForwarder] ✅ Downloaded source photo ({thumb_file.stat().st_size} bytes)")
                    except Exception as e:
                        logger.warning(f"[ChannelForwarder] ❌ Failed to download source photo: {e}")
                        thumb_file = None

                # Documents with image mime
                elif getattr(source_message, 'document', None) and getattr(source_message.document, 'mime_type', '').startswith('image'):
                    logger.info(f"[ChannelForwarder] Source has image document, downloading...")
                    image_src = source_message.document.file_id if getattr(source_message.document, 'file_id', None) else None
                    try:
                        thumb_file = Path(tempfile.gettempdir()) / f"{download_id}_source_doc.jpg"
                        downloaded = await client.download_media(source_message.document, file_name=str(thumb_file))
                        if not downloaded:
                            thumb_file = None
                            logger.warning("[ChannelForwarder] ❌ Failed to download source document image")
                        else:
                            logger.info(f"[ChannelForwarder] ✅ Downloaded source document image ({thumb_file.stat().st_size} bytes)")
                    except Exception as e:
                        logger.warning(f"[ChannelForwarder] ❌ Failed to download source document image: {e}")
                        thumb_file = None

                # Videos with thumb
                elif getattr(source_message, 'video', None) and getattr(source_message.video, 'thumb', None):
                    logger.info(f"[ChannelForwarder] Source has video with thumb, downloading...")
                    image_src = source_message.video.thumb.file_id if getattr(source_message.video.thumb, 'file_id', None) else None
                    try:
                        thumb_file = Path(tempfile.gettempdir()) / f"{download_id}_source_video_thumb.jpg"
                        downloaded = await client.download_media(source_message.video.thumb, file_name=str(thumb_file))
                        if not downloaded:
                            thumb_file = None
                            logger.warning("[ChannelForwarder] ❌ Failed to download source video thumb")
                        else:
                            logger.info(f"[ChannelForwarder] ✅ Downloaded source video thumb ({thumb_file.stat().st_size} bytes)")
                    except Exception as e:
                        logger.warning(f"[ChannelForwarder] ❌ Failed to download source video thumb: {e}")
                        thumb_file = None
                else:
                    logger.info(f"[ChannelForwarder] Source message has no photo/image/video media")
            except Exception as e:
                logger.warning(f"[ChannelForwarder] Error extracting source image: {e}")
        
        if not thumb_file:
            logger.warning(f"[ChannelForwarder] ⚠️  No thumbnail/image available")
        
        uploader = TelegramUploader(client)
        
        # Step 4: Upload to target channel with source link button (ONCE)
        source_chat_id = source_message.chat.id
        source_message_id = source_message.id
        
        # Generate clickable source link
        if source_chat_id < 0:  # Channel/Group
            try:
                source_link = source_message.link
            except:
                source_link = f"https://t.me/c/{abs(source_chat_id)}/{source_message_id}"
        else:  # Private chat
            source_link = None
        
        target_caption = f"*{title}*\n\n📊 Size: {format_bytes(file_size)}\n\n🎯 Post: #{source_message_id}\n\n🤖 Auto-downloaded from TeraBox"
        
        # NO buttons for target channel - just upload video cleanly
        keyboard = None
        
        # Resolve target channel entity first (fixes "Peer id invalid" errors)
        try:
            await client.get_chat(target_chat_id)
        except Exception:
            logger.info(f"[ChannelForwarder] Resolving target channel via dialogs...")
            async for dialog in client.get_dialogs():
                if dialog.chat.id == target_chat_id:
                    logger.info(f"[ChannelForwarder] ✅ Found target in dialogs: {dialog.chat.title}")
                    break
        
        upload_msg = None
        try:
            # Verify the video file exists before uploading
            if not temp_file.exists() or temp_file.stat().st_size == 0:
                logger.error(f"[ChannelForwarder] ❌ Video file missing or empty: {temp_file}")
                logger.info(f"[ChannelForwarder] 💡 Creating stub message with link instead...")
                try:
                    stub_caption = f"*{title}*\n\n📊 Size: {format_bytes(file_size)}\n\n⚠️ Upload failed (video file disappeared)\n🔗 [Open in TeraBox]({link})\n\n🤖 Auto message from TeraBox downloader"
                    stub_msg = await client.send_message(
                        chat_id=target_chat_id,
                        text=stub_caption,
                        parse_mode=enums.ParseMode.MARKDOWN,
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton(text="🔗 Open Link", url=link)
                        ]])
                    )
                    if stub_msg:
                        logger.info(f"[ChannelForwarder] ✅ Sent stub message with link: msg_id={stub_msg.id}")
                        upload_msg = stub_msg
                except Exception as e:
                    logger.warning(f"[ChannelForwarder] Failed to send stub message: {e}")
            else:
                logger.info(f"[ChannelForwarder] 📤 Uploading video to target channel {target_chat_id}...")
                upload_msg = await client.send_video(
                    chat_id=target_chat_id,
                    video=str(temp_file),
                    caption=target_caption,
                    thumb=str(thumb_file) if thumb_file and thumb_file.exists() else None,
                    parse_mode=enums.ParseMode.MARKDOWN,
                    reply_markup=keyboard,
                    supports_streaming=True
                )
            
            if upload_msg:
                logger.info(f"[ChannelForwarder] ✅ Uploaded to target channel msg_id={upload_msg.id}")
            else:
                logger.error(f"[ChannelForwarder] ❌ Upload to target channel returned no message")
                
        except Exception as e:
            logger.error(f"[ChannelForwarder] ❌ Upload error: {e}", exc_info=True)
        
        # Step 5: Copy message to database channel for backup (if different from target)
        backup_msg = None
        if upload_msg and db_channel_id and db_channel_id != target_chat_id:
            try:
                logger.info(f"[ChannelForwarder] 📋 Copying message to database channel {db_channel_id} for backup...")
                
                # Resolve database channel entity first
                try:
                    await client.get_chat(db_channel_id)
                except Exception:
                    logger.info(f"[ChannelForwarder] Resolving database channel via dialogs...")
                    async for dialog in client.get_dialogs():
                        if dialog.chat.id == db_channel_id:
                            logger.info(f"[ChannelForwarder] ✅ Found database channel in dialogs: {dialog.chat.title}")
                            break
                
                # Copy the message instead of uploading again
                backup_msg = await client.copy_message(
                    chat_id=db_channel_id,
                    from_chat_id=target_chat_id,
                    message_id=upload_msg.id,
                    caption=f"*{title}*\n\nSize: {format_bytes(file_size)}\n📦 Backup\n\n🔗 Source: {link}",
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                
                if backup_msg:
                    logger.info(f"[ChannelForwarder] ✅ Copied to database channel msg_id={backup_msg.id}")
                    
            except Exception as e:
                logger.warning(f"[ChannelForwarder] ⚠️  Failed to copy to database channel: {e}")
        
        # Step 6: Save backup record (CRITICAL - must persist to database)
        record_id = None
        if upload_msg:
            try:
                if not image_src:
                    image_src = thumbnail_url or ""
                
                # Determine backup channel/message IDs
                backup_channel_id = db_channel_id if backup_msg else (db_channel_id if db_channel_id else None)
                backup_message_id = backup_msg.id if backup_msg else None
                
                logger.info(f"[ChannelForwarder] 💾 Saving backup record: filename={filename}, channel={backup_channel_id}, msg={backup_message_id}")
                
                # save_backup_record now includes retry logic (3 attempts with backoff)
                record_id = db.save_backup_record(
                    download_id=download_id,
                    filename=filename,
                    filesize=file_size,
                    backup_channel_id=backup_channel_id,
                    backup_message_id=backup_message_id,
                    image_src=image_src,
                    extra={"source_chat_id": source_message.chat.id, "source_message_id": source_message.id}
                )
                
                if not record_id or record_id == 0:
                    logger.error(f"[ChannelForwarder] ❌ Failed to save backup record after all retries - returned 0")
                    record_id = None
                else:
                    # Verify record was actually saved
                    import time
                    time.sleep(0.1)  # Brief delay to ensure DB is flushed
                    verify_record = db.get_cached_by_id(record_id)
                    if verify_record:
                        logger.info(f"[ChannelForwarder] ✅ Verified record saved: id={record_id}, filename={verify_record.get('filename')}")
                    else:
                        logger.warning(f"[ChannelForwarder] ⚠️  Record {record_id} returned but immediate verification failed - may need delay")
                        # Try again after a longer delay
                        import time
                        time.sleep(0.5)
                        verify_record = db.get_cached_by_id(record_id)
                        if verify_record:
                            logger.info(f"[ChannelForwarder] ✅ Delayed verification succeeded: id={record_id}, filename={verify_record.get('filename')}")
                        else:
                            logger.error(f"[ChannelForwarder] ❌ ERROR: Record {record_id} saved but verification failed even after delay - not found in DB!")
                            record_id = None
                
            except Exception as e:
                logger.error(f"[ChannelForwarder] ❌ Failed to save backup record: {e}", exc_info=True)
                record_id = None
        
        # Step 7: Post source image with download button to IMAGE_SOURCE_GROUP
        if record_id and upload_msg:
            try:
                image_source_group = int(settings.image_source_group) if settings.image_source_group else 0
                # Always post to IMAGE_SOURCE_GROUP only
                image_target = image_source_group
                image_target_label = "IMAGE_SOURCE_GROUP"

                if not image_target:
                    logger.debug(f"[ChannelForwarder] {image_target_label} not configured, skipping image post")
                elif image_target == target_chat_id:
                    logger.debug(f"[ChannelForwarder] {image_target_label} same as target, skipping image post")
                else:
                    logger.info(f"[ChannelForwarder] 🖼️ Posting source image with download button to {image_target_label} {image_target}...")
                    logger.info(f"[ChannelForwarder] Button deeplink: https://t.me/{settings.bot_username}?start=video_{record_id}")

                    # Resolve IMAGE_SOURCE_* entity first
                    try:
                        await client.get_chat(image_target)
                    except Exception as e:
                        logger.debug(f"[ChannelForwarder] Resolving {image_target_label} via dialogs: {e}")
                        async for dialog in client.get_dialogs():
                            if dialog.chat.id == image_target:
                                logger.debug(f"[ChannelForwarder] Found {image_target_label} in dialogs")
                                break
                    
                    # Create Bot API style reply_markup
                    button_url = f"https://t.me/{settings.bot_username}?start=video_{record_id}"
                    logger.info(f"[ChannelForwarder] Creating button: text='📥 Get Video', url='{button_url}'")
                    reply_markup = {"inline_keyboard": [[{"text": "📥 Get Video", "url": button_url}]]}
                    
                    image_caption = f"*{title}*\n\n📊 Size: {format_bytes(file_size)}\n\n🔢 Post no: #{record_id}\n🆔 Msg id: {source_message_id}\n\n✅ Ready to download"
                    
                    # Try to get photo from source message
                    image_msg = None
                    
                    if source_message.photo:
                        # Send photo + caption with download button (attach keyboard)
                        logger.info(f"[ChannelForwarder] 📥 Downloading source photo...")
                        try:
                            photo_path = Path(tempfile.gettempdir()) / f"source_photo_{source_message.id}.jpg"
                            await source_message.download(file_name=str(photo_path))

                            if photo_path.exists():
                                logger.info(f"[ChannelForwarder] ✅ Photo downloaded: {photo_path}")
                                logger.info(f"[ChannelForwarder] 📤 Sending photo with download button to {image_target_label} ({image_target}) via Bot API...")
                                image_msg = botapi_send_photo(image_target, str(photo_path), caption=image_caption, reply_markup=reply_markup)

                                if image_msg:
                                    logger.info(f"[ChannelForwarder] ✅ Photo sent to {image_target_label}! msg_id={image_msg.get('message_id') or image_msg.get('message_id')}")

                                # (Posting only to IMAGE_SOURCE_GROUP)

                                try:
                                    photo_path.unlink()
                                except Exception:
                                    pass
                        except Exception as e:
                            logger.error(f"[ChannelForwarder] ❌ Failed: {e}", exc_info=True)
                            image_msg = None
                    elif thumb_file and thumb_file.exists():
                        # No source photo, use downloaded thumbnail
                        logger.info(f"[ChannelForwarder] ✅ Sending thumbnail with button to {image_target_label} ({image_target}) via Bot API...")
                        image_msg = botapi_send_photo(image_target, str(thumb_file), caption=image_caption, reply_markup=reply_markup)
                        logger.info(f"[ChannelForwarder] Thumbnail response: {image_msg is not None}")

                        # (Posting only to IMAGE_SOURCE_GROUP)
                    else:
                        # No image available, send text only with button
                        logger.info(f"[ChannelForwarder] ℹ️  Sending text-only with button to {image_target_label} ({image_target})...")
                        logger.info(f"[ChannelForwarder] ℹ️  Sending text-only with button to {image_target_label} ({image_target}) via Bot API...")
                        image_msg = botapi_send_message(image_target, image_caption, reply_markup=reply_markup)
                        logger.info(f"[ChannelForwarder] Message response: {image_msg is not None}")

                        # (Posting only to IMAGE_SOURCE_GROUP)
                    
                    if image_msg:
                        # botapi_send_* returns a dict (Bot API result) while Pyrogram returns an object.
                        if isinstance(image_msg, dict):
                            msg_id = image_msg.get('message_id') or image_msg.get('message', {}).get('message_id')
                        else:
                            msg_id = getattr(image_msg, 'id', None)
                        logger.info(f"[ChannelForwarder] ✅ Posted to {image_target_label} msg_id={msg_id}")
                    else:
                        logger.warning(f"[ChannelForwarder] ⚠️  Post to {image_target_label} returned no message")
                    
            except Exception as e:
                logger.error(f"[ChannelForwarder] ❌ Failed to post image with button: {e}", exc_info=True)
        
        # Cleanup temporary files
        logger.info(f"[ChannelForwarder] Cleaning up temporary files...")
        if thumb_file and thumb_file.exists():
            try:
                thumb_file.unlink()
                logger.debug(f"[ChannelForwarder] Deleted thumb: {thumb_file}")
            except Exception as e:
                logger.debug(f"[ChannelForwarder] Failed to delete thumb: {e}")
        
        if temp_file.exists():
            try:
                temp_file.unlink()
                logger.debug(f"[ChannelForwarder] Deleted temp: {temp_file}")
            except Exception as e:
                logger.debug(f"[ChannelForwarder] Failed to delete temp: {e}")
        
        # Force cleanup of entire temp directory after processing
        cleanup_temp_files()
        
        logger.info(f"[ChannelForwarder] ✅ Processing complete for {filename}\n")
        return True
        
    except Exception as e:
        logger.error(f"[ChannelForwarder] ❌ Error processing TeraBox link: {e}", exc_info=True)
        return False


async def on_channel_message(client: Client, message: Message):
    """
    Handle new messages from source channels.
    Extract TeraBox links and process them one-by-one.
    Mark as processed ONLY after successful download.
    
    Args:
        client: Pyrogram client
        message: Incoming message
    """
    try:
        # Validate that message has required attributes
        if not message or not message.chat:
            logger.warning("[ChannelForwarder] ⚠️ Skipping message with missing chat object")
            return
        
        # Check if this message was already processed (prevents reprocessing on bot restart)
        if db.is_message_processed(message.chat.id, message.id):
            logger.info(f"[ChannelForwarder] ⏭️  Message already processed (skipping): chat={message.chat.id} msg={message.id}")
            return
        
        # Extract text and caption
        text = message.text or message.caption or ""

        # Log incoming message for debugging
        media_info = []
        if message.photo:
            media_info.append("📷 PHOTO")
        if getattr(message, 'video', None):
            media_info.append("🎬 VIDEO")
        if getattr(message, 'document', None):
            media_info.append(f"📄 DOCUMENT({message.document.mime_type})")

        logger.info(f"[ChannelForwarder] Message details: chat={message.chat.id} msg={message.id} media={media_info} text={len(text)} chars")

        # Extract TeraBox links from text
        terabox_links = extract_terabox_links(text)
        logger.info(f"[ChannelForwarder] Text-extracted links: {len(terabox_links)} found")

        # If no links found in plain text, check URL entities (text_link or url)
        if not terabox_links:
            logger.info(f"[ChannelForwarder] Checking message entities for URLs...")
            try:
                entities = (message.entities or []) + (message.caption_entities or [])
                logger.info(f"[ChannelForwarder] Total entities: {len(entities)}")
                for ent in entities:
                    if ent.type in ("url", "text_link"):
                        url = None
                        if ent.type == "text_link":
                            url = getattr(ent, 'url', None)
                            logger.info(f"[ChannelForwarder] Found text_link entity: {url}")
                        else:
                            # slice from text/caption using offsets
                            src = message.text or message.caption or ""
                            try:
                                url = src[ent.offset: ent.offset + ent.length]
                                logger.info(f"[ChannelForwarder] Found url entity: {url}")
                            except Exception:
                                url = None

                        if url:
                            # check if it's a terabox link
                            if is_terabox_link(url):
                                logger.info(f"[ChannelForwarder] ✅ URL is TeraBox link: {url}")
                                terabox_links.append(url)
                            else:
                                logger.debug(f"[ChannelForwarder] URL not TeraBox: {url}")
            except Exception as e:
                logger.warning(f"[ChannelForwarder] Error parsing entities for URLs: {e}")
        
        if terabox_links:
            logger.info(f"[ChannelForwarder] ✅ Found {len(terabox_links)} TeraBox link(s)")
            
            # Get concurrency limits from config
            max_concurrent_uploads = getattr(settings, 'max_concurrent_uploads', 2)
            
            # Create semaphore to limit concurrent uploads across all links
            upload_semaphore = asyncio.Semaphore(max_concurrent_uploads)
            
            async def process_link_with_limit(i, link):
                """Process a single TeraBox link with upload concurrency limit."""
                async with upload_semaphore:
                    logger.info(f"[ChannelForwarder] Processing link {i}/{len(terabox_links)}: {link}")
                    try:
                        result = await process_terabox_link(
                            client=client,
                            link=link,
                            source_message=message,
                            target_chat_id=settings.target_channel,
                            db_channel_id=settings.database_channel
                        )
                        return result
                    except Exception as e:
                        logger.error(f"[ChannelForwarder] ❌ Error processing link {link}: {e}")
                        return False
            
            # Process all links in PARALLEL with upload concurrency limit
            logger.info(f"[ChannelForwarder] 🚀 Processing {len(terabox_links)} link(s) in parallel (max {max_concurrent_uploads} concurrent uploads)")
            tasks = [process_link_with_limit(i, link) for i, link in enumerate(terabox_links, start=1)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter out exceptions in results
            results = [r for r in results if not isinstance(r, Exception)]
            
            # ✅ Mark as processed ONLY if ALL links succeeded (results all True)
            all_succeeded = all(results)
            if all_succeeded:
                logger.info(f"[ChannelForwarder] ✅ All {len(terabox_links)} link(s) processed successfully, marking message as done")
                db.mark_message_processed(message.chat.id, message.id)
            else:
                failed_count = sum(1 for r in results if not r)
                logger.warning(f"[ChannelForwarder] ⚠️  {failed_count}/{len(terabox_links)} link(s) failed - message will retry on next restart")
        
        else:
            logger.info(f"[ChannelForwarder] No TeraBox links found in message - marking as processed anyway")
            # Even if no links found, mark as processed to avoid checking this message again
            db.mark_message_processed(message.chat.id, message.id)
        logger.debug(f"[ChannelForwarder] ✅ Marked message {message.id} as processed")
        
        # Cleanup after message processing
        cleanup_temp_files()
        gc.collect()
    
    except Exception as e:
        logger.error(f"[ChannelForwarder] ❌ Error handling message: {e}", exc_info=True)
        # Still cleanup on error
        try:
            cleanup_temp_files()
            gc.collect()
        except Exception:
            pass


async def process_existing_messages(client: Client, chat_id: int, limit: int = None):
    """
    Fetch and process existing messages from a channel ONE-BY-ONE.
    OPTIMIZED: Fetch processed IDs once into memory, then skip efficiently.
    Process each message immediately: fetch → extract links → download → upload.
    
    Args:
        client: Pyrogram client
        chat_id: Channel ID to fetch messages from
        limit: Max messages to process (None = ALL messages)
    """
    try:
        logger.info(f"[ChannelForwarder] 📚 Processing messages from channel {chat_id}...")
        
        # OPTIMIZATION: Get all processed message IDs for this chat into memory (one query)
        try:
            processed_ids_set = db.get_processed_message_ids(chat_id)
            logger.info(f"[ChannelForwarder] 🚀 Found {len(processed_ids_set)} already-processed messages in DB")
        except Exception as e:
            logger.warning(f"[ChannelForwarder] ⚠️  Error getting processed IDs: {e}")
            processed_ids_set = set()
        
        # CRITICAL: Resolve channel entity first (fixes "Peer id invalid" error)
        logger.info(f"[ChannelForwarder] 🔐 Resolving channel entity {chat_id}...")
        try:
            chat = await client.get_chat(chat_id)
            logger.info(f"[ChannelForwarder] ✅ Resolved: {chat.title or chat.username}")
        except Exception as e:
            logger.warning(f"[ChannelForwarder] ⚠️  Failed to resolve channel: {e}")
            logger.info(f"[ChannelForwarder] 🔄 Trying alternate resolution via dialogs...")
            
            # Fallback: search through dialogs to find and resolve the channel
            found = False
            try:
                async for dialog in client.get_dialogs():
                    if dialog.chat and dialog.chat.id == chat_id:
                        logger.info(f"[ChannelForwarder] ✅ Found in dialogs: {dialog.chat.title}")
                        found = True
                        break
            except Exception as dialog_error:
                logger.warning(f"[ChannelForwarder] ⚠️  Error searching dialogs: {dialog_error}")
            
            if not found:
                logger.warning(f"[ChannelForwarder] ❌ Channel {chat_id} not found in dialogs - skipping")
                return
        
        # Collect message IDs only (lightweight, fast)
        logger.info(f"[ChannelForwarder] 🔄 Collecting message IDs...")
        message_ids = []
        count = 0
        
        try:
            async for message in client.get_chat_history(chat_id, limit=limit):
                try:
                    if message and hasattr(message, 'id'):
                        message_ids.append(message.id)
                        count += 1
                        if count % 1000 == 0:
                            logger.info(f"[ChannelForwarder] ⏳ Scanned {count} messages...")
                except Exception as msg_error:
                    logger.debug(f"[ChannelForwarder] ⚠️  Error processing message object: {msg_error}")
                    continue
                    
        except Exception as e:
            logger.warning(f"[ChannelForwarder] ⚠️  Error during ID collection: {e}")
            if count == 0:
                logger.warning(f"[ChannelForwarder] ❌ Failed to collect any messages from {chat_id}")
                return
        
        logger.info(f"[ChannelForwarder] ✅ Found {len(message_ids)} messages total")
        
        if not message_ids:
            logger.warning(f"[ChannelForwarder] ℹ️  No messages found")
            return
        
        # Reverse to process oldest first
        message_ids.reverse()
        
        # Filter out already-processed messages (in-memory lookup is instant)
        new_message_ids = [msg_id for msg_id in message_ids if msg_id not in processed_ids_set]
        logger.info(f"[ChannelForwarder] 📊 NEW messages to process: {len(new_message_ids)} (skipped {len(message_ids) - len(new_message_ids)} already-processed)")
        
        if not new_message_ids:
            logger.info(f"[ChannelForwarder] ℹ️  No new messages to process")
            return
        
        logger.info(f"[ChannelForwarder] 🔄 Processing {len(new_message_ids)} new messages one-by-one (oldest first)...")
        logger.info(f"[ChannelForwarder] 📥 Fetch → 🔗 Extract → 💾 Download → 📤 Upload → ✅ Mark\n")
        
        # Get concurrency limits from config
        max_concurrent = getattr(settings, 'max_concurrent_downloads', 3)
        logger.info(f"[ChannelForwarder] 🚀 Parallel processing enabled: max {max_concurrent} concurrent downloads")
        
        # Create semaphore to limit concurrent message processing
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_message_with_limit(msg_id):
            """Process a single message with concurrency limit."""
            async with semaphore:
                try:
                    # Fetch one message
                    try:
                        message = await client.get_messages(chat_id, msg_id)
                    except Exception as e:
                        logger.debug(f"[ChannelForwarder] ⚠️  Could not fetch msg {msg_id}: {e}")
                        await asyncio.sleep(0.1)
                        return False
                        
                    if not message:
                        logger.debug(f"[ChannelForwarder] ⚠️  Message {msg_id} returned None")
                        return False
                    
                    # Validate message has required attributes
                    if not message.chat:
                        logger.debug(f"[ChannelForwarder] ⚠️  Message {msg_id} has no chat object")
                        return False
                    
                    # Process it (extract links, download, upload)
                    await on_channel_message(client, message)
                    
                    # Periodic cleanup after every message
                    cleanup_temp_files()
                    
                    # Small delay to avoid rate limits
                    await asyncio.sleep(0.1)
                    return True
                        
                except Exception as e:
                    logger.warning(f"[ChannelForwarder] ⚠️  Error processing msg {msg_id}: {e}")
                    await asyncio.sleep(0.1)
                    return False
        
        start_time = asyncio.get_event_loop().time()
        
        # Process all messages in parallel with concurrency limit
        tasks = [process_message_with_limit(msg_id) for msg_id in new_message_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        message_count = sum(1 for r in results if r is True)
        failed_count = sum(1 for r in results if isinstance(r, Exception))
        
        elapsed = asyncio.get_event_loop().time() - start_time
        logger.info(f"\n[ChannelForwarder] ✅ Finished! Processed {message_count}/{len(new_message_ids)} new messages in {elapsed:.0f}s (failed: {failed_count})\n")
        
        # Final cleanup after all messages processed
        logger.info(f"[ChannelForwarder] 🧹 Final cleanup...")
        cleanup_temp_files()
        gc.collect()
        logger.info(f"[ChannelForwarder] ✅ Cleanup complete")
        
    except Exception as e:
        logger.error(f"[ChannelForwarder] ❌ Error processing existing messages: {e}", exc_info=True)
        # Still cleanup on error
        try:
            cleanup_temp_files()
            gc.collect()
        except Exception:
            pass


def register_channel_forwarder_handlers(app: Client):
    """
    Register channel forwarder handlers.
    
    Args:
        app: Pyrogram client
    """
    if not settings.source_channels_list:
        logger.warning("❌ No source channels configured for channel forwarder")
        return
    
    logger.info(f"✅ Registering channel forwarder for {len(settings.source_channels_list)} source channel(s): {settings.source_channels_list}")
    logger.info(f"   → Target channel: {settings.target_channel}")
    logger.info(f"   → Database/Backup channel: {settings.database_channel}")
    
    @app.on_message(filters.chat(settings.source_channels_list))
    async def channel_message_handler(client: Client, message: Message):
        """Handle NEW messages from source channels."""
        logger.info(f"[ChannelForwarder] 📨 Received message from chat {message.chat.id}, msg_id={message.id}")
        await on_channel_message(client, message)
    
    logger.info("✅ Channel forwarder handlers registered successfully")
