"""
Telegram utilities for handling message sending, editing, and file uploads.
Optimized for fast uploads with configurable chunk sizes.
"""

import asyncio
from typing import Optional, List
from pyrogram import Client
from pyrogram.types import Message, Document
from config import settings
from utils.logger import logger


class TelegramUploader:
    """Handles Telegram file uploads with progress tracking and optimized chunking."""

    def __init__(self, client: Client):
        """
        Initialize uploader.
        
        Args:
            client: Pyrogram client instance
        """
        self.client = client
        self.chunk_size = settings.upload_chunk_size  # Default 1MB

    async def upload_document(
        self,
        chat_id: int,
        file_path: str,
        caption: str = "",
        progress_callback=None,
        parse_mode: str = "html"
    ) -> Optional[Message]:
        """
        Upload file to Telegram as document with optimized chunking.
        
        Args:
            chat_id: Telegram chat ID
            file_path: Path to file to upload
            caption: Document caption
            progress_callback: Async callback for progress
            parse_mode: Parse mode for caption
            
        Returns:
            Sent message or None if error
        """
        try:
            message = await self.client.send_document(
                chat_id=chat_id,
                document=file_path,
                caption=caption,
                parse_mode=parse_mode,
                progress=progress_callback,
                progress_args=(chat_id,),
                disable_notification=False,
                file_name=file_path.split("/")[-1]  # Use original filename
            )
            logger.info(f"File uploaded successfully to {chat_id}")
            return message
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return None

    async def upload_video(
        self,
        chat_id: int,
        file_path: str,
        caption: str = "",
        thumbnail_path: Optional[str] = None,
        progress_callback=None,
        parse_mode: str = "html"
    ) -> Optional[Message]:
        """
        Upload file to Telegram as video with optional thumbnail.
        
        Args:
            chat_id: Telegram chat ID
            file_path: Path to video file
            caption: Video caption
            thumbnail_path: Optional path to thumbnail image
            progress_callback: Async callback for progress
            parse_mode: Parse mode for caption
            
        Returns:
            Sent message or None if error
        """
        try:
            message = await self.client.send_video(
                chat_id=chat_id,
                video=file_path,
                caption=caption,
                parse_mode=parse_mode,
                thumb=thumbnail_path,
                progress=progress_callback,
                progress_args=(chat_id,),
                disable_notification=False,
                supports_streaming=True
            )
            logger.info(f"Video uploaded successfully to {chat_id}")
            return message
        except Exception as e:
            logger.error(f"Video upload error: {e}")
            return None

    async def forward_to_channel(
        self,
        from_chat_id: int,
        message_id: int,
        channel_id: int
    ) -> Optional[Message]:
        """
        Forward message to channel.
        
        Args:
            from_chat_id: Source chat ID
            message_id: Message to forward
            channel_id: Destination channel ID
            
        Returns:
            Forwarded message or None
        """
        try:
            message = await self.client.forward_messages(
                chat_id=channel_id,
                from_chat_id=from_chat_id,
                message_ids=[message_id]
            )
            logger.info(f"Message forwarded to channel {channel_id}")
            return message
        except Exception as e:
            logger.error(f"Forward error: {e}")
            return None

    async def copy_message_to_channel(
        self,
        from_chat_id: int,
        message_id: int,
        channel_id: int
    ) -> Optional[Message]:
        """
        Copy message to channel without re-uploading (server-side copy).

        Args:
            from_chat_id: Source chat ID
            message_id: Message ID to copy
            channel_id: Destination channel ID

        Returns:
            Copied message or None
        """
        try:
            # Step 1: Resolve source channel peer to fix "Peer id invalid" error
            logger.debug(f"[TelegramUploader] Resolving source channel {from_chat_id}...")
            try:
                await self.client.get_chat(from_chat_id)
                logger.debug(f"[TelegramUploader] ✅ Source channel resolved")
            except Exception as resolve_error:
                logger.warning(f"[TelegramUploader] ⚠️  Failed to resolve source channel: {resolve_error}")
                logger.debug(f"[TelegramUploader] Attempting to resolve via dialogs...")
                found = False
                try:
                    async for dialog in self.client.get_dialogs():
                        if dialog.chat and dialog.chat.id == from_chat_id:
                            logger.debug(f"[TelegramUploader] ✅ Found source in dialogs")
                            found = True
                            break
                except Exception:
                    pass
                if not found:
                    logger.error(f"[TelegramUploader] ❌ Could not resolve source channel {from_chat_id}")
                    return None
            
            # Step 2: Resolve destination channel peer
            logger.debug(f"[TelegramUploader] Resolving destination channel {channel_id}...")
            try:
                await self.client.get_chat(channel_id)
                logger.debug(f"[TelegramUploader] ✅ Destination channel resolved")
            except Exception as resolve_error:
                logger.warning(f"[TelegramUploader] ⚠️  Failed to resolve destination channel: {resolve_error}")
                logger.debug(f"[TelegramUploader] Attempting to resolve via dialogs...")
                found = False
                try:
                    async for dialog in self.client.get_dialogs():
                        if dialog.chat and dialog.chat.id == channel_id:
                            logger.debug(f"[TelegramUploader] ✅ Found destination in dialogs")
                            found = True
                            break
                except Exception:
                    pass
                if not found:
                    logger.error(f"[TelegramUploader] ❌ Could not resolve destination channel {channel_id}")
                    return None
            
            # Step 3: Copy message after both peers are resolved
            logger.debug(f"[TelegramUploader] Copying message {message_id} from {from_chat_id} to {channel_id}...")
            message = await self.client.copy_message(
                chat_id=channel_id,
                from_chat_id=from_chat_id,
                message_id=message_id
            )
            logger.info(f"[TelegramUploader] ✅ Message copied to channel {channel_id}")
            return message
        except Exception as e:
            logger.error(f"[TelegramUploader] ❌ Copy message error: {e}", exc_info=True)
            return None

    async def copy_message_via_bot_api(
        self,
        from_chat_id: int,
        message_id: int,
        channel_id: int
    ) -> Optional[dict]:
        """
        Copy message using Telegram Bot API instead of Pyrogram (more reliable for channel peers).

        Args:
            from_chat_id: Source chat ID
            message_id: Message ID to copy
            channel_id: Destination channel ID

        Returns:
            Copied message dict or None
        """
        try:
            import requests
            
            bot_token = settings.telegram_bot_token
            if not bot_token:
                logger.error(f"[TelegramUploader] ❌ Bot token not configured")
                return None
            
            api_url = f"https://api.telegram.org/bot{bot_token}/copyMessage"
            
            # Bot API copyMessage parameters
            data = {
                "chat_id": channel_id,
                "from_chat_id": from_chat_id,
                "message_id": message_id,
            }
            
            logger.debug(f"[TelegramUploader] Attempting Bot API copy: from {from_chat_id} msg {message_id} to {channel_id}")
            
            response = requests.post(api_url, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    message_data = result.get("result")
                    logger.info(f"[TelegramUploader] ✅ Message copied via Bot API to channel {channel_id}, msg_id={message_data.get('message_id')}")
                    return message_data
                else:
                    error_desc = result.get("description", "Unknown error")
                    logger.warning(f"[TelegramUploader] ⚠️  Bot API error: {error_desc}")
                    return None
            else:
                logger.warning(f"[TelegramUploader] ⚠️  Bot API HTTP {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"[TelegramUploader] ❌ Bot API copy error: {e}")
            return None

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        disable_web_page_preview: bool = True
    ) -> Optional[Message]:
        """
        Edit existing message text.
        
        Args:
            chat_id: Chat ID
            message_id: Message ID
            text: New text
            disable_web_page_preview: Disable previews
            
        Returns:
            Edited message or None
        """
        try:
            message = await self.client.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                disable_web_page_preview=disable_web_page_preview
            )
            return message
        except Exception as e:
            logger.error(f"Edit error: {e}")
            return None


async def send_message(
    client: Client,
    chat_id: int,
    text: str,
    parse_mode: str = None
) -> Optional[Message]:
    """
    Send text message.
    
    Args:
        client: Pyrogram client
        chat_id: Chat ID
        text: Message text
        parse_mode: Parse mode (default None for plain text)
        
    Returns:
        Sent message or None
    """
    try:
        message = await client.send_message(
            chat_id=chat_id,
            text=text,
            disable_web_page_preview=True
        )
        return message
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        return None


async def send_typing_action(client: Client, chat_id: int):
    """
    Send typing action (shows 'typing...' to user).
    
    Args:
        client: Pyrogram client
        chat_id: Chat ID
    """
    try:
        await client.send_chat_action(chat_id, "typing")
    except Exception as e:
        logger.debug(f"Typing action error: {e}")
