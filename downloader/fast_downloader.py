"""
Fast downloader module using cloudscraper for rapid downloads.
Supports streaming with progress updates without chunking overhead.
"""

import asyncio
import aiofiles
import time
from pathlib import Path
from typing import Optional, Callable, Dict
from concurrent.futures import ThreadPoolExecutor

try:
    import cloudscraper
except ImportError:
    cloudscraper = None

from utils.logger import logger
from utils.helpers import format_bytes


class DownloadProgress:
    """Track download progress."""
    def __init__(self):
        self.downloaded = 0
        self.total = 0
        self.start_time = time.time()
        self.last_update_percent = -1
        self.last_update_time = 0
    
    @property
    def progress_percent(self) -> int:
        """Get progress percentage."""
        if self.total == 0:
            return 0
        return int((self.downloaded / self.total) * 100)
    
    @property
    def speed(self) -> float:
        """Get download speed in MB/s."""
        elapsed = time.time() - self.start_time
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
    
    def should_update(self) -> bool:
        """Check if progress should be reported."""
        current_percent = self.progress_percent
        current_time = time.time()
        
        # Update if:
        # 1. First update (last_update_percent == -1)
        # 2. Moved to next 10% bracket
        # 3. More than 2 seconds elapsed since last update
        # 4. Download is complete (100%)
        
        if self.last_update_percent == -1:  # First update
            return True
        
        if current_percent >= self.last_update_percent + 10:  # Next 10% bracket
            return True
        
        if current_time - self.last_update_time >= 2:  # Time-based update
            return True
        
        if current_percent == 100:  # Always show completion
            return True
        
        return False
    
    def mark_updated(self):
        """Mark that progress was updated."""
        self.last_update_percent = self.progress_percent
        self.last_update_time = time.time()


class FastDownloader:
    """Fast file downloader using cloudscraper and browser-like headers."""

    def __init__(self):
        """Initialize fast downloader."""
        self.session = None
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._init_scraper()

    def _init_scraper(self):
        """Initialize cloudscraper session if available."""
        if cloudscraper:
            try:
                self.session = cloudscraper.create_scraper()
                
                # Add connection pooling
                from requests.adapters import HTTPAdapter
                from urllib3.util.retry import Retry
                
                retry_strategy = Retry(
                    total=3,
                    backoff_factor=1,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["HEAD", "GET", "OPTIONS"]
                )
                
                adapter = HTTPAdapter(
                    max_retries=retry_strategy,
                    pool_connections=10,
                    pool_maxsize=10
                )
                
                self.session.mount("http://", adapter)
                self.session.mount("https://", adapter)
                
                # Enhance headers for better performance
                self.session.headers.update({
                    'Accept-Encoding': 'gzip, deflate',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                })
                
                logger.info("✅ CloudScraper initialized with optimized pooling")
            except Exception as e:
                logger.warning(f"CloudScraper initialization failed: {e}, falling back to requests")
                self._init_requests_session()
        else:
            self._init_requests_session()

    def _init_requests_session(self):
        """Initialize requests session with browser-like headers."""
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            
            self.session = requests.Session()
            
            # Setup connection pooling and retries
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS"]
            )
            
            adapter = HTTPAdapter(
                max_retries=retry_strategy,
                pool_connections=10,
                pool_maxsize=10
            )
            
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)
            
            # Better browser headers
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate',
                'Accept-Language': 'en-US,en;q=0.9',
                'Cache-Control': 'no-cache',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            })
            logger.info("✅ Requests session initialized for downloads with pooling")
        except Exception as e:
            logger.error(f"Failed to initialize download session: {e}")

    async def download_fast(
        self,
        url: str,
        output_path: Path,
        progress_callback: Optional[Callable] = None,
        timeout: int = 3600
    ) -> bool:
        """
        Fast download using cloudscraper in thread pool.
        
        Args:
            url: URL to download
            output_path: Path to save file
            progress_callback: Optional async callback for progress updates
            timeout: Download timeout in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            loop = asyncio.get_event_loop()
            
            # Run download in thread pool to avoid blocking
            result = await loop.run_in_executor(
                self.executor,
                self._download_sync,
                url,
                output_path,
                progress_callback,
                timeout,
                loop
            )
            return result
        except Exception as e:
            logger.error(f"Fast download error: {e}")
            return False

    def _download_sync(
        self,
        url: str,
        output_path: Path,
        progress_callback: Optional[Callable],
        timeout: int,
        loop: asyncio.AbstractEventLoop
    ) -> bool:
        """
        Synchronous download implementation with progress tracking.
        
        Args:
            url: URL to download
            output_path: Path to save file
            progress_callback: Progress callback
            timeout: Timeout in seconds
            loop: Event loop for async callbacks
            
        Returns:
            True if successful
        """
        try:
            if not self.session:
                logger.error("Download session not initialized")
                return False

            # Make request with streaming
            response = self.session.get(
                url,
                stream=True,
                timeout=(5, 30),  # (connect_timeout, read_timeout)
                allow_redirects=True
            )
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            progress = DownloadProgress()
            progress.total = total_size
            
            # Adaptive chunk size: larger for faster streams, smaller for slow streams
            # Start with 512KB chunks for better responsiveness
            chunk_size = 512 * 1024  # 512KB chunks
            
            # Create parent directory
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        progress.downloaded += len(chunk)

                        # Call progress callback if provided
                        if progress_callback and total_size > 0:
                            try:
                                # Check if we should update (10% intervals or time-based)
                                if progress.should_update():
                                    progress.mark_updated()
                                    
                                    # Schedule async callback on the event loop
                                    if loop and not loop.is_closed():
                                        asyncio.run_coroutine_threadsafe(
                                            progress_callback(progress),
                                            loop
                                        )
                                    
                                    logger.info(
                                        f"📊 Download progress: {progress.progress_percent}% "
                                        f"({format_bytes(progress.downloaded)}/{format_bytes(progress.total)}) "
                                        f"Speed: {progress.speed:.2f} MB/s "
                                        f"ETA: {progress.eta}s"
                                    )
                            except Exception as e:
                                logger.debug(f"Progress callback error: {e}")

            final_size = output_path.stat().st_size
            logger.info(f"✅ Fast download complete: {final_size} bytes in {progress.eta} seconds")
            return True

        except Exception as e:
            logger.error(f"Download error: {e}")
            return False

    def close(self):
        """Close session and cleanup."""
        if self.session:
            try:
                self.session.close()
            except:
                pass
        self.executor.shutdown(wait=True)


# Global fast downloader instance
_fast_downloader = None


def get_fast_downloader() -> FastDownloader:
    """Get or create global fast downloader instance."""
    global _fast_downloader
    if _fast_downloader is None:
        _fast_downloader = FastDownloader()
    return _fast_downloader


async def fast_download(
    url: str,
    output_path: Path,
    progress_callback: Optional[Callable] = None
) -> bool:
    """
    Convenience function for fast downloading.
    
    Args:
        url: URL to download
        output_path: Output file path
        progress_callback: Optional progress callback
        
    Returns:
        True if successful
    """
    downloader = get_fast_downloader()
    return await downloader.download_fast(url, output_path, progress_callback)

