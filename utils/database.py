"""
Database module for TeraBox Downloader Bot.
Manages SQLite database for tracking downloads, users, and logs.
"""

import sqlite3
import json
import os
from urllib.parse import urlparse
try:
    import pymysql
except Exception:
    pymysql = None
try:
    import psycopg2
except Exception:
    psycopg2 = None
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from config import settings
from utils.logger import logger, log_action


class MySQLConnection:
    """Light wrapper for pymysql connection to provide cursor() with sqlite-like interface."""
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self):
        return MySQLCursor(self._conn.cursor())

    def commit(self):
        return self._conn.commit()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


class MySQLCursor:
    def __init__(self, raw_cursor):
        self._cur = raw_cursor

    def execute(self, query, params=None):
        # Convert sqlite '?' placeholders to '%s' for PyMySQL
        if params is None:
            return self._cur.execute(query)
        q = query.replace('?', '%s')
        return self._cur.execute(q, params)

    def executemany(self, query, seq_of_params):
        q = query.replace('?', '%s')
        return self._cur.executemany(q, seq_of_params)

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def lastrowid(self):
        return getattr(self._cur, 'lastrowid', None)

    def close(self):
        try:
            self._cur.close()
        except Exception:
            pass


class PostgresConnection:
    """Wrapper for psycopg2 connection to provide sqlite-like cursor interface."""
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self):
        return PostgresCursor(self._conn.cursor())

    def commit(self):
        return self._conn.commit()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


class PostgresCursor:
    def __init__(self, raw_cursor):
        self._cur = raw_cursor

    def execute(self, query, params=None):
        # Convert sqlite '?' placeholders to '%s' for psycopg2
        if params is None:
            return self._cur.execute(query)
        q = query.replace('?', '%s')
        return self._cur.execute(q, params)

    def executemany(self, query, seq_of_params):
        q = query.replace('?', '%s')
        return self._cur.executemany(q, seq_of_params)

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def lastrowid(self):
        # psycopg2 cursor may not provide lastrowid; use RETURNING in queries when needed
        return getattr(self._cur, 'lastrowid', None)

    def close(self):
        try:
            self._cur.close()
        except Exception:
            pass


class DatabaseManager:
    """Manages SQLite database operations for the bot."""

    def __init__(self, db_path: str = None):
        """
        Initialize database manager.
        
        Args:
            db_path: Path to database file (uses config by default)
        """
        # Support optional MySQL or PostgreSQL via settings or env var
        self.mysql_url = getattr(settings, 'mysql_database_url', None) or os.environ.get("MYSQL_DATABASE_URL")
        self.postgres_url = getattr(settings, 'database_url', None) or os.environ.get("DATABASE_URL")
        self.db_path = db_path or settings.database_path
        if not self.mysql_url:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_database()

    def get_connection(self):
        """Get database connection."""
        # If PostgreSQL configured and psycopg2 available, return a wrapper connection
        if self.postgres_url and psycopg2:
            parsed = urlparse(self.postgres_url)
            user = parsed.username
            password = parsed.password
            host = parsed.hostname
            port = parsed.port or 5432
            dbname = parsed.path.lstrip('/')

            raw_conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=dbname
            )
            return PostgresConnection(raw_conn)

        # If MySQL configured and PyMySQL available, return a wrapper connection
        if self.mysql_url and pymysql:
            parsed = urlparse(self.mysql_url)
            user = parsed.username
            password = parsed.password
            host = parsed.hostname
            port = parsed.port or 3306
            dbname = parsed.path.lstrip('/')

            raw_conn = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=dbname,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
                charset='utf8mb4'
            )
            return MySQLConnection(raw_conn)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self):
        """Initialize database schema if not exists (sqlite only)."""
        if self.mysql_url and pymysql:
            logger.info("MySQL configured via MYSQL_DATABASE_URL — skipping sqlite schema creation (ensure schema exists).")
            return

        conn = self.get_connection()
        cursor = conn.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_downloads INTEGER DEFAULT 0,
                settings JSON DEFAULT '{}'
            )
        """)

        # Downloads table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                download_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                filename TEXT,
                filesize INTEGER,
                status TEXT DEFAULT 'pending',
                progress INTEGER DEFAULT 0,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Activity logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                level TEXT DEFAULT 'INFO',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Telegram messages cache (for progress updates)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_cache (
                message_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                download_id TEXT,
                message_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Cached backups table - stores metadata about backups stored in a backup/ database channel
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cached_backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                download_id TEXT,
                filename TEXT,
                filesize INTEGER,
                backup_channel_id INTEGER,
                backup_message_id INTEGER,
                image_src TEXT,
                extra JSON DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Cached videos table - for tracking group processor downloads
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cached_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_chat_id INTEGER,
                source_message_id INTEGER,
                terabox_link TEXT UNIQUE,
                filename TEXT,
                filesize INTEGER,
                thumb_path TEXT,
                backup_channel_id INTEGER,
                backup_message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Processed messages table - tracks which channel messages have been processed
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, message_id)
            )
        """)

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")

    def add_user(self, user_id: int, username: str = "", first_name: str = "", last_name: str = ""):
        """Add or update user record."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            """, (user_id, username, first_name, last_name))
            
            cursor.execute("""
                UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?
            """, (user_id,))
            
            conn.commit()
            log_action(user_id, "user_registered", f"{first_name} {last_name}")
        except Exception as e:
            logger.error(f"Error adding user: {e}")
        finally:
            conn.close()

    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def log_download(self, download_id: str, user_id: int, url: str, filename: str = "", filesize: int = 0):
        """Log a new download."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO downloads (download_id, user_id, url, filename, filesize)
                VALUES (?, ?, ?, ?, ?)
            """, (download_id, user_id, url, filename, filesize))
            
            cursor.execute("""
                UPDATE users SET total_downloads = total_downloads + 1 WHERE user_id = ?
            """, (user_id,))
            
            conn.commit()
            log_action(user_id, "download_logged", filename)
        except Exception as e:
            logger.error(f"Error logging download: {e}")
        finally:
            conn.close()

    def update_download_status(self, download_id: str, status: str, progress: int = 0, error_message: str = ""):
        """Update download status and progress."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            if status == "completed":
                cursor.execute("""
                    UPDATE downloads SET status = ?, progress = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE download_id = ?
                """, (status, 100, download_id))
            else:
                cursor.execute("""
                    UPDATE downloads SET status = ?, progress = ?, error_message = ?
                    WHERE download_id = ?
                """, (status, progress, error_message, download_id))
            
            conn.commit()
        except Exception as e:
            logger.error(f"Error updating download status: {e}")
        finally:
            conn.close()

    def get_download(self, download_id: str) -> Optional[Dict]:
        """Get download details."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM downloads WHERE download_id = ?", (download_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def get_user_downloads(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Get user's download history."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM downloads WHERE user_id = ? ORDER BY started_at DESC LIMIT ?
        """, (user_id, limit))
        
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def add_activity_log(self, user_id: int, action: str, details: str = "", level: str = "INFO"):
        """Add activity log entry."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO activity_logs (user_id, action, details, level)
                VALUES (?, ?, ?, ?)
            """, (user_id, action, details, level))
            conn.commit()
        except Exception as e:
            logger.error(f"Error adding activity log: {e}")
        finally:
            conn.close()

    def get_stats(self) -> Dict[str, Any]:
        """Get bot statistics."""
        conn = self.get_connection()
        cursor = conn.cursor()

        stats = {}
        
        try:
            cursor.execute("SELECT COUNT(*) as total FROM users")
            stats["total_users"] = cursor.fetchone()["total"]
            
            cursor.execute("SELECT SUM(total_downloads) as total FROM users")
            result = cursor.fetchone()["total"]
            stats["total_downloads"] = result if result else 0
            
            cursor.execute("""
                SELECT COUNT(*) as total FROM downloads WHERE status IN ('pending', 'downloading', 'uploading')
            """)
            stats["active_streams"] = cursor.fetchone()["total"]
            
            cursor.execute("""
                SELECT COUNT(*) as total FROM downloads WHERE status = 'failed'
            """)
            stats["failed_downloads"] = cursor.fetchone()["total"]
            
            cursor.execute("""
                SELECT SUM(filesize) as total FROM downloads WHERE status = 'completed'
            """)
            result = cursor.fetchone()["total"]
            stats["total_bytes_downloaded"] = result if result else 0
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
        finally:
            conn.close()

        return stats

    def save_backup_record(
        self,
        download_id: str,
        filename: str,
        filesize: int,
        backup_channel_id: int,
        backup_message_id: int,
        image_src: str = "",
        extra: Optional[Dict] = None,
    ) -> int:
        """Save a backup record and return its numeric id."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            extra_json = json.dumps(extra or {})
            cursor.execute(
                """
                INSERT INTO cached_backups (
                    download_id, filename, filesize, backup_channel_id,
                    backup_message_id, image_src, extra
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (download_id, filename, filesize, backup_channel_id, backup_message_id, image_src, extra_json),
            )
            conn.commit()
            record_id = cursor.lastrowid
            log_action(0, "backup_saved", f"backup_id={record_id} download_id={download_id}")
            return record_id
        except Exception as e:
            logger.error(f"Error saving backup record: {e}")
            return 0
        finally:
            conn.close()

    def get_cached_by_id(self, record_id: int) -> Optional[Dict]:
        """Retrieve a cached backup record by its numeric id."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM cached_backups WHERE id = ?", (record_id,))
            row = cursor.fetchone()
            if not row:
                return None

            data = dict(row)
            # Parse JSON extra field
            try:
                data["extra"] = json.loads(data.get("extra") or "{}")
            except Exception:
                data["extra"] = {}

            return data
        except Exception as e:
            logger.error(f"Error fetching cached backup id={record_id}: {e}")
            return None
        finally:
            conn.close()

    def get_cached_video_by_id(self, record_id: int) -> Optional[Dict]:
        """Retrieve a cached_videos record by id and normalize keys to cached_backups shape."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM cached_videos WHERE id = ?", (record_id,))
            row = cursor.fetchone()
            if not row:
                return None

            data = dict(row)
            # Normalize to the same shape as cached_backups used by handlers
            normalized = {
                "id": data.get("id"),
                "download_id": None,
                "filename": data.get("filename"),
                "filesize": data.get("filesize"),
                "backup_channel_id": data.get("backup_channel_id"),
                "backup_message_id": data.get("backup_message_id"),
                "image_src": data.get("thumb_path"),
                "extra": {
                    "source_chat_id": data.get("source_chat_id"),
                    "source_message_id": data.get("source_message_id"),
                },
                "created_at": data.get("created_at")
            }
            return normalized
        except Exception as e:
            logger.error(f"Error fetching cached video id={record_id}: {e}")
            return None
        finally:
            conn.close()

    def add_cached_video(
        self,
        source_chat_id: int,
        source_message_id: int,
        terabox_link: str,
        filename: str,
        filesize: int,
        thumb_path: str = "",
        backup_channel_id: int = None,
        backup_message_id: int = None,
    ) -> int:
        """Save a cached video record for group processor. Returns record id."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO cached_videos (
                    source_chat_id, source_message_id, terabox_link, filename,
                    filesize, thumb_path, backup_channel_id, backup_message_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (source_chat_id, source_message_id, terabox_link, filename,
                 filesize, thumb_path, backup_channel_id, backup_message_id),
            )
            conn.commit()
            record_id = cursor.lastrowid
            logger.info(f"Cached video record id={record_id} for link={terabox_link[:50]}")
            return record_id
        except Exception as e:
            logger.error(f"Error saving cached video: {e}")
            return 0
        finally:
            conn.close()

    def get_cached_by_link(self, terabox_link: str) -> Optional[Dict]:
        """Retrieve a cached video record by TeraBox link."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM cached_videos WHERE terabox_link = ?", (terabox_link,))
            row = cursor.fetchone()
            if not row:
                return None
            return dict(row)
        except Exception as e:
            logger.error(f"Error fetching cached video by link: {e}")
            return None
        finally:
            conn.close()
    def is_group_message_processed(self, chat_id: int, message_id: int, link: str) -> bool:
        """Check if a message from a group+link combo was already processed."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id FROM cached_videos 
                WHERE source_chat_id = ? AND source_message_id = ? AND terabox_link = ?
                LIMIT 1
            """, (chat_id, message_id, link))
            
            result = cursor.fetchone()
            return result is not None
        except Exception as e:
            logger.error(f"Error checking processed message: {e}")
            return False
        finally:
            conn.close()

    def save_group_message_processed(
        self,
        chat_id: int,
        message_id: int,
        terabox_link: str,
        filename: str = "",
        filesize: int = 0,
        thumb_path: str = "",
        link_label: str = "",
    ) -> bool:
        """Save a processed group message to prevent duplicate downloads."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Store link_label in extra JSON
            extra = json.dumps({"link_label": link_label})
            cursor.execute("""
                INSERT OR IGNORE INTO cached_videos 
                (source_chat_id, source_message_id, terabox_link, filename, filesize, thumb_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (chat_id, message_id, terabox_link, filename, filesize, thumb_path))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving processed group message: {e}")
            return False
        finally:
            conn.close()

    def update_group_message_backup(
        self,
        chat_id: int,
        message_id: int,
        terabox_link: str,
        backup_channel_id: int,
        backup_message_id: int,
    ) -> bool:
        """Update a group message record with backup channel info."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE cached_videos
                SET backup_channel_id = ?, backup_message_id = ?
                WHERE source_chat_id = ? AND source_message_id = ? AND terabox_link = ?
            """, (backup_channel_id, backup_message_id, chat_id, message_id, terabox_link))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating group message backup: {e}")
            return False
        finally:
            conn.close()

    def get_group_videos_by_message(
        self,
        chat_id: int,
        message_id: int,
    ) -> List[Dict]:
        """Get all cached videos for a source message with their labels."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Note: For SQLite we can't parse JSON directly in old versions
            # So we fetch and parse in Python
            cursor.execute("""
                SELECT id, filename, filesize FROM cached_videos 
                WHERE source_chat_id = ? AND source_message_id = ? 
                ORDER BY id
            """, (chat_id, message_id))
            
            rows = cursor.fetchall()
            result = []
            for i, row in enumerate(rows, start=1):
                d = dict(row)
                d['label'] = d.get('link_label', f"Part {i}")  # Fallback to Part N
                result.append(d)
            return result
        except Exception as e:
            logger.error(f"Error fetching group videos: {e}")
            return []
        finally:
            conn.close()

    def get_cached_video_label(self, video_id: int) -> str:
        """Get link label for a cached video ID."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id FROM cached_videos WHERE id = ?
                LIMIT 1
            """, (video_id,))
            
            row = cursor.fetchone()
            if row:
                # For now, return a default since we're not storing label as column
                # This is handled by the new label extraction logic
                return None
            return None
        except Exception as e:
            logger.error(f"Error fetching video label: {e}")
            return None
        finally:
            conn.close()

    def is_message_processed(self, chat_id: int, message_id: int) -> bool:
        """Check if a message from a channel has already been processed."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id FROM processed_messages 
                WHERE chat_id = ? AND message_id = ?
                LIMIT 1
            """, (chat_id, message_id))
            
            result = cursor.fetchone()
            return result is not None
        except Exception as e:
            logger.error(f"Error checking processed message: {e}")
            return False
        finally:
            conn.close()

    def mark_message_processed(self, chat_id: int, message_id: int) -> bool:
        """Mark a message as processed to prevent duplicate processing on bot restart."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR IGNORE INTO processed_messages (chat_id, message_id)
                VALUES (?, ?)
            """, (chat_id, message_id))
            
            conn.commit()
            logger.debug(f"Marked message processed: chat={chat_id} msg={message_id}")
            return True
        except Exception as e:
            logger.error(f"Error marking message processed: {e}")
            return False
        finally:
            conn.close()

# Global database instance
db = DatabaseManager()
