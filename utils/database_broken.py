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
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from config import settings
from utils.logger import logger, log_action


class DatabaseManager:
    """Manages SQLite database operations for the bot."""

    def __init__(self, db_path: str = None):
        """
        Initialize database manager.
        
        Args:
            db_path: Path to database file (uses config by default)
        """
        # Support optional MySQL via settings or env var
        self.mysql_url = getattr(settings, 'mysql_database_url', None) or os.environ.get("MYSQL_DATABASE_URL")
        self.db_path = db_path or settings.database_path
        if not self.mysql_url:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_database()

    def get_connection(self):
        """Get database connection."""
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

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")


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

    def init_database(self):
        """Initialize database schema if not exists."""
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

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")

    def add_user(self, user_id: int, username: str = "", first_name: str = "", last_name: str = ""):
        """
        Add or update user record.
        
        Args:
            user_id: Telegram user ID
            username: Telegram username
            first_name: User's first name
            last_name: User's last name
        """
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
        """
        Get user by ID.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            User data as dictionary or None
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def log_download(self, download_id: str, user_id: int, url: str, filename: str = "", filesize: int = 0):
        """
        Log a new download.
        
        Args:
            download_id: Unique download identifier
            user_id: Telegram user ID
            url: Download URL
            filename: Downloaded filename
            filesize: File size in bytes
        """
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
        """
        Update download status and progress.
        
        Args:
            download_id: Download ID
            status: Status (pending, downloading, uploading, completed, failed)
            progress: Progress percentage (0-100)
            error_message: Error message if failed
        """
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
        """
        Get download details.
        
        Args:
            download_id: Download ID
            
        Returns:
            Download data or None
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM downloads WHERE download_id = ?", (download_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def get_user_downloads(self, user_id: int, limit: int = 10) -> List[Dict]:
        """
        Get user's download history.
        
        Args:
            user_id: User ID
            limit: Number of downloads to retrieve
            
        Returns:
            List of downloads
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM downloads WHERE user_id = ? ORDER BY started_at DESC LIMIT ?
        """, (user_id, limit))
        
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def add_activity_log(self, user_id: int, action: str, details: str = "", level: str = "INFO"):
        """
        Add activity log entry.
        
        Args:
            user_id: User ID
            action: Action name
            details: Action details
            level: Log level
        """
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
        """
        Get bot statistics.
        
        Returns:
            Statistics dictionary
        """
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

    def get_detailed_stats(self) -> Dict:
        """Get detailed statistics for admin panel."""
        conn = self.get_connection()
        cursor = conn.cursor()
        stats = {}

        try:
            # User stats
            cursor.execute("SELECT COUNT(*) as total FROM users")
            stats["total_users"] = cursor.fetchone()["total"]
            
            cursor.execute("""
                SELECT COUNT(*) as total FROM users 
                WHERE date(joined_at) = date('now')
            """)
            stats["users_today"] = cursor.fetchone()["total"]
            
            cursor.execute("""
                SELECT COUNT(*) as total FROM users 
                WHERE date(joined_at) >= date('now', '-7 days')
            """)
            stats["users_this_week"] = cursor.fetchone()["total"]
            
            # Download stats
            cursor.execute("SELECT COUNT(*) as total FROM downloads WHERE status = 'completed'")
            stats["total_downloads"] = cursor.fetchone()["total"]
            
            cursor.execute("""
                SELECT COUNT(*) as total FROM downloads 
                WHERE status = 'completed' AND date(created_at) = date('now')
            """)
            stats["downloads_today"] = cursor.fetchone()["total"]
            
            cursor.execute("""
                SELECT AVG(filesize) as avg FROM downloads WHERE status = 'completed'
            """)
            result = cursor.fetchone()["avg"]
            stats["avg_file_size"] = int(result) if result else 0
            
            cursor.execute("""
                SELECT SUM(filesize) as total FROM downloads WHERE status = 'completed'
            """)
            result = cursor.fetchone()["total"]
            stats["total_size"] = result if result else 0
            
            # Error stats
            cursor.execute("SELECT COUNT(*) as total FROM activity_logs WHERE level = 'ERROR'")
            stats["total_errors"] = cursor.fetchone()["total"]
            
            cursor.execute("""
                SELECT COUNT(*) as total FROM activity_logs 
                WHERE level = 'ERROR' AND date(timestamp) = date('now')
            """)
            stats["errors_today"] = cursor.fetchone()["total"]
            
        except Exception as e:
            logger.error(f"Error getting detailed stats: {e}")
        finally:
            conn.close()

        return stats

    def get_recent_downloads(self, limit: int = 10) -> List[Dict]:
        """Get recent downloads."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT download_id, filename, file_size, status, created_at 
                FROM downloads 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            
            downloads = []
            for row in cursor.fetchall():
                downloads.append({
                    "download_id": row["download_id"],
                    "filename": row["filename"],
                    "file_size": row["file_size"],
                    "status": row["status"],
                    "user_id": row.get("user_id", "N/A"),
                    "created_at": row["created_at"]
                })
            
            return downloads
        except Exception as e:
            logger.error(f"Error getting recent downloads: {e}")
            return []
        finally:
            conn.close()

    def get_active_users(self, limit: int = 10) -> List[Dict]:
        """Get active users."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT user_id, total_downloads, last_active 
                FROM users 
                WHERE last_active >= datetime('now', '-7 days')
                ORDER BY total_downloads DESC 
                LIMIT ?
            """, (limit,))
            
            users = []
            for row in cursor.fetchall():
                users.append({
                    "user_id": row["user_id"],
                    "download_count": row["total_downloads"],
                    "last_active": row["last_active"]
                })
            
            return users
        except Exception as e:
            logger.error(f"Error getting active users: {e}")
            return []
        finally:
            conn.close()

    def get_db_info(self) -> Dict:
        """Get database information."""
        conn = self.get_connection()
        cursor = conn.cursor()
        info = {}

        try:
            cursor.execute("SELECT COUNT(*) as total FROM users")
            info["users"] = cursor.fetchone()["total"]
            
            cursor.execute("SELECT COUNT(*) as total FROM downloads")
            info["downloads"] = cursor.fetchone()["total"]
            
            cursor.execute("SELECT COUNT(*) as total FROM activity_logs")
            info["logs"] = cursor.fetchone()["total"]
            
            cursor.execute("SELECT COUNT(*) as total FROM message_cache")
            info["cache"] = cursor.fetchone()["total"]
            
            # Get database file size
            import os
            db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            info["size"] = db_size
            
        except Exception as e:
            logger.error(f"Error getting db info: {e}")
        finally:
            conn.close()

        return info

    def get_user_info(self, user_id: int) -> Optional[Dict]:
        """Get detailed user information."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM users WHERE user_id = ?
            """, (user_id,))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
        finally:
            conn.close()

        return None

    def clear_failed_downloads(self) -> int:
        """Clear failed downloads from queue."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT COUNT(*) as total FROM downloads WHERE status = 'failed'")
            count = cursor.fetchone()["total"]
            
            cursor.execute("DELETE FROM downloads WHERE status = 'failed'")
            conn.commit()
            
            logger.info(f"Cleared {count} failed downloads")
            return count
        except Exception as e:
            logger.error(f"Error clearing failed downloads: {e}")
            return 0
        finally:
            conn.close()

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
        """
        Save a backup record and return its numeric id.

        Args:
            download_id: Original download id
            filename: Stored filename
            filesize: File size in bytes
            backup_channel_id: Telegram channel ID where backup message was stored
            backup_message_id: Telegram message id of the backup
            image_src: Thumbnail or image source URL used for upload
            extra: Optional extra metadata

        Returns:
            Integer id of the cached backup record
        """
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
        """
        Retrieve a cached backup record by its numeric id.

        Args:
            record_id: Numeric id returned from `save_backup_record`

        Returns:
            Record dict or None
        """
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


# Global database instance
db = DatabaseManager()

