#!/usr/bin/env python3
"""
Clear processed messages from the database to restart fresh.
This allows all videos to be reprocessed from scratch.
"""

from utils.database import db
import sys

def main():
    """Clear the processed_messages table."""
    print("=" * 50)
    print("⚠️  Database Cleanup Tool")
    print("=" * 50)
    
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Get count before deletion
        cursor.execute("SELECT COUNT(*) FROM processed_messages")
        count_before = cursor.fetchone()[0]
        print(f"\n📊 Current processed messages in DB: {count_before}")
        
        # Confirm deletion
        if count_before > 0:
            response = input(f"\n⚠️  Delete all {count_before} processed message records? (yes/no): ").strip().lower()
            if response != 'yes':
                print("❌ Cancelled. Database unchanged.")
                conn.close()
                return
        
        # Clear the table
        cursor.execute("DELETE FROM processed_messages")
        conn.commit()
        
        print(f"✅ Deleted {cursor.rowcount} records from processed_messages table")
        print("✅ Database cleared successfully!\n")
        print("📝 Next steps:")
        print("1. Run: python main.py")
        print("2. Bot will reprocess ALL videos from source channels")
        print("3. Check logs: tail -f logs/bot.log | grep 'NEW messages'")
        print("\n" + "=" * 50)
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error clearing database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
