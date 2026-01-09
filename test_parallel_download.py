#!/usr/bin/env python3
"""
Test parallel downloader with a real small file.
"""

import asyncio
import tempfile
from pathlib import Path
from downloader.parallel_downloader import parallel_download


async def test_parallel_download():
    """Test parallel download functionality."""
    # Use a small test file (1MB from a reliable source)
    test_url = "https://httpbin.org/bytes/1048576"  # 1MB test file
    
    temp_dir = Path(tempfile.gettempdir()) / "terabox_test"
    temp_dir.mkdir(exist_ok=True)
    output_file = temp_dir / "test_download.bin"
    
    progress_updates = []
    
    async def on_progress(progress):
        """Capture progress updates."""
        progress_updates.append({
            'percent': progress.progress_percent,
            'speed': progress.speed,
            'eta': progress.eta,
            'downloaded': progress.downloaded,
            'total': progress.total
        })
        if progress.progress_percent % 20 == 0:
            print(
                f"📊 Progress: {progress.progress_percent}% "
                f"Speed: {progress.speed:.2f} MB/s "
                f"ETA: {progress.eta}s"
            )
    
    print("🚀 Starting parallel download test...")
    print(f"📥 URL: {test_url}")
    print(f"💾 Output: {output_file}")
    
    success = await parallel_download(
        url=test_url,
        output_path=output_file,
        progress_callback=on_progress,
        num_threads=4
    )
    
    if success and output_file.exists():
        file_size = output_file.stat().st_size
        print(f"\n✅ Download successful!")
        print(f"📦 File size: {file_size} bytes")
        print(f"📈 Progress updates: {len(progress_updates)}")
        
        if progress_updates:
            first = progress_updates[0]
            last = progress_updates[-1]
            print(f"\n📊 First update: {first['percent']}% @ {first['speed']:.2f} MB/s")
            print(f"📊 Last update: {last['percent']}% @ {last['speed']:.2f} MB/s")
        
        # Cleanup
        output_file.unlink()
        return True
    else:
        print(f"\n❌ Download failed or file missing")
        return False


if __name__ == "__main__":
    result = asyncio.run(test_parallel_download())
    exit(0 if result else 1)
