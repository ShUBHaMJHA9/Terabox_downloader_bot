"""
Downloader module for TeraBox and similar file-hosting services.
Manages downloading, caching, and streaming of files.
"""

import re
import hashlib
import asyncio
from pathlib import Path
from typing import Optional, Callable, Dict
from datetime import datetime, timedelta
import aiohttp
import aiofiles
from config import settings
from utils.logger import logger, log_action, log_error


class DownloadProgress:
    """Track download progress."""

    def __init__(self):
        self.downloaded = 0
        self.total = 0
        self.start_time = datetime.now()

    @property
    def progress_percent(self) -> int:
        """Get progress percentage."""
        if self.total == 0:
            return 0
        return int((self.downloaded / self.total) * 100)

    @property
    def speed(self) -> float:
        """Get download speed in MB/s."""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if elapsed == 0:
            return 0
        return (self.downloaded / (1024 * 1024)) / elapsed

    @property
    def eta(self) -> int:
        """Get estimated time remaining in seconds."""
        if self.speed == 0:
            return 0
        remaining = self.total - self.downloaded
        return int(remaining / (self.speed * 1024 * 1024))


class FileCache:
    """Simple file cache with TTL support."""

    def __init__(self, cache_dir: str = None):
        """
        Initialize cache.
        
        Args:
            cache_dir: Cache directory path
        """
        self.cache_dir = Path(cache_dir or settings.cache_directory)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cache_path(self, url: str) -> Path:
        """Generate cache path for URL."""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.cache_dir / url_hash

    def get_cached_file(self, url: str) -> Optional[Path]:
        """
        Get cached file if exists and not expired.
        
        Args:
            url: File URL
            
        Returns:
            Path to cached file or None
        """
        cache_path = self.get_cache_path(url)
        
        if cache_path.exists():
            # Check if cached file is less than 24 hours old
            age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
            if age < timedelta(hours=24):
                logger.info(f"Using cached file: {cache_path}")
                return cache_path
            else:
                # Remove expired cache
                cache_path.unlink()
                logger.info(f"Removed expired cache: {cache_path}")
        
        return None

    def save_to_cache(self, url: str, file_path: Path) -> Path:
        """
        Save file to cache.
        
        Args:
            url: Original URL
            file_path: Path to file to cache
            
        Returns:
            Cache path
        """
        cache_path = self.get_cache_path(url)
        file_path.rename(cache_path)
        return cache_path


class TeraBoxDownloader:
    """
    Downloads files from TeraBox via Cloudflare Worker.
    Handles progress tracking, error handling, and caching.
    """

    def __init__(self):
        """Initialize downloader."""
        self.cache = FileCache() if settings.enable_file_caching else None
        self.active_downloads: Dict[str, DownloadProgress] = {}
        self.session = None  # Will be created in async context

    async def validate_url(self, url: str) -> bool:
        """
        Validate if URL is a valid TeraBox link.
        Supports all known TeraBox domains, mirrors, and regional variants.
        
        Args:
            url: URL to validate
            
        Returns:
            True if valid TeraBox URL
        """
        # Comprehensive list of TeraBox domains and mirrors (2024-2025)
        terabox_domains = [
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
        ]
        
        # Build patterns from domain list
        patterns = [rf"https?://(?:www\.)?{domain.replace('.', r'\.')}/" for domain in terabox_domains]
        
        return any(re.match(pattern, url, re.IGNORECASE) for pattern in patterns)

    async def get_stream_url(self, direct_link: str) -> Optional[str]:
        """
        Get streaming URL from Cloudflare Worker using direct_link.
        
        Args:
            direct_link: Direct download link from TeraBox API
            
        Returns:
            Stream URL or None if error
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Send direct_link to the STREAM_SERVICE worker's /data endpoint
                payload = {"url": direct_link}
                
                async with session.post(
                    f"{settings.stream_worker}/data",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120, sock_connect=30, sock_read=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("stream_url")
                    else:
                        logger.error(f"Stream worker error: {resp.status}")
                        return None
        except Exception as e:
            logger.error(f"Error getting stream URL: {e}")
            return None

    async def download(
        self,
        download_id: str,
        stream_url: str,
        output_path: Path,
        progress_callback: Optional[Callable] = None,
        user_id: int = 0,
        max_retries: int = 3
    ) -> bool:
        """
        Download file from stream URL with progress tracking and retry logic.
        
        Args:
            download_id: Unique download identifier
            stream_url: URL to download from
            output_path: Path to save file
            progress_callback: Async callback for progress updates
            user_id: Telegram user ID for logging
            max_retries: Maximum number of retries on failure
            
        Returns:
            True if successful, False otherwise
        """
        for attempt in range(max_retries):
            try:
                progress = DownloadProgress()
                self.active_downloads[download_id] = progress

                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        stream_url,
                        timeout=aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=60),
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                        }
                    ) as resp:
                        if resp.status != 200:
                            log_error(user_id, "download_http_error", f"Status {resp.status}")
                            if attempt < max_retries - 1:
                                wait_time = 2 ** attempt  # Exponential backoff
                                logger.warning(f"[Download] Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                                await asyncio.sleep(wait_time)
                                continue
                            return False

                        # Get total file size
                        content_length = resp.headers.get("Content-Length")
                        if content_length:
                            progress.total = int(content_length)

                        # Download with progress tracking
                        async with aiofiles.open(output_path, "wb") as f:
                            async for chunk in resp.content.iter_chunked(1024 * 256):  # 256KB chunks
                                if not chunk:
                                    break

                                await f.write(chunk)
                                progress.downloaded += len(chunk)

                                # Call progress callback
                                if progress_callback:
                                    await progress_callback(progress)

                log_action(user_id, "download_completed", f"Size: {progress.total}")
                return True

            except asyncio.TimeoutError as e:
                error_msg = f"Socket timeout: {e}"
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"[Download] {error_msg}, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    log_error(user_id, "download_timeout", error_msg)
                    return False
            except Exception as e:
                error_msg = f"{type(e).__name__}: {e}"
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"[Download] {error_msg}, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    log_error(user_id, "download_error", error_msg)
                    return False
            finally:
                self.active_downloads.pop(download_id, None)

    async def download_with_cache(
        self,
        download_id: str,
        terabox_url: str,
        output_path: Path,
        progress_callback: Optional[Callable] = None,
        user_id: int = 0
    ) -> bool:
        """
        Download file with caching support and size validation.
        
        Args:
            download_id: Download ID
            terabox_url: Original TeraBox URL
            output_path: Output file path
            progress_callback: Progress callback
            user_id: User ID for logging
            
        Returns:
            True if successful
        """
        # Check cache first
        if self.cache:
            cached_file = self.cache.get_cached_file(terabox_url)
            if cached_file:
                # Verify file size
                file_size = cached_file.stat().st_size
                if file_size <= settings.max_file_size:
                    # Copy cached file to output
                    import shutil
                    shutil.copy2(cached_file, output_path)
                    log_action(user_id, "cache_hit", f"Using cached file")
                    return True
                else:
                    log_error(user_id, "file_too_large", f"Cached file exceeds {settings.max_file_size} bytes")
                    return False

        # Get stream URL from worker
        stream_url = await self.get_stream_url(terabox_url)
        if not stream_url:
            log_error(user_id, "stream_url_error", "Failed to get stream URL")
            return False

        # Download file with size validation
        if await self.download(download_id, stream_url, output_path, progress_callback, user_id):
            # Verify file size
            file_size = output_path.stat().st_size
            if file_size > settings.max_file_size:
                output_path.unlink()  # Delete oversized file
                log_error(user_id, "file_too_large", f"File {file_size} exceeds limit {settings.max_file_size}")
                return False
            
            # Cache the file if enabled
            if self.cache:
                try:
                    self.cache.save_to_cache(terabox_url, output_path)
                except Exception as e:
                    logger.warning(f"Failed to cache file: {e}")
            return True

        return False

    def get_progress(self, download_id: str) -> Optional[DownloadProgress]:
        """
        Get progress for a download.
        
        Args:
            download_id: Download ID
            
        Returns:
            DownloadProgress object or None
        """
        return self.active_downloads.get(download_id)

    def cancel_download(self, download_id: str):
        """
        Cancel an ongoing download.
        
        Args:
            download_id: Download ID
        """
        if download_id in self.active_downloads:
            del self.active_downloads[download_id]
            logger.info(f"Download cancelled: {download_id}")


# Global downloader instance
downloader = TeraBoxDownloader()
