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
from pathlib import Path
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import settings
from utils.logger import logger, log_action, log_error
from utils.telegram import TelegramUploader
from utils.helpers import format_bytes, extract_url_from_text
from downloader.manager import downloader
from downloader.terabox_api import get_terabox_api


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


async def process_terabox_link(client: Client, link: str, source_message: Message, target_chat_id: int, db_channel_id: int):
    """
    Process a TeraBox link: download, backup, and upload with source link button.
    
    Args:
        client: Pyrogram client
        link: TeraBox URL
        source_message: Original message from source channel
        target_chat_id: Target channel to upload to
        db_channel_id: Database channel for backup
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
            return
        
        direct_link = api_data.get("direct_link")
        filename = api_data.get("filename", "download")
        file_size = int(api_data.get("size", 0))
        thumbnail_url = api_data.get("thumbnail")
        title = api_data.get("title", filename)
        
        logger.info(f"[Channel Forwarder] Got info: {filename}, size={file_size}")
        
        # Check file size limit
        if file_size > settings.max_file_size:
            logger.warning(f"[Channel Forwarder] File too large: {file_size} > {settings.max_file_size}")
            return
        
        # Step 2: Create stream URL
        logger.info(f"[Channel Forwarder] Creating stream...")
        stream_url = await downloader.get_stream_url(direct_link)
        
        if not stream_url:
            logger.warning(f"[Channel Forwarder] Failed to create stream")
            return
        
        # Step 3: Download file
        temp_dir = Path(tempfile.gettempdir()) / "terabox_bot"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = temp_dir / f"{download_id}.tmp"
        
        logger.info(f"[Channel Forwarder] Downloading file...")
        success = await downloader.download(
            download_id=download_id,
            stream_url=stream_url,
            output_path=temp_file,
            user_id=0
        )
        
        if not success or not temp_file.exists() or temp_file.stat().st_size == 0:
            logger.warning(f"[Channel Forwarder] Download failed")
            return
        
        logger.info(f"[Channel Forwarder] Downloaded {format_bytes(file_size)}")
        
        # Download thumbnail
        thumb_file = None
        if thumbnail_url:
            try:
                thumb_file = Path(tempfile.gettempdir()) / f"{download_id}_thumb.jpg"
                async with downloader.session.get(thumbnail_url, timeout=30) as resp:
                    if resp.status == 200:
                        with open(thumb_file, 'wb') as f:
                            f.write(await resp.read())
                        logger.info(f"[Channel Forwarder] Thumbnail downloaded")
            except Exception as e:
                logger.warning(f"[Channel Forwarder] Thumbnail download failed: {e}")
                thumb_file = None
        
        uploader = TelegramUploader(client)
        
        # Step 4: Upload to database channel for backup (without buttons)
        db_caption = f"*{title}*\n\nSize: {format_bytes(file_size)}\n📦 Backup copy\n\n🔗 Source: {link}"
        
        if db_channel_id and db_channel_id != target_chat_id:
            logger.info(f"[Channel Forwarder] Uploading to database channel...")
            try:
                await uploader.upload_video(
                    chat_id=db_channel_id,
                    file_path=str(temp_file),
                    caption=db_caption,
                    thumbnail_path=str(thumb_file) if thumb_file and thumb_file.exists() else None,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                logger.info(f"[Channel Forwarder] Backed up to database channel")
            except Exception as e:
                logger.error(f"[Channel Forwarder] Database backup failed: {e}")
        
        # Step 5: Upload to target channel with source link button
        logger.info(f"[Channel Forwarder] Uploading to target channel with source button...")
        
        # Create caption with source information
        source_chat_id = source_message.chat.id
        source_message_id = source_message.id
        
        # Generate clickable source link
        if source_chat_id < 0:  # Channel/Group
            # For channels/groups, create link format: https://t.me/channel_username/message_id
            # or use message link
            try:
                source_link = source_message.link
            except:
                source_link = f"https://t.me/c/{abs(source_chat_id)}/{source_message_id}"
        else:  # Private chat
            source_link = None
        
        target_caption = f"*{title}*\n\n📊 Size: {format_bytes(file_size)}\n\n🎯 Post: #{source_message_id}\n\n🤖 Auto-downloaded from TeraBox"
        
        # Upload with inline buttons
        buttons = []
        if source_link:
            buttons.append(InlineKeyboardButton(
                text="🔗 Go to Original",
                url=source_link
            ))
        
        buttons.append(InlineKeyboardButton(
            text="📥 TeraBox Link",
            url=link
        ))
        
        keyboard = InlineKeyboardMarkup([buttons]) if buttons else None
        
        try:
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
                logger.info(f"[Channel Forwarder] Uploaded to target channel with message ID: {upload_msg.id}")
            else:
                logger.error(f"[Channel Forwarder] Upload to target channel failed")
        except Exception as e:
            logger.error(f"[Channel Forwarder] Upload error: {e}", exc_info=True)
        
        # Cleanup
        if thumb_file and thumb_file.exists():
            try:
                thumb_file.unlink()
            except:
                pass
        
        if temp_file.exists():
            try:
                temp_file.unlink()
            except:
                pass
        
        logger.info(f"[Channel Forwarder] Processing complete for {filename}")
        
    except Exception as e:
        logger.error(f"[Channel Forwarder] Error processing TeraBox link: {e}", exc_info=True)


async def on_channel_message(client: Client, message: Message):
    """
    Handle new messages from source channels.
    Extract TeraBox links and process them one-by-one.
    
    Args:
        client: Pyrogram client
        message: Incoming message
    """
    try:
        # Extract text and caption
        text = message.text or message.caption or ""
        
        logger.info(f"[Channel Forwarder] New message from chat {message.chat.id}, message ID: {message.id}")
        
        # Extract TeraBox links from text
        terabox_links = extract_terabox_links(text)
        
        if terabox_links:
            logger.info(f"[Channel Forwarder] Found {len(terabox_links)} TeraBox link(s)")
            
            # Process each link one-by-one in background
            for link in terabox_links:
                logger.info(f"[Channel Forwarder] Queuing TeraBox link: {link}")
                asyncio.create_task(
                    process_terabox_link(
                        client=client,
                        link=link,
                        source_message=message,
                        target_chat_id=settings.target_channel,
                        db_channel_id=settings.database_channel
                    )
                )
        
        # Forward original message to target channel (text messages)
        elif settings.target_channel and not message.media:
            try:
                await client.forward_messages(
                    chat_id=settings.target_channel,
                    from_chat_id=message.chat.id,
                    message_ids=[message.id]
                )
                logger.info(f"[Channel Forwarder] Forwarded text message from {message.chat.id} to target channel")
            except Exception as e:
                logger.warning(f"[Channel Forwarder] Forward failed: {e}")
    
    except Exception as e:
        logger.error(f"[Channel Forwarder] Error handling message: {e}", exc_info=True)


def register_channel_forwarder_handlers(app: Client):
    """
    Register channel forwarder handlers.
    
    Args:
        app: Pyrogram client
    """
    if not settings.source_channels_list:
        logger.warning("No source channels configured for channel forwarder")
        return
    
    logger.info(f"Registering channel forwarder for {len(settings.source_channels_list)} source channels...")
    
    @app.on_message(filters.chat(settings.source_channels_list))
    async def channel_message_handler(client: Client, message: Message):
        """Handle messages from source channels."""
        await on_channel_message(client, message)
    
    logger.info("✅ Channel forwarder handlers registered successfully")
