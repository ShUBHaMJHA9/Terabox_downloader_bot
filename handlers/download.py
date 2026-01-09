"""
Download handlers - Processes URL submission and manages download/upload pipeline.
Proper flow: URL → TeraBox API → Stream Worker → Download → Upload (no chunking)
"""

import tempfile
import asyncio
import time
from pathlib import Path
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import settings
from messages import *
from utils.database import db
from utils.logger import logger, log_action, log_error
from utils.telegram import TelegramUploader
from utils.helpers import extract_url_from_text, format_bytes
from downloader.manager import downloader
from downloader.terabox_api import get_terabox_api
from downloader.aria2_downloader import aria2_download
from downloader.parallel_downloader import parallel_download


async def auto_delete_file(file_path: Path, delay: int = 300):
    """
    Automatically delete file after specified delay.
    
    Args:
        file_path: Path to file to delete
        delay: Delay in seconds before deletion (default 5 minutes)
    """
    try:
        await asyncio.sleep(delay)
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Auto-deleted: {file_path}")
    except Exception as e:
        logger.warning(f"Failed to auto-delete {file_path}: {e}")


async def on_url_message(client: Client, message: Message):
    """
    Handle URL submission - Main entry point for downloads.
    
    Proper flow: 
    1. Validate URL
    2. Call TeraBox API → get direct_link
    3. Call Stream Worker → get stream_url
    4. Download from stream_url
    5. Upload directly to Telegram (no chunking)
    """
    user = message.from_user
    chat_id = message.chat.id
    
    # Extract URL from message
    url = extract_url_from_text(message.text)
    
    if not url:
        await message.reply_text(ERROR_INVALID_URL, parse_mode=enums.ParseMode.MARKDOWN)
        log_action(user.id, "invalid_url_submitted")
        return
    
    # Validate TeraBox URL
    if not await downloader.validate_url(url):
        await message.reply_text(ERROR_INVALID_URL, parse_mode=enums.ParseMode.MARKDOWN)
        log_action(user.id, "unsupported_url_type", url)
        return
    
    # Generate download ID
    import uuid
    download_id = str(uuid.uuid4())[:12]
    
    # Send initial message
    processing_msg = await message.reply_text(
        "🔄 *Processing...*\n\nFetching from TeraBox API...",
        parse_mode=enums.ParseMode.MARKDOWN
    )
    
    try:
        # STEP 1: Get direct_link from TeraBox API
        logger.info(f"[{download_id}] Step 1: Fetching from TeraBox API: {url}")
        terabox_api = get_terabox_api()
        api_data = await terabox_api.get_download_info(url, user.id)
        
        if not api_data or not api_data.get("direct_link"):
            await processing_msg.edit_text(
                ERROR_DOWNLOAD_FAILED.format(
                    error_message="Failed to fetch video info from TeraBox"
                ),
                parse_mode=enums.ParseMode.MARKDOWN
            )
            log_error(user.id, "terabox_api_error", url)
            return
        
        direct_link = api_data.get("direct_link")
        filename = api_data.get("filename", "download")
        file_size = int(api_data.get("size", 0))  # Convert to int
        
        logger.info(f"[{download_id}] Step 1 complete: Got direct_link, file={filename}, size={file_size}")
        
        # Check file size limit
        if file_size > settings.max_file_size:
            await processing_msg.edit_text(
                ERROR_FILE_TOO_LARGE.format(
                    max_size=format_bytes(settings.max_file_size),
                    actual_size=format_bytes(file_size)
                ),
                parse_mode=enums.ParseMode.MARKDOWN
            )
            log_error(user.id, "file_too_large", f"{filename} ({file_size} bytes)")
            return
        
        # Update message
        await processing_msg.edit_text(
            "⚙️ *Creating Stream...*\n\nPreparing CloudFlare stream...",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        
        # STEP 2: Get stream_url from Stream Worker
        logger.info(f"[{download_id}] Step 2: Creating stream via CloudFlare Worker")
        stream_url = await downloader.get_stream_url(direct_link)
        
        if not stream_url:
            await processing_msg.edit_text(
                ERROR_DOWNLOAD_FAILED.format(
                    error_message="Failed to create stream via CloudFlare Worker"
                ),
                parse_mode=enums.ParseMode.MARKDOWN
            )
            log_error(user.id, "stream_creation_error", direct_link)
            return
        
        logger.info(f"[{download_id}] Step 2 complete: Got stream_url")
        
        # Create temporary file for download
        temp_dir = Path(tempfile.gettempdir()) / "terabox_bot"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = temp_dir / f"{download_id}.tmp"
        
        # Log download start
        db.log_download(download_id, user.id, url, filename, file_size)
        db.update_download_status(download_id, "downloading", 0)
        
        # STEP 3A: Share stream URL with user (can watch while downloading)
        logger.info(f"[{download_id}] Step 3A: Sharing stream URL with user")
        stream_link_msg = await message.reply_text(
            f"""🎬 *Stream Ready - Watch Now!*

📺 You can watch the video while downloading:

🔗 [**Click to Stream Video**]({stream_url})

⏳ File is being downloaded in the background...

📊 File: *{filename}*
📦 Size: {format_bytes(file_size)}

*This link will be removed after upload is complete.*""",
            parse_mode=enums.ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
        # Update message with download progress
        await processing_msg.edit_text(
            f"""📥 *Downloading...*

File: {filename}
Size: {format_bytes(file_size)}

0%""",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        
        # Progress callback
        async def on_progress(progress):
            """Update progress in message."""
            try:
                progress_bar = "█" * (progress.progress_percent // 10) + "░" * (10 - progress.progress_percent // 10)
                
                text = f"""📥 *Download Progress*

Progress: {progress.progress_percent}%
[{progress_bar}]
Size: {format_bytes(progress.downloaded)} / {format_bytes(progress.total)}
Speed: {progress.speed:.2f} MB/s
ETA: ~{progress.eta}s"""
                
                await processing_msg.edit_text(text, parse_mode=enums.ParseMode.MARKDOWN)
                db.update_download_status(download_id, "downloading", progress.progress_percent)
            except Exception as e:
                logger.debug(f"Progress update error: {e}")
        
        # STEP 3B: Download file using fastest available method
        logger.info(f"[{download_id}] Step 3B: Starting download from direct_link")
        
        # Try aria2c first (ultra-fast, C++ implementation)
        logger.info(f"[{download_id}] Attempting aria2c (16 parallel connections)...")
        success = await aria2_download(
            url=direct_link,
            output_path=temp_file,
            progress_callback=on_progress
        )
        
        # Fallback to parallel download (Python, 8 threads)
        if not success:
            logger.info(f"[{download_id}] aria2c not available, using parallel downloader (8 threads)...")
            success = await parallel_download(
                url=direct_link,
                output_path=temp_file,
                progress_callback=on_progress,
                num_threads=8
            )
        
        if not success:
            await processing_msg.edit_text(
                ERROR_DOWNLOAD_FAILED.format(error_message="Download failed"),
                parse_mode=enums.ParseMode.MARKDOWN
            )
            # Delete the stream link message since download failed
            try:
                await stream_link_msg.delete()
            except:
                pass
            log_error(user.id, "download_failed", filename)
            db.update_download_status(download_id, "failed", 0, "Download failed")
            return
        
        logger.info(f"[{download_id}] Step 3B complete: File fast-downloaded")
        
        # Verify file exists and has content
        if not temp_file.exists() or temp_file.stat().st_size == 0:
            await processing_msg.edit_text(
                ERROR_DOWNLOAD_FAILED.format(error_message="Downloaded file is empty or missing"),
                parse_mode=enums.ParseMode.MARKDOWN
            )
            log_error(user.id, "download_incomplete", f"File missing or empty: {temp_file}")
            db.update_download_status(download_id, "failed", 0, "File incomplete")
            return
        
        # Download thumbnail if available
        thumb_file = None
        thumbnail_url = api_data.get("thumbnail")
        if thumbnail_url:
            try:
                logger.info(f"[{download_id}] Downloading thumbnail from API")
                thumb_file = Path(tempfile.gettempdir()) / f"{download_id}_thumb.jpg"
                
                # Create temporary session for thumbnail download
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(thumbnail_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status == 200:
                            with open(thumb_file, 'wb') as f:
                                f.write(await resp.read())
                            logger.info(f"[{download_id}] Thumbnail downloaded")
            except Exception as e:
                logger.warning(f"[{download_id}] Failed to download thumbnail: {e}")
                thumb_file = None
        
        # Update message
        await processing_msg.edit_text(
            f"📤 *Uploading to Telegram*\n\nFile: {filename}\nSize: {format_bytes(file_size)}",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        
        # STEP 4: Upload to Telegram (direct, no chunking, as video with thumbnail)
        logger.info(f"[{download_id}] Step 4: Uploading to Telegram as video with thumbnail")
        db.update_download_status(download_id, "uploading", 50)
        
        uploader = TelegramUploader(client)
        
        # Simple upload progress callback
        async def upload_progress(current, total, *args):
            """Progress callback for upload."""
            try:
                if total == 0:
                    return
                percent = int((current / total) * 100)
                if percent % 20 == 0:  # Update every 20%
                    progress_bar = "█" * (percent // 10) + "░" * (10 - percent // 10)
                    
                    text = f"""📤 *Uploading to Telegram*

Progress: {percent}%
[{progress_bar}]"""
                    
                    await processing_msg.edit_text(text, parse_mode=enums.ParseMode.MARKDOWN)
                    db.update_download_status(download_id, "uploading", 50 + (percent // 2))
            except Exception as e:
                logger.debug(f"Upload progress error: {e}")
        
        upload_msg = await uploader.upload_video(
            chat_id=chat_id,
            file_path=str(temp_file),
            caption=f"*{filename}*\n\nSize: {format_bytes(file_size)}\n✅ Downloaded!",
            thumbnail_path=str(thumb_file) if thumb_file and thumb_file.exists() else None,
            progress_callback=upload_progress,
            parse_mode=enums.ParseMode.MARKDOWN
        )
        
        if not upload_msg:
            await processing_msg.edit_text(
                ERROR_UPLOAD_FAILED.format(error_message="Upload to Telegram failed"),
                parse_mode=enums.ParseMode.MARKDOWN
            )
            log_error(user.id, "upload_failed", filename)
            db.update_download_status(download_id, "failed", 0, "Upload failed")
            return
        
        logger.info(f"[{download_id}] Step 4 complete: File uploaded to Telegram")
        
        # STEP 5: Forward to TERABOX_CHANNEL and get channel message link
        channel_msg_link = None
        if settings.terabox_channel:
            logger.info(f"[{download_id}] Step 5: Forwarding to TERABOX_CHANNEL")
            try:
                forward_msg = await uploader.forward_to_channel(
                    from_chat_id=chat_id,
                    message_id=upload_msg.id,
                    channel_id=settings.terabox_channel
                )
                if forward_msg:
                    logger.info(f"[{download_id}] Step 5 complete: Forwarded to TERABOX_CHANNEL")
                    # Generate channel message link
                    channel_username = settings.channel_username or f"c/{str(settings.terabox_channel)[4:]}"
                    channel_msg_link = f"https://t.me/{channel_username}/{forward_msg.id}"
                else:
                    logger.warning(f"[{download_id}] Failed to forward to TERABOX_CHANNEL")
            except Exception as e:
                logger.error(f"Forward error: {e}")
                logger.warning(f"[{download_id}] Failed to forward to TERABOX_CHANNEL")
        
        # Success!
        db.update_download_status(download_id, "completed", 100)
        
        # Create attractive completion message with buttons
        from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        buttons = []
        if channel_msg_link:
            buttons.append([InlineKeyboardButton("📺 View in Channel", url=channel_msg_link)])
        
        if settings.channel_username:
            buttons.append([InlineKeyboardButton("🔔 Join Channel for More Videos", url=f"https://t.me/{settings.channel_username}")])
        
        buttons.append([InlineKeyboardButton("🔄 Download Another", callback_data="start")])
        
        completion_message = f"""✅ *Download Complete!*

📁 **File:** {filename}
📦 **Size:** {format_bytes(file_size)}

{'🎬 **Your video is now in our channel!**' if channel_msg_link else '✨ **Upload successful!**'}

⏰ **Auto-Delete:** This video will be automatically deleted after **12 hours**

💡 **Tip:** Join our channel to access all videos permanently and get instant notifications for new uploads!"""
        
        await processing_msg.edit_text(
            completion_message,
            parse_mode=enums.ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
        )
        
        # STEP 6: Delete stream link message AFTER showing completion
        logger.info(f"[{download_id}] Step 6: Removing stream link message")
        try:
            await stream_link_msg.delete()
            logger.info(f"[{download_id}] Stream link message deleted")
        except Exception as e:
            logger.warning(f"[{download_id}] Failed to delete stream link message: {e}")
        
        log_action(user.id, "download_complete", f"{filename} ({format_bytes(file_size)})")
        
        # Clean up thumbnail
        if thumb_file and thumb_file.exists():
            try:
                thumb_file.unlink()
            except:
                pass
        
        # Auto-delete file after upload if enabled
        if settings.auto_delete_after_upload:
            asyncio.create_task(auto_delete_file(temp_file, settings.auto_delete_delay))
            logger.info(f"[{download_id}] Scheduled auto-delete in {settings.auto_delete_delay}s")
        else:
            # Clean up immediately if auto-delete disabled
            try:
                temp_file.unlink()
            except:
                pass
        
    except Exception as e:
        logger.error(f"[{download_id}] Unexpected error: {e}", exc_info=True)
        try:
            await processing_msg.edit_text(
                f"❌ *Unexpected Error*\n\n{str(e)[:100]}",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        except:
            pass
        log_error(user.id, "unexpected_error", str(e))
        try:
            db.update_download_status(download_id, "failed", 0, str(e)[:100])
        except:
            pass


def register_download_handlers(app: Client):
    """Register download handlers."""
    
    @app.on_message(filters.text & filters.private)
    async def text_handler(client: Client, message: Message):
        """Handle text messages that might contain URLs."""
        # Skip if it's a command
        if message.text.startswith("/"):
            return
        
        # Check if message contains URL
        if "://" in message.text:
            await on_url_message(client, message)
