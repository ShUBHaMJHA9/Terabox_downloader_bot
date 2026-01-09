"""
Ultra-fast downloader using aria2c external tool.
aria2 is one of the fastest download tools available (C++ implementation).
Supports multiple connections, segmented downloading, and resume.
"""

import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Callable
import shutil

from utils.logger import logger
from utils.helpers import format_bytes


class Aria2Downloader:
    """Download using aria2c for maximum speed."""
    
    @staticmethod
    def is_available() -> bool:
        """Check if aria2c is installed."""
        return shutil.which("aria2c") is not None
    
    @staticmethod
    async def download(
        url: str,
        output_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """
        Download file using aria2c.
        
        Args:
            url: URL to download
            output_path: Output file path
            progress_callback: Optional progress callback
            
        Returns:
            True if successful
        """
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # aria2c options for maximum speed:
            # -x 16: max 16 connections
            # -k 1M: min 1MB per connection
            # -s 16: max 16 simultaneous downloads
            # --max-connection-per-server=4: connections per server
            # --split=16: split file into 16 parts
            # --min-split-size=1M: min 1MB per part
            # --lowest-speed-limit=0: no speed limit
            # -j 1: single input file
            
            cmd = [
                "aria2c",
                url,
                "-x", "16",                           # 16 connections
                "-k", "1M",                           # 1MB min per connection
                "-s", "16",                           # 16 simultaneous
                "--max-connection-per-server=4",      # 4 per server
                "--split=16",                         # 16 parts
                "--min-split-size=1M",                # 1MB min per part
                "--lowest-speed-limit=0",             # no speed limit
                "--follow-metalink=mem",              # follow metalinks
                "--allow-overwrite=true",             # overwrite output
                "-d", str(output_path.parent),        # output directory
                "-o", str(output_path.name),          # output filename
                "--no-conf",                          # ignore .aria2 config
                "--quiet",                            # minimal output
            ]
            
            logger.info(f"🚀 Starting aria2c download: {url}")
            logger.info(f"📊 Using 16 parallel connections for maximum speed")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and output_path.exists():
                size = output_path.stat().st_size
                logger.info(f"✅ aria2c download complete: {format_bytes(size)}")
                
                if progress_callback:
                    try:
                        # Simulate 100% progress
                        class FakeProgress:
                            progress_percent = 100
                            speed = 0
                            eta = 0
                        await progress_callback(FakeProgress())
                    except:
                        pass
                
                return True
            else:
                error_msg = stderr.decode('utf-8', errors='ignore') if stderr else "Unknown error"
                logger.error(f"aria2c failed: {error_msg}")
                return False
                
        except Exception as e:
            logger.warning(f"aria2c download error: {e}")
            return False


async def aria2_download(
    url: str,
    output_path: Path,
    progress_callback: Optional[Callable] = None
) -> bool:
    """
    Convenience function for aria2c downloading.
    
    Args:
        url: URL to download
        output_path: Output file path
        progress_callback: Optional progress callback
        
    Returns:
        True if successful
    """
    if not Aria2Downloader.is_available():
        logger.warning("aria2c not available")
        return False
    
    return await Aria2Downloader.download(url, output_path, progress_callback)
