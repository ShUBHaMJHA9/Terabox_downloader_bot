"""
Logging module for TeraBox Downloader Bot.
Provides structured logging to both file and console with different log levels.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from config import settings


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color support for console output."""

    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[35m",   # Magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        """Format log record with colors."""
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logging():
    """Initialize logging configuration."""
    # Create logs directory
    log_dir = Path(settings.log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("terabox_bot")
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # File Handler
    file_handler = logging.FileHandler(settings.log_file)
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_format)

    # Console Handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_format = ColoredFormatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_format)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# Global logger instance
logger = setup_logging()


def get_logger(name: str = "terabox_bot"):
    """Get logger instance by name."""
    return logging.getLogger(name)


def log_action(user_id: int, action: str, details: str = "", level: str = "INFO"):
    """
    Log user action with details.
    
    Args:
        user_id: Telegram user ID
        action: Action name (e.g., "download_start")
        details: Additional details
        level: Log level (DEBUG, INFO, WARNING, ERROR)
    """
    message = f"[User: {user_id}] {action}"
    if details:
        message += f" | {details}"
    
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message)


def log_error(user_id: int, error_type: str, error_message: str):
    """
    Log error with context.
    
    Args:
        user_id: Telegram user ID
        error_type: Type of error
        error_message: Error message
    """
    logger.error(f"[User: {user_id}] Error {error_type}: {error_message}")


def get_recent_logs(lines: int = 50) -> str:
    """
    Retrieve recent log lines from file.
    
    Args:
        lines: Number of lines to retrieve
        
    Returns:
        Recent log lines as string
    """
    try:
        with open(settings.log_file, "r") as f:
            all_lines = f.readlines()
            recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return "".join(recent)
    except FileNotFoundError:
        return "No logs found yet."
