#!/usr/bin/env python3
"""
Database Record Migration Utility

This script helps recover videos that were uploaded successfully but don't have
database records (orphaned videos). It fetches recent messages from the backup
channel and creates missing database records.
"""

import sys
import os
import asyncio
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pyrogram import Client
from pyrogram.types import Message
from config import settings
from utils.database import db
from utils.logger import logger


async def scan_backup_channel_for_orphans(hours: int = 24):
    """
    Scan backup channel for messages without database records.
    
    Args:
        hours: Look back this many hours for orphaned videos
    """
    print(f"\n🔍 Scanning backup channel for videos from last {hours} hours...\n")
    
    try:
        client = Client("terabox_migrator")
        await client.start()
        
        backup_channel_id = int(settings.backup_channel_id) if settings.backup_channel_id else 0
        
        if not backup_channel_id:
            print("❌ BACKUP_CHANNEL_ID not configured")
            await client.stop()
            return
        
        print(f"📺 Backup Channel ID: {backup_channel_id}")
        
        # Get messages from last N hours
        messages_checked = 0
        orphans_found = 0
        records_created = 0
        
        # Fetch recent messages
        async for message in client.get_chat_history(backup_channel_id, limit=200):
            messages_checked += 1
            
            if not message.media:
                continue
            
            # Check if this message has a database record
            existing_record = None
            try:
                # Try to find by message ID
                conn = db.get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM cached_backups WHERE backup_message_id = ?",
                    (message.id,)
                )
                existing_record = cursor.fetchone()
                conn.close()
            except:
                pass
            
            if existing_record:
                continue  # Already has a record
            
            # This is an orphan - try to extract info
            orphans_found += 1
            
            filename = "Unknown"
            filesize = 0
            
            # Try to get filename from caption
            if message.caption:
                # Extract filename from caption or use first line
                lines = message.caption.split('\n')
                filename = lines[0][:100] if lines else "Unknown"
            
            # Try to get file size
            if message.video:
                filesize = message.video.file_size or 0
                if not filename or filename == "Unknown":
                    filename = f"video_{message.id}.mp4"
            elif message.document:
                filesize = message.document.file_size or 0
                if not filename or filename == "Unknown":
                    filename = message.document.file_name or f"file_{message.id}"
            
            print(f"\n📦 Orphan #{orphans_found}:")
            print(f"   Message ID: {message.id}")
            print(f"   Filename: {filename}")
            print(f"   File Size: {filesize / (1024*1024):.2f} MB")
            print(f"   Date: {message.date}")
            
            # Ask user if they want to create a record
            response = input("   Create database record? (y/n/skip): ").strip().lower()
            
            if response == 'y':
                try:
                    record_id = db.save_backup_record(
                        download_id=f"migrated_{message.id}",
                        filename=filename,
                        filesize=filesize,
                        backup_channel_id=backup_channel_id,
                        backup_message_id=message.id,
                        image_src="",
                        extra={
                            "migrated": True,
                            "migration_date": datetime.now().isoformat(),
                            "original_message_date": message.date.isoformat() if message.date else None,
                            "original_caption": message.caption[:200] if message.caption else ""
                        }
                    )
                    
                    if record_id and record_id > 0:
                        records_created += 1
                        print(f"   ✅ Record created with ID: {record_id}")
                    else:
                        print(f"   ❌ Failed to create record")
                except Exception as e:
                    print(f"   ❌ Error creating record: {e}")
            elif response == 'skip':
                print("   ⏭️  Skipped this message")
            else:
                print("   ⏭️  No record created")
        
        await client.stop()
        
        # Summary
        print("\n" + "="*70)
        print("\n📋 MIGRATION SUMMARY:")
        print(f"   Messages checked: {messages_checked}")
        print(f"   Orphans found: {orphans_found}")
        print(f"   Records created: {records_created}")
        print(f"   Records skipped: {orphans_found - records_created}")
        print("\n" + "="*70 + "\n")
        
    except Exception as e:
        print(f"❌ Error during scan: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            await client.stop()
        except:
            pass


async def count_orphans(hours: int = 24) -> int:
    """Count orphaned messages without actually creating records."""
    print(f"\n📊 Counting orphan videos from last {hours} hours...\n")
    
    try:
        client = Client("terabox_counter")
        await client.start()
        
        backup_channel_id = int(settings.backup_channel_id) if settings.backup_channel_id else 0
        
        if not backup_channel_id:
            print("❌ BACKUP_CHANNEL_ID not configured")
            await client.stop()
            return 0
        
        orphan_count = 0
        message_count = 0
        
        async for message in client.get_chat_history(backup_channel_id, limit=200):
            message_count += 1
            
            if not message.media:
                continue
            
            # Check if has database record
            existing = None
            try:
                conn = db.get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM cached_backups WHERE backup_message_id = ?",
                    (message.id,)
                )
                existing = cursor.fetchone()
                conn.close()
            except:
                pass
            
            if not existing:
                orphan_count += 1
        
        await client.stop()
        
        print(f"   Total messages: {message_count}")
        print(f"   Orphan videos: {orphan_count}")
        print(f"   Records in DB: {message_count - orphan_count}\n")
        
        return orphan_count
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 0
    finally:
        try:
            await client.stop()
        except:
            pass


def main():
    """Main entry point."""
    print("\n" + "🔄 DATABASE RECORD MIGRATION UTILITY".center(70))
    print("=" * 70)
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "count":
            orphans = asyncio.run(count_orphans(hours=int(sys.argv[2]) if len(sys.argv) > 2 else 24))
            return 0 if orphans >= 0 else 1
            
        elif command == "migrate":
            asyncio.run(scan_backup_channel_for_orphans(hours=int(sys.argv[2]) if len(sys.argv) > 2 else 24))
            return 0
        
        elif command == "help":
            print("\nUsage:")
            print("  python3 database_migration.py count [hours]")
            print("      → Count orphaned videos from last N hours")
            print("  python3 database_migration.py migrate [hours]") 
            print("      → Interactive mode: find orphans and create records")
            print("  python3 database_migration.py help")
            print("      → Show this help message\n")
            return 0
        
        else:
            print(f"❌ Unknown command: {command}\n")
            return 1
    
    else:
        print("\nUsage:")
        print("  python3 database_migration.py count [hours]")
        print("      → Count orphaned videos from last N hours (default: 24)")
        print("  python3 database_migration.py migrate [hours]")
        print("      → Interactive mode: find orphans and create records (default: 24)")
        print("  python3 database_migration.py help")
        print("      → Show detailed help\n")
        print("Examples:")
        print("  python3 database_migration.py count 48")
        print("      → Count orphans from last 48 hours")
        print("  python3 database_migration.py migrate")
        print("      → Start interactive migration mode\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
