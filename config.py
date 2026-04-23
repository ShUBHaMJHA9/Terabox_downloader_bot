"""
Configuration module for TeraBox Downloader Bot.
Loads and manages environment variables and application settings.
"""

import os
from pathlib import Path
from typing import List, Union
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
import psutil


def calculate_optimal_concurrency():
    """
    Auto-detect CPU cores and RAM, calculate optimal concurrency limits.
    
    Returns:
        tuple: (max_concurrent_channels, max_concurrent_downloads, max_concurrent_uploads)
    """
    try:
        cpu_count = psutil.cpu_count(logical=False) or 2  # Physical cores
        total_ram_gb = psutil.virtual_memory().total / (1024**3)  # Convert to GB
        
        # Conservative estimates:
        # - Each download/upload needs ~100-200MB RAM
        # - Each channel needs ~50MB RAM
        
        # For channels (minimal resource usage)
        if cpu_count >= 8:
            max_channels = min(6, int(cpu_count / 2))
        elif cpu_count >= 4:
            max_channels = 4
        else:
            max_channels = 2
        
        # For downloads (more CPU intensive)
        if cpu_count >= 8:
            max_downloads = min(5, int(cpu_count / 1.5))
        elif cpu_count >= 4:
            max_downloads = 4
        else:
            max_downloads = 2
        
        # For uploads (constrained by Telegram API limits)
        if cpu_count >= 8:
            max_uploads = min(3, int(total_ram_gb / 400))  # ~400MB per upload
        else:
            max_uploads = 2
        
        return max_channels, max_downloads, max_uploads, cpu_count, total_ram_gb
        
    except Exception as e:
        print(f"⚠️  Failed to detect hardware specs: {e}, using defaults")
        return 2, 2, 1, 2, 2.0  # Conservative defaults


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ============ Telegram Configuration ============
    telegram_api_id: int = Field(default=0, alias="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(default="", alias="TELEGRAM_API_HASH")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    bot_username: str = Field(default="terabox_bot", alias="BOT_USERNAME")
    phone_number: str = Field(default="", alias="PHONE_NUMBER")
    
    # User account mode (for faster downloads with user permissions)
    use_user_account: bool = Field(default=False, alias="USE_USER_ACCOUNT")
    user_phone: str = Field(default="", alias="USER_PHONE")
    user_account_session: str = Field(default="./sessions/user", alias="USER_SESSION")

    # ============ Admin & Channel Configuration ============
    admin_ids: str = Field(default="", alias="ADMIN_IDS")  # Comma-separated string
    admin_ids_list: List[int] = Field(default=[], exclude=True)  # Parsed list
    admin_username: str = Field(default="", alias="ADMIN_USERNAME")
    
    # Channels
    main_channel_id: int = Field(default=0, alias="MAIN_CHANNEL_ID")
    channel_username: str = Field(default="", alias="CHANNEL_USERNAME")
    terabox_channel: int = Field(default=0, alias="TERABOX_CHANNEL")
    force_join_channel: int = Field(default=0, alias="FORCE_JOIN_CHANNEL")
    target_channel: int = Field(default=0, alias="TARGET_CHANNEL")
    image_source_group: int = Field(default=0, alias="IMAGE_SOURCE_GROUP")
    image_source_channel: int = Field(default=0, alias="IMAGE_SOURCE_CHANNEL")
    public_channel_id: int = Field(default=0, alias="PUBLIC_CHANNEL_ID")
    source_channels: str = Field(default="", alias="SOURCE_CHANNELS")  # Comma-separated string
    source_channels_list: List[int] = Field(default=[], exclude=True)  # Parsed list
    database_channel: int = Field(default=0, alias="DATABASE_CHANNEL")  # Backup storage channel
    
    # Storage channels
    instagram_group: str = Field(default="", alias="INSTAGRAM_GROUP")
    youtube_group: str = Field(default="", alias="YOUTUBE_GROUP")
    general_group: str = Field(default="", alias="GENERAL_GROUP")
    movie_group: int = Field(default=0, alias="MOVIE_GROUP")
    private_channel_link: str = Field(default="", alias="PRIVATE_CHANNEL_LINK")

    # ============ Downloader Configuration ============
    stream_worker: str = Field(default="", alias="STREAM_WORKER")
    terabox_api_v1: str = Field(default="", alias="TERABOX_API_V1")
    aria2_connections: int = Field(default=16, alias="ARIA2_CONNECTIONS")
    parallel_threads: int = Field(default=8, alias="PARALLEL_THREADS")
    
    # Parallel processing limits (auto-detected from CPU/RAM if not set)
    max_concurrent_downloads: int = Field(default=0, alias="MAX_CONCURRENT_DOWNLOADS")  # 0 = auto-detect
    max_concurrent_uploads: int = Field(default=0, alias="MAX_CONCURRENT_UPLOADS")  # 0 = auto-detect
    max_concurrent_channels: int = Field(default=0, alias="MAX_CONCURRENT_CHANNELS")  # 0 = auto-detect
    
    # Legacy support
    cloudflare_worker_url: str = Field(default="", alias="CLOUDFLARE_WORKER_URL")

    # ============ File & Storage Configuration ============
    database_path: str = Field(default="./data/bot.db", alias="DATABASE_PATH")
    file_storage_dir: str = Field(default="./storage", alias="FILE_STORAGE_DIR")
    
    premium_video_folder: str = Field(default="videos/premium", alias="PREMIUM_VIDEO_FOLDER")
    free_video_folder: str = Field(default="videos/free", alias="FREE_VIDEO_FOLDER")
    
    premium_file_lifetime: int = Field(default=259200, alias="PREMIUM_FILE_LIFETIME")  # 3 days
    free_file_lifetime: int = Field(default=1800, alias="FREE_FILE_LIFETIME")  # 30 min
    free_hourly_limit: int = Field(default=10, alias="FREE_HOURLY_LIMIT")
    max_free_size: int = Field(default=2097152000, alias="MAX_FREE_SIZE")  # 2GB

    # ============ Database Configuration ============
    # MongoDB
    mongo_uri: str = Field(default="", alias="MONGO_URI")
    # External MySQL (optional)
    mysql_database_url: str = Field(default="", alias="MYSQL_DATABASE_URL")
    
    # PostgreSQL - Supabase
    database_url: str = Field(default="", alias="DATABASE_URL")
    
    # PostgreSQL - Tembo
    tembo_host: str = Field(default="", alias="TEMBO_HOST")
    tembo_port: int = Field(default=5432, alias="TEMBO_PORT")
    tembo_name: str = Field(default="postgres", alias="TEMBO_NAME")
    tembo_user: str = Field(default="", alias="TEMBO_USER")
    tembo_password: str = Field(default="", alias="TEMBO_PASSWORD")
    
    # LibSQL - Turso
    turso_database_url: str = Field(default="", alias="TURSO_DATABASE_URL")
    turso_auth_token: str = Field(default="", alias="TURSO_AUTH_TOKEN")

    # ============ Logging Configuration ============
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="./logs/bot.log", alias="LOG_FILE")

    # ============ Feature Flags ============
    enable_channel_forwarding: bool = Field(
        default=False, alias="ENABLE_CHANNEL_FORWARDING"
    )
    enable_startup_processing: bool = Field(default=False, alias="ENABLE_STARTUP_PROCESSING")
    forward_channel_id: int = Field(default=0, alias="FORWARD_CHANNEL_ID")
    enable_file_caching: bool = Field(default=True, alias="ENABLE_FILE_CACHING")
    cache_directory: str = Field(default="./cache", alias="CACHE_DIRECTORY")
    parallel_processing: bool = Field(default=False, alias="PARALLEL_PROCESSING")
    debug: bool = Field(default=False, alias="DEBUG")

    # ============ Timeout & Limits ============
    download_timeout: int = Field(default=3600, alias="DOWNLOAD_TIMEOUT")
    upload_timeout: int = Field(default=3600, alias="UPLOAD_TIMEOUT")
    retries: int = Field(default=3, alias="RETRIES")
    
    # File Size Limits (in bytes)
    max_file_size: int = Field(default=524288000, alias="MAX_FILE_SIZE")  # 500MB default
    premium_max_file_size: int = Field(default=2147483648, alias="PREMIUM_MAX_FILE_SIZE")  # 2GB
    
    # Auto-delete settings
    auto_delete_after_upload: bool = Field(default=True, alias="AUTO_DELETE_AFTER_UPLOAD")
    auto_delete_delay: int = Field(default=300, alias="AUTO_DELETE_DELAY")  # 5 minutes in seconds
    
    # Upload optimization
    upload_chunk_size: int = Field(default=1048576, alias="UPLOAD_CHUNK_SIZE")  # 1MB chunks

    # ============ API Keys & Tokens ============
    add_api_key: str = Field(default="", alias="ADD_API_KEY")
    key: str = Field(default="", alias="KEY")

    # ============ Webhook Configuration ============
    webhook_url: str = Field(default="", alias="WEBHOOK_URL")

    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields
        json_schema_extra = {
            "admin_ids": {"type": "string", "description": "Comma-separated admin IDs"},
            "source_channels": {"type": "string", "description": "Comma-separated source channel IDs"},
        }

    @field_validator("admin_ids", mode="after")
    @classmethod
    def parse_admin_ids_after(cls, v):
        """Store parsed admin IDs for later access."""
        if isinstance(v, str):
            return v
        return ""

    @field_validator("source_channels", mode="after")
    @classmethod
    def parse_source_channels_after(cls, v):
        """Store parsed source channels for later access."""
        if isinstance(v, str):
            return v
        return ""

    def __init__(self, **data):
        """Parse comma-separated values after initialization."""
        super().__init__(**data)
        
        # Auto-detect concurrency limits from hardware if not explicitly set (= 0)
        if self.max_concurrent_channels == 0 or self.max_concurrent_downloads == 0 or self.max_concurrent_uploads == 0:
            auto_channels, auto_downloads, auto_uploads, cpu_count, ram_gb = calculate_optimal_concurrency()
            
            if self.max_concurrent_channels == 0:
                self.max_concurrent_channels = auto_channels
            if self.max_concurrent_downloads == 0:
                self.max_concurrent_downloads = auto_downloads
            if self.max_concurrent_uploads == 0:
                self.max_concurrent_uploads = auto_uploads
            
            print(f"\n{'='*60}")
            print(f"🚀 AUTO-CONFIGURATION (Hardware Detection)")
            print(f"{'='*60}")
            print(f"CPU Cores: {cpu_count}")
            print(f"RAM: {ram_gb:.1f}GB")
            print(f"\n⚙️  Parallel Processing Settings:")
            print(f"  • Max Concurrent Channels: {self.max_concurrent_channels}")
            print(f"  • Max Concurrent Downloads: {self.max_concurrent_downloads}")
            print(f"  • Max Concurrent Uploads: {self.max_concurrent_uploads}")
            print(f"{'='*60}\n")
        
        # Parse admin_ids string to list
        if self.admin_ids:
            self.admin_ids_list = [
                int(id_.strip()) for id_ in self.admin_ids.split(",") if id_.strip()
            ]
        
        # Parse source_channels string to list
        if self.source_channels:
            self.source_channels_list = []
            for channel_id in self.source_channels.split(","):
                channel_id = channel_id.strip()
                if channel_id:
                    try:
                        self.source_channels_list.append(int(channel_id))
                    except ValueError:
                        raise RuntimeError(
                            f"❌ Invalid SOURCE_CHANNELS value: '{channel_id}'\n"
                            f"Expected numeric channel ID (e.g., -1003615834886)\n\n"
                            f"For private channels, use the numeric ID:\n"
                            f"1. Forward a message from your private channel\n"
                            f"2. The bot will log: 'chat_id=XXXXX' (copy this number)\n"
                            f"3. Update .env: SOURCE_CHANNELS=XXXXX\n\n"
                            f"Or run: python get_channel_id.py"
                        )

    @property
    def app_dirs(self):
        """Create necessary application directories."""
        dirs = [
            Path(self.database_path).parent,
            Path(self.log_file).parent,
            Path(self.cache_directory),
            Path(self.file_storage_dir),
            Path(self.premium_video_folder),
            Path(self.free_video_folder),
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
        return dirs

    @property
    def active_worker_url(self) -> str:
        """Get active worker URL (stream_worker or cloudflare_worker_url)."""
        return self.stream_worker or self.cloudflare_worker_url or ""


# Load settings
try:
    settings = Settings()
except Exception as e:
    raise RuntimeError(f"Failed to load settings: {e}")

