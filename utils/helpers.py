"""
Basic utility functions for the bot.
"""

import os
import psutil
from pathlib import Path
from typing import Tuple
from datetime import datetime, timedelta


def format_bytes(bytes_size: int) -> str:
    """
    Format bytes to human-readable string.
    
    Args:
        bytes_size: Size in bytes
        
    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.2f} PB"


def format_seconds(seconds: int) -> str:
    """
    Format seconds to human-readable time.
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted string (e.g., "1h 30m")
    """
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"


def get_system_stats() -> Tuple[float, float, str]:
    """
    Get system statistics.
    
    Returns:
        Tuple of (memory_percent, disk_percent, uptime_str)
    """
    try:
        # Memory usage
        memory_percent = psutil.virtual_memory().percent

        # Disk usage
        disk_percent = psutil.disk_usage("/").percent

        # Uptime
        uptime_seconds = int(datetime.now().timestamp() - psutil.boot_time())
        uptime_str = format_seconds(uptime_seconds)

        return memory_percent, disk_percent, uptime_str
    except Exception:
        return 0, 0, "Unknown"


def extract_filename_from_path(path: str) -> str:
    """Extract filename from path."""
    return Path(path).name


def is_valid_telegram_id(user_id: int) -> bool:
    """Check if valid Telegram ID."""
    return isinstance(user_id, int) and user_id > 0


def extract_url_from_text(text: str) -> str:
    """
    Extract URL from text message.
    
    Args:
        text: Message text
        
    Returns:
        URL if found, empty string otherwise
    """
    import re
    
    url_pattern = r"https?://[^\s]+"
    match = re.search(url_pattern, text)
    
    if match:
        return match.group(0)
    return ""


def render_progress_text(title: str, percent: int, downloaded: int, total: int, speed_bytes: float, eta_seconds: int, bar_length: int = 20) -> str:
    """
    Render a compact, attractive progress text block for Telegram.

    Args:
        title: Title line (e.g., 'Download Progress')
        percent: Progress percent (0-100)
        downloaded: Downloaded bytes
        total: Total bytes
        speed_bytes: Speed in bytes/sec
        eta_seconds: Estimated seconds remaining
        bar_length: Characters in progress bar

    Returns:
        Formatted markdown string
    """
    filled = int((percent / 100) * bar_length)
    empty = max(bar_length - filled, 0)
    bar = "█" * filled + "░" * empty
    speed_mb = speed_bytes / (1024 * 1024) if speed_bytes is not None else 0.0
    return (
        f"🔹 *{title}*\n\n"
        f"{percent}%   [{bar}]\n"
        f"{format_bytes(downloaded)} / {format_bytes(total)} • {speed_mb:.2f} MB/s • ETA: {format_seconds(int(eta_seconds))}"
    )
