"""
Download handlers - lightweight, non-blocking implementation.
This file schedules heavy work in background tasks so command handlers remain responsive.
"""

import tempfile
import asyncio
from pathlib import Path
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import settings
from messages import *
from utils.database import db
from utils.logger import logger, log_action, log_error
from utils.telegram import TelegramUploader
from utils.helpers import extract_url_from_text, format_bytes, render_progress_text
from downloader.manager import downloader
from downloader.aria2_downloader import aria2_download
from downloader.parallel_downloader import parallel_download


async def auto_delete_file(file_path: Path, delay: int = 300):
    try:
        await asyncio.sleep(delay)
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Auto-deleted: {file_path}")
    except Exception as e:
        logger.warning(f"Failed to auto-delete {file_path}: {e}")


async def _process_download(client: Client, message: Message, url: str, download_id: str, processing_msg_id: int):
    """Background download/upload worker."""
    user = message.from_user
    chat_id = message.chat.id

    processing_msg = None
    try:
        # try to fetch processing message (if id provided)
        try:
            processing_msg = await client.get_messages(chat_id, processing_msg_id)
        except Exception:
            processing_msg = None

        logger.info(f"[{download_id}] Fetching TeraBox info: {url}")
        terabox_api = downloader.get_terabox_api() if hasattr(downloader, 'get_terabox_api') else None
        if terabox_api:
            api_data = await terabox_api.get_download_info(url, user.id)
        else:
            api_data = None

        if not api_data or not api_data.get('direct_link'):
            if processing_msg:
                await processing_msg.edit_text(ERROR_DOWNLOAD_FAILED.format(error_message="Failed to fetch video info from TeraBox"), parse_mode=enums.ParseMode.MARKDOWN)
            log_error(user.id, 'terabox_api_error', url)
            return

        direct_link = api_data.get('direct_link')
        filename = api_data.get('filename', 'download')
        file_size = int(api_data.get('size', 0) or 0)

        if file_size > settings.max_file_size:
            if processing_msg:
                await processing_msg.edit_text(ERROR_FILE_TOO_LARGE.format(max_size=format_bytes(settings.max_file_size), actual_size=format_bytes(file_size)), parse_mode=enums.ParseMode.MARKDOWN)
            log_error(user.id, 'file_too_large', f"{filename} ({file_size} bytes)")
            return

        # prepare temp file
        temp_dir = Path(tempfile.gettempdir()) / 'terabox_bot'
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = temp_dir / f"{download_id}.tmp"

        db.log_download(download_id, user.id, url, filename, file_size)
        db.update_download_status(download_id, 'downloading', 0)

        # download
        async def on_progress(progress):
            try:
                if processing_msg:
                    text = render_progress_text(title='Download Progress', percent=progress.progress_percent, downloaded=progress.downloaded, total=progress.total, speed_bytes=getattr(progress,'speed',0), eta_seconds=getattr(progress,'eta',0))
                    await processing_msg.edit_text(text, parse_mode=enums.ParseMode.MARKDOWN)
                    db.update_download_status(download_id, 'downloading', progress.progress_percent)
            except Exception:
                logger.debug('Progress update error')

        success = await aria2_download(url=direct_link, output_path=temp_file, progress_callback=on_progress, max_connections=settings.aria2_connections, split_count=settings.aria2_connections, max_conn_per_server=max(1, settings.aria2_connections//4), min_split_size='1M')
        if not success:
            success = await parallel_download(url=direct_link, output_path=temp_file, progress_callback=on_progress, num_threads=settings.parallel_threads)

        if not success:
            if processing_msg:
                await processing_msg.edit_text(ERROR_DOWNLOAD_FAILED.format(error_message='Download failed'), parse_mode=enums.ParseMode.MARKDOWN)
            log_error(user.id, 'download_failed', filename)
            db.update_download_status(download_id, 'failed', 0, 'Download failed')
            return

        # upload
        uploader = TelegramUploader(client)

        async def upload_progress(current, total, *args):
            try:
                if processing_msg and total:
                    percent = int((current/total)*100)
                    if percent % 5 == 0 or percent >= 99:
                        text = render_progress_text(title='Uploading to Telegram', percent=percent, downloaded=current, total=total, speed_bytes=0.0, eta_seconds=0)
                        await processing_msg.edit_text(text, parse_mode=enums.ParseMode.MARKDOWN)
                        db.update_download_status(download_id, 'uploading', 50 + (percent//2))
            except Exception:
                logger.debug('Upload progress error')

        upload_msg = await uploader.upload_video(chat_id=chat_id, file_path=str(temp_file), caption=f"*{filename}*\n\nSize: {format_bytes(file_size)}\n✅ Downloaded!", thumbnail_path=None, progress_callback=upload_progress, parse_mode=enums.ParseMode.MARKDOWN)
        if not upload_msg:
            if processing_msg:
                await processing_msg.edit_text(ERROR_UPLOAD_FAILED.format(error_message='Upload to Telegram failed'), parse_mode=enums.ParseMode.MARKDOWN)
            log_error(user.id, 'upload_failed', filename)
            db.update_download_status(download_id, 'failed', 0, 'Upload failed')
            return

        db.update_download_status(download_id, 'completed', 100)
        log_action(user.id, 'download_complete', f"{filename} ({format_bytes(file_size)})")

        # schedule cleanup
        if settings.auto_delete_after_upload:
            asyncio.create_task(auto_delete_file(temp_file, settings.auto_delete_delay))
        else:
            try:
                temp_file.unlink()
            except Exception:
                pass

        if processing_msg:
            await processing_msg.edit_text(f"✅ Upload complete: {filename}\nSize: {format_bytes(file_size)}", parse_mode=enums.ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"[{download_id}] Unexpected error: {e}", exc_info=True)
        try:
            if processing_msg:
                await processing_msg.edit_text(f"❌ Unexpected Error: {str(e)[:120]}")
        except Exception:
            pass
        log_error(user.id, 'unexpected_error', str(e))


async def on_url_message(client: Client, message: Message):
    """Public handler: validate and schedule a background download."""
    url = extract_url_from_text(message.text or "")
    user = message.from_user

    if not url:
        await message.reply_text(ERROR_INVALID_URL, parse_mode=enums.ParseMode.MARKDOWN)
        log_action(user.id, 'invalid_url_submitted')
        return

    if not await downloader.validate_url(url):
        await message.reply_text(ERROR_INVALID_URL, parse_mode=enums.ParseMode.MARKDOWN)
        log_action(user.id, 'unsupported_url_type', url)
        return

    import uuid
    download_id = str(uuid.uuid4())[:12]

    processing_msg = await message.reply_text("🔄 *Processing...*\n\nPreparing...", parse_mode=enums.ParseMode.MARKDOWN)

    asyncio.create_task(_process_download(client, message, url, download_id, processing_msg.id))
    # return immediately so bot remains responsive
    return


def register_download_handlers(app: Client):
    """Register download handlers."""

    @app.on_message(filters.text & filters.private)
    async def text_handler(client: Client, message: Message):
        logger.info(f"[DownloadHandler] Received private message from {getattr(message.from_user,'id',None)}: {str(message.text)[:120]}")
        if not message.text:
            return
        if message.text.startswith('/'):
            return
        if '://' in message.text:
            # schedule handler (on_url_message itself returns quickly)
            asyncio.create_task(on_url_message(client, message))
