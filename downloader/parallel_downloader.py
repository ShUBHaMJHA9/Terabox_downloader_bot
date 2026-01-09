"""
Parallel downloader using multiple concurrent connections and range requests.
Downloads file in parallel chunks for maximum speed.
Supports HTTP 206 Partial Content for true parallel downloads.
"""

import asyncio
import time
from pathlib import Path
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    requests = None

try:
    import cloudscraper
except ImportError:
    cloudscraper = None

from utils.logger import logger
from utils.helpers import format_bytes


class ParallelProgress:
    """Track parallel download progress."""
    def __init__(self):
        self.downloaded = 0
        self.total = 0
        self.start_time = time.time()
        self.last_update_percent = -1
        self.last_update_time = 0
        self.chunks_completed = 0
        self.total_chunks = 0
        self.lock = __import__('threading').Lock()
    
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
        
        if self.last_update_percent == -1:  # First update
            return True
        
        if current_percent >= self.last_update_percent + 5:  # Every 5% for parallel
            return True
        
        if current_time - self.last_update_time >= 2:  # Every 2 seconds
            return True
        
        if current_percent == 100:  # Always show completion
            return True
        
        return False
    
    def mark_updated(self):
        """Mark that progress was updated."""
        self.last_update_percent = self.progress_percent
        self.last_update_time = time.time()
    
    def add_downloaded(self, amount: int):
        """Thread-safe add to downloaded counter."""
        with self.lock:
            self.downloaded += amount


class ParallelDownloader:
    """Download files using multiple parallel connections for maximum speed."""
    
    def __init__(self, num_threads: int = 8):
        """
        Initialize parallel downloader.
        
        Args:
            num_threads: Number of parallel download threads (default 8)
        """
        self.num_threads = num_threads
        self.executor = ThreadPoolExecutor(max_workers=num_threads)
        self.session = None
        self._init_session()
    
    def _init_session(self):
        """Initialize HTTP session with optimizations."""
        try:
            # Try cloudscraper first
            if cloudscraper:
                try:
                    self.session = cloudscraper.create_scraper()
                    logger.info("✅ CloudScraper initialized for parallel downloads")
                except Exception as e:
                    logger.warning(f"CloudScraper failed: {e}, using requests")
                    self.session = None
            
            # Use requests if cloudscraper not available or failed
            if not self.session:
                import requests
                self.session = requests.Session()
                
            # Setup connection pooling and retries
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            
            retry_strategy = Retry(
                total=3,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS"]
            )
            
            adapter = HTTPAdapter(
                max_retries=retry_strategy,
                pool_connections=self.num_threads,
                pool_maxsize=self.num_threads
            )
            
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)
            
            # Optimized headers
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Cache-Control': 'no-cache',
            })
            
            logger.info(f"✅ Parallel downloader session ready with {self.num_threads} threads")
        except Exception as e:
            logger.error(f"Session initialization error: {e}")
            self.session = None
    
    def _check_range_support(self, url: str) -> bool:
        """Check if server supports HTTP 206 range requests."""
        try:
            resp = self.session.head(url, timeout=5, allow_redirects=True)
            accept_ranges = resp.headers.get('Accept-Ranges', '').lower()
            return accept_ranges == 'bytes'
        except Exception as e:
            logger.warning(f"Range support check failed: {e}")
            return False
    
    def _download_chunk(
        self,
        url: str,
        chunk_index: int,
        start: int,
        end: int,
        output_path: Path,
        progress: ParallelProgress
    ) -> bool:
        """
        Download a single chunk using range request.
        
        Args:
            url: URL to download
            chunk_index: Chunk number for ordering
            start: Start byte position
            end: End byte position
            output_path: File to save to
            progress: Progress tracker
            
        Returns:
            True if successful
        """
        try:
            headers = {'Range': f'bytes={start}-{end}'}
            
            response = self.session.get(
                url,
                headers=headers,
                stream=True,
                timeout=(5, 30),
                allow_redirects=True
            )
            
            if response.status_code not in [200, 206]:
                logger.error(f"Chunk {chunk_index}: HTTP {response.status_code}")
                return False
            
            chunk_data = b''
            for data in response.iter_content(chunk_size=256*1024):  # 256KB buffers
                if data:
                    chunk_data += data
            
            # Write chunk to file at correct position
            with open(output_path, 'r+b') as f:
                f.seek(start)
                f.write(chunk_data)
            
            chunk_size = len(chunk_data)
            progress.add_downloaded(chunk_size)
            
            logger.debug(
                f"Chunk {chunk_index}: {format_bytes(chunk_size)} downloaded "
                f"(Total: {format_bytes(progress.downloaded)}/{format_bytes(progress.total)})"
            )
            return True
            
        except Exception as e:
            logger.error(f"Chunk {chunk_index} download error: {e}")
            return False
    
    async def download_parallel(
        self,
        url: str,
        output_path: Path,
        progress_callback: Optional[Callable] = None,
        timeout: int = 3600
    ) -> bool:
        """
        Download file using parallel connections.
        
        Args:
            url: URL to download
            output_path: Output file path
            progress_callback: Optional async progress callback
            timeout: Download timeout in seconds
            
        Returns:
            True if successful
        """
        try:
            if not self.session:
                logger.error("Session not initialized")
                return False
            
            loop = asyncio.get_event_loop()
            
            # Get file size
            try:
                resp = self.session.head(url, timeout=5, allow_redirects=True)
                total_size = int(resp.headers.get('content-length', 0))
                
                if total_size == 0:
                    logger.warning("Could not determine file size, falling back to single-threaded")
                    return await self._download_single_threaded(url, output_path, progress_callback)
                
            except Exception as e:
                logger.warning(f"Size check failed: {e}, using single-threaded")
                return await self._download_single_threaded(url, output_path, progress_callback)
            
            # Check range support
            supports_ranges = self._check_range_support(url)
            
            if not supports_ranges or total_size < 5*1024*1024:  # < 5MB use single thread
                logger.info("Range requests not supported or file too small, using single-threaded")
                return await self._download_single_threaded(url, output_path, progress_callback)
            
            # Calculate chunk size (aim for num_threads chunks)
            chunk_size = max(1024*1024, total_size // self.num_threads)  # Min 1MB per chunk
            chunks = []
            
            # Create chunk ranges
            current_pos = 0
            chunk_idx = 0
            while current_pos < total_size:
                end = min(current_pos + chunk_size - 1, total_size - 1)
                chunks.append((chunk_idx, current_pos, end))
                chunk_idx += 1
                current_pos = end + 1
            
            # Initialize progress tracker
            progress = ParallelProgress()
            progress.total = total_size
            progress.total_chunks = len(chunks)
            
            # Create empty file with proper size
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.seek(total_size - 1)
                f.write(b'\0')
            
            logger.info(
                f"📥 Starting parallel download: {format_bytes(total_size)} "
                f"in {len(chunks)} chunks using {self.num_threads} threads"
            )
            
            # Launch chunk downloads
            futures = []
            for chunk_idx, start, end in chunks:
                future = self.executor.submit(
                    self._download_chunk,
                    url,
                    chunk_idx,
                    start,
                    end,
                    output_path,
                    progress
                )
                futures.append(future)
            
            # Start background progress monitor
            async def monitor_progress():
                """Monitor and report progress while downloading."""
                while progress.chunks_completed < progress.total_chunks:
                    await asyncio.sleep(1)  # Update every second
                    
                    if progress_callback and progress.should_update():
                        progress.mark_updated()
                        try:
                            await progress_callback(progress)
                            logger.info(
                                f"📊 Download: {progress.progress_percent}% "
                                f"({format_bytes(progress.downloaded)}/{format_bytes(progress.total)}) "
                                f"Speed: {progress.speed:.2f} MB/s ETA: {progress.eta}s "
                                f"[{progress.chunks_completed}/{progress.total_chunks} chunks]"
                            )
                        except Exception as e:
                            logger.debug(f"Progress callback error: {e}")
            
            # Start monitor task
            monitor_task = asyncio.create_task(monitor_progress())
            
            # Monitor chunk completion
            for future in as_completed(futures, timeout=timeout):
                if future.result():
                    with progress.lock:
                        progress.chunks_completed += 1
                    logger.debug(f"Chunk {progress.chunks_completed}/{progress.total_chunks} complete")
                else:
                    logger.warning(f"Chunk download failed")
            
            # Cancel monitor
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            
            # Cancel monitor
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            
            # Final callback
            if progress_callback:
                try:
                    await progress_callback(progress)
                except Exception as e:
                    logger.debug(f"Final progress callback error: {e}")
            
            final_size = output_path.stat().st_size
            logger.info(
                f"✅ Parallel download complete: {format_bytes(final_size)} "
                f"({progress.chunks_completed}/{progress.total_chunks} chunks)"
            )
            return final_size == total_size
            
        except Exception as e:
            logger.error(f"Parallel download error: {e}")
            return False
    
    async def _download_single_threaded(
        self,
        url: str,
        output_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """Fallback to single-threaded download."""
        try:
            loop = asyncio.get_event_loop()
            
            response = self.session.get(
                url,
                stream=True,
                timeout=(5, 30),
                allow_redirects=True
            )
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            progress = ParallelProgress()
            progress.total = total_size
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=512*1024):
                    if chunk:
                        f.write(chunk)
                        progress.add_downloaded(len(chunk))
                        
                        if progress_callback and progress.should_update():
                            progress.mark_updated()
                            try:
                                if loop and not loop.is_closed():
                                    asyncio.run_coroutine_threadsafe(
                                        progress_callback(progress),
                                        loop
                                    )
                            except Exception as e:
                                logger.debug(f"Progress callback error: {e}")
            
            return True
        except Exception as e:
            logger.error(f"Single-threaded download error: {e}")
            return False
    
    def close(self):
        """Close session and cleanup."""
        if self.session:
            try:
                self.session.close()
            except:
                pass
        self.executor.shutdown(wait=True)


# Global parallel downloader instance
_parallel_downloader = None


def get_parallel_downloader(num_threads: int = 8) -> ParallelDownloader:
    """Get or create global parallel downloader instance."""
    global _parallel_downloader
    if _parallel_downloader is None:
        _parallel_downloader = ParallelDownloader(num_threads=num_threads)
    return _parallel_downloader


async def parallel_download(
    url: str,
    output_path: Path,
    progress_callback: Optional[Callable] = None,
    num_threads: int = 8
) -> bool:
    """
    Convenience function for parallel downloading.
    
    Args:
        url: URL to download
        output_path: Output file path
        progress_callback: Optional progress callback
        num_threads: Number of parallel threads (default 8)
        
    Returns:
        True if successful
    """
    downloader = get_parallel_downloader(num_threads=num_threads)
    return await downloader.download_parallel(url, output_path, progress_callback)
