#!/usr/bin/env python3
"""
Database Health Check Utility

Run this script to diagnose database integrity and record persistence issues.
"""

import sys
import os
import sqlite3
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.database import db
from config import settings
from utils.logger import logger


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}\n")


def check_database_connection():
    """Check if database can be accessed."""
    print_header("🔌 DATABASE CONNECTION CHECK")
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        conn.close()
        
        print("✅ Database connection: OK")
        print(f"   Database type: {settings.database_type}")
        print(f"   Connection string: {settings.database_type}://...")
        return True
    except Exception as e:
        print(f"❌ Database connection: FAILED")
        print(f"   Error: {e}")
        return False


def check_tables_exist():
    """Check if required tables exist."""
    print_header("📋 TABLES CHECK")
    tables_to_check = ["cached_backups", "cached_videos", "processed_messages"]
    
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        all_exist = True
        for table in tables_to_check:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table} LIMIT 1")
                count = cursor.fetchone()[0]
                print(f"✅ {table}: EXISTS ({count} records)")
            except Exception as e:
                print(f"❌ {table}: MISSING or ERROR - {e}")
                all_exist = False
        
        conn.close()
        return all_exist
    except Exception as e:
        print(f"❌ Error checking tables: {e}")
        return False


def check_database_integrity():
    """Run full database integrity check."""
    print_header("📊 DATABASE INTEGRITY CHECK")
    try:
        diagnostics = db.check_database_integrity()
        
        if diagnostics:
            print(f"Cached Backups:        {diagnostics.get('cached_backups_count', 0):,} records")
            print(f"Cached Videos:         {diagnostics.get('cached_videos_count', 0):,} records")
            print(f"Processed Messages:    {diagnostics.get('processed_messages_count', 0):,} entries")
            print(f"Total Backup Size:     {diagnostics.get('total_backup_size_mb', 0):,.2f} MB")
            print(f"Database File Size:    {diagnostics.get('database_file_size_mb', 0):,.2f} MB")
            print("\n✅ Integrity check passed")
            return True
        else:
            print("❌ Integrity check failed")
            return False
    except Exception as e:
        print(f"❌ Error during integrity check: {e}")
        return False


def check_recent_records():
    """Check if recent records can be retrieved."""
    print_header("🔍 RECENT RECORDS CHECK")
    try:
        records = db.get_all_cached_backups()
        
        if not records:
            print("⚠️  No records found in database")
            return True
        
        print(f"Found {len(records)} recent records:\n")
        
        for i, rec in enumerate(records[:10], 1):
            record_id = rec.get('id', '?')
            filename = rec.get('filename', '')[:50]
            channel_id = rec.get('backup_channel_id', '?')
            msg_id = rec.get('backup_message_id', '?')
            
            print(f"  {i}. ID {record_id}: {filename}")
            print(f"     Channel: {channel_id}, Message: {msg_id}")
        
        print(f"\n✅ Record retrieval: OK")
        return True
    except Exception as e:
        print(f"❌ Error retrieving records: {e}")
        return False


def test_record_persistence():
    """Test if a new record can be saved and retrieved."""
    print_header("✏️  RECORD PERSISTENCE TEST")
    try:
        # Create a test record
        import uuid
        from datetime import datetime
        
        test_id = str(uuid.uuid4())[:8]
        test_filename = f"TEST_RECORD_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        
        print(f"Creating test record: {test_filename}")
        
        # Save the record
        record_id = db.save_backup_record(
            download_id=test_id,
            filename=test_filename,
            filesize=1024000,
            backup_channel_id=-1001234567890,  # Test channel ID
            backup_message_id=12345,
            image_src="test_image.jpg",
            extra={"test": True, "timestamp": datetime.now().isoformat()}
        )
        
        if record_id == 0:
            print(f"❌ Failed to save test record")
            return False
        
        print(f"✅ Record saved with ID: {record_id}")
        
        # Try to retrieve it
        import time
        time.sleep(0.2)  # Brief delay
        
        retrieved = db.get_cached_by_id(record_id)
        
        if retrieved:
            print(f"✅ Record retrieved successfully")
            print(f"   Filename: {retrieved.get('filename')}")
            print(f"   Channel: {retrieved.get('backup_channel_id')}")
            print(f"\n✅ Persistence test: PASSED")
            return True
        else:
            print(f"❌ Failed to retrieve test record ID {record_id}")
            print(f"\n❌ Persistence test: FAILED")
            return False
            
    except Exception as e:
        print(f"❌ Error during persistence test: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all health checks."""
    print("\n" + "🏥 TERABOX BOT DATABASE HEALTH CHECK".center(70))
    print("=" * 70)
    
    results = {
        "Connection": check_database_connection(),
        "Tables": check_tables_exist(),
        "Integrity": check_database_integrity(),
        "Recent Records": check_recent_records(),
        "Persistence": test_record_persistence(),
    }
    
    # Summary
    print_header("📋 SUMMARY")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for check, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}  {check}")
    
    print(f"\nOverall: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n✅ Database is healthy and working correctly!")
    else:
        print("\n⚠️  Some checks failed. Please review the errors above.")
    
    print("\n" + "="*70 + "\n")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
