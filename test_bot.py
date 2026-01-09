"""
Example test file demonstrating bot functionality.
Run with: pytest test_bot.py -v
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from config import settings
from utils.database import DatabaseManager
from downloader.manager import TeraBoxDownloader, DownloadProgress


class TestDownloadProgress:
    """Test download progress tracking."""

    def test_progress_calculation(self):
        """Test progress percentage calculation."""
        progress = DownloadProgress()
        progress.total = 1000
        progress.downloaded = 250
        
        assert progress.progress_percent == 25

    def test_speed_calculation(self):
        """Test download speed calculation."""
        progress = DownloadProgress()
        progress.total = 1024 * 1024 * 100  # 100 MB
        progress.downloaded = 1024 * 1024 * 10  # 10 MB
        
        # Should calculate MB/s (actual depends on time elapsed)
        assert isinstance(progress.speed, float)

    def test_eta_calculation(self):
        """Test ETA calculation."""
        progress = DownloadProgress()
        progress.total = 1024 * 1024 * 100  # 100 MB
        progress.downloaded = 1024 * 1024 * 50  # 50 MB downloaded
        
        # ETA should be calculated (actual depends on speed)
        assert isinstance(progress.eta, int)


class TestTeraBoxDownloader:
    """Test TeraBox downloader functionality."""

    @pytest.mark.asyncio
    async def test_validate_url_valid(self):
        """Test URL validation with valid TeraBox URL."""
        downloader = TeraBoxDownloader()
        
        valid_urls = [
            "https://www.terabox.com/sharing/code123",
            "https://terabox.com/sharing/code123",
            "https://1024terabox.com/sharing/code123",
        ]
        
        for url in valid_urls:
            is_valid = await downloader.validate_url(url)
            assert is_valid

    @pytest.mark.asyncio
    async def test_validate_url_invalid(self):
        """Test URL validation with invalid URLs."""
        downloader = TeraBoxDownloader()
        
        invalid_urls = [
            "https://google.com",
            "https://example.com",
            "not a url",
        ]
        
        for url in invalid_urls:
            is_valid = await downloader.validate_url(url)
            assert not is_valid


class TestDatabase:
    """Test database functionality."""

    def test_database_initialization(self, tmp_path):
        """Test database creation and schema."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(str(db_path))
        
        # Database should be created
        assert db_path.exists()

    def test_add_user(self, tmp_path):
        """Test user addition."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(str(db_path))
        
        db.add_user(123456, "testuser", "Test", "User")
        user = db.get_user(123456)
        
        assert user is not None
        assert user["username"] == "testuser"
        assert user["first_name"] == "Test"

    def test_log_download(self, tmp_path):
        """Test download logging."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(str(db_path))
        
        db.add_user(123456, "testuser", "Test", "User")
        db.log_download(
            download_id="abc123",
            user_id=123456,
            url="https://terabox.com/test",
            filename="test.zip",
            filesize=1024000
        )
        
        download = db.get_download("abc123")
        assert download is not None
        assert download["filename"] == "test.zip"
        assert download["filesize"] == 1024000

    def test_update_download_status(self, tmp_path):
        """Test download status update."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(str(db_path))
        
        db.log_download(
            download_id="abc123",
            user_id=123456,
            url="https://terabox.com/test",
            filename="test.zip",
            filesize=1024000
        )
        
        db.update_download_status("abc123", "downloading", 50)
        download = db.get_download("abc123")
        
        assert download["status"] == "downloading"
        assert download["progress"] == 50

    def test_get_stats(self, tmp_path):
        """Test statistics retrieval."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(str(db_path))
        
        db.add_user(123456, "testuser", "Test", "User")
        db.add_user(789012, "testuser2", "Test", "User2")
        
        stats = db.get_stats()
        assert stats["total_users"] == 2


class TestHelpers:
    """Test helper functions."""

    def test_format_bytes(self):
        """Test bytes formatting."""
        from utils.helpers import format_bytes
        
        assert "B" in format_bytes(512)
        assert "KB" in format_bytes(1024 * 10)
        assert "MB" in format_bytes(1024 * 1024 * 5)
        assert "GB" in format_bytes(1024 * 1024 * 1024 * 2)

    def test_format_seconds(self):
        """Test seconds formatting."""
        from utils.helpers import format_seconds
        
        assert "s" in format_seconds(30)
        assert "m" in format_seconds(120)
        assert "h" in format_seconds(3600)

    def test_is_valid_telegram_id(self):
        """Test Telegram ID validation."""
        from utils.helpers import is_valid_telegram_id
        
        assert is_valid_telegram_id(123456789)
        assert not is_valid_telegram_id(-1)
        assert not is_valid_telegram_id(0)
        assert not is_valid_telegram_id("not_a_number")

    def test_extract_url_from_text(self):
        """Test URL extraction."""
        from utils.helpers import extract_url_from_text
        
        text = "Check this link: https://terabox.com/sharing/abc123"
        url = extract_url_from_text(text)
        
        assert "terabox.com" in url
        assert url.startswith("https://")


# Configuration for pytest
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
