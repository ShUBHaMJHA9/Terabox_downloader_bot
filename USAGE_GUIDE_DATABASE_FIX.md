# 🚀 Database Persistence Fix - Complete Usage Guide

## Quick Start

Your bot now has **automatic retry logic** and **save verification** to ensure videos upload and persist correctly. Here's what happens now:

### Before (Old Behavior) ❌
1. Video uploads to backup channel
2. Record saved to database (maybe?)
3. Button posted to source group
4. User clicks button → **"Video not found"** error (record_id = 0)

### After (New Behavior) ✅
1. Video uploads to backup channel
2. **Retry mechanism** (up to 3 attempts) saves record
3. **Verification check** confirms record is in database
4. Only posts button if save + verify succeeds
5. User clicks button → **Works perfectly** ✅

---

## What Changed

### 1. Database Save Automatically Retries ✅
When saving a record to database:
- **Attempt 1**: Try to save immediately
- **Attempt 2** (if 1 fails): Retry after 0.5 seconds
- **Attempt 3** (if 2 fails): Retry after 1.0 second
- Returns 0 if all 3 attempts fail

**Where**: `utils/database.py` → `save_backup_record()` method

### 2. Handler Verifies Saves ✅
After saving, the bot verifies the record:
- **Immediate check** (0.1s after save): Can we retrieve it?
- **Delayed check** (if immediate fails): Try again after 0.5s
- If both fail: Don't post button, log error

**Where**: `handlers/channel_forwarder.py` → `process_terabox_link()` function

### 3. Bot Displays Database Health on Startup ✅
When bot starts, shows:
- Number of records in database
- Total backup size
- Recent cached videos
- Database file size

**Example startup output**:
```
🔍 DATABASE DIAGNOSTICS:
  Cached Backups: 42 records
  Cached Videos: 15 records
  Total Backup Size: 250.50 MB

📦 RECENT CACHED RECORDS:
  ID  42: Popular_Video.mp4
  ID  41: Music_Collection.mp4
```

---

## New Tools Available

### 1. 🏥 Database Health Check Script

**Purpose**: Diagnose database issues and verify everything is working

**How to use**:
```bash
python3 database_health_check.py
```

**What it checks**:
- ✅ Database connection working
- ✅ All required tables exist
- ✅ Record counts and sizes
- ✅ Can retrieve recent records
- ✅ Can save and retrieve test record

**Example output**:
```
🏥 TERABOX BOT DATABASE HEALTH CHECK

🔌 DATABASE CONNECTION CHECK
✅ Database connection: OK
   Database type: sqlite

📋 TABLES CHECK
✅ cached_backups: EXISTS (42 records)
✅ cached_videos: EXISTS (15 records)

📊 DATABASE INTEGRITY CHECK
Cached Backups: 42 records
Cached Videos: 15 records
Total Backup Size: 250.50 MB
✅ Integrity check passed

🔍 RECENT RECORDS CHECK
Found 10 recent records
✅ Record retrieval: OK

✏️  RECORD PERSISTENCE TEST
✅ Record saved with ID: 43
✅ Record retrieved successfully
✅ Persistence test: PASSED

📋 SUMMARY
✅ PASS  Connection
✅ PASS  Tables
✅ PASS  Integrity
✅ PASS  Recent Records
✅ PASS  Persistence

Overall: 5/5 checks passed
✅ Database is healthy and working correctly!
```

**Use this when**: Database issues, videos not saving, startup diagnostics look bad

---

### 2. 🔄 Database Migration Utility

**Purpose**: Recover videos that uploaded successfully but don't have database records

**How to use**:

#### Count orphaned videos (no database record)
```bash
# Check last 24 hours
python3 database_migration.py count

# Check last 48 hours
python3 database_migration.py count 48

# Output:
#   Total messages: 200
#   Orphan videos: 15
#   Records in DB: 185
```

#### Interactive migration mode (with prompts)
```bash
# Migrate videos from last 24 hours
python3 database_migration.py migrate

# For each orphan found, you'll be asked:
# 📦 Orphan #1:
#    Message ID: 12345
#    Filename: Beautiful_Video.mp4
#    File Size: 450.25 MB
#    Date: 2024-01-15 14:30:00
#    Create database record? (y/n/skip):

# Type:
#   y = Create database record for this video
#   n = Skip this video
#   skip = Skip to next video

# Migrate videos from last 72 hours
python3 database_migration.py migrate 72
```

**What it does**:
1. Scans backup channel for videos uploaded in last N hours
2. Checks if each video has a database record
3. For missing records, shows you the video details
4. Asks you to confirm before creating record
5. Creates record with migration metadata

**Use this when**: Videos were uploaded before the fix but didn't get database records

---

## Monitoring Logs

### Success Indicators ✅
Look for these in bot logs:
```
[ChannelForwarder] ✅ Verified record saved: id=42, filename=Video.mp4
[Database] ✅ Saved backup record (attempt 1): id=42, filename=Video.mp4
```

### Retry Indicators ⚠️
If you see these, retries are working:
```
[Database] ⚠️  Save attempt 2/3 failed: [error details]
[Database] ⚠️  Save attempt 3/3 failed: [error details]
```

### Error Indicators ❌
If you see these, there's a problem:
```
[ChannelForwarder] ❌ Failed to save backup record after all retries
[ChannelForwarder] ❌ Record saved but verification failed - not found in DB!
```

---

## Troubleshooting

### Problem: "Videos upload but buttons don't work"
**Solution**:
1. Run health check: `python3 database_health_check.py`
2. Check if says "✅ Database is healthy"
3. If not, see specific failure and fix

### Problem: "Database file seems empty"
**Solution**:
1. Check database connection: `python3 database_health_check.py`
2. Look for error messages about connection
3. Verify BACKUP_CHANNEL_ID and backup channel exists

### Problem: "Some old videos not in database"
**Solution**:
1. Count orphans: `python3 database_migration.py count 720`
2. If found: `python3 database_migration.py migrate`
3. For each orphan, decide whether to recover it

### Problem: "Logs show save attempt 2/3 or 3/3"
**Meaning**: Retry logic activated (transient DB issue)
**Action**: Monitor for now; if persists run health check

---

## Performance Impact

| Operation | Time Added | When |
|-----------|------------|------|
| Save retry logic | 0 ms (no retry) or +0.5-1.5s (on retry) | Only if DB unavailable |
| Verification check | +0.1s immediate + optional +0.5s delayed | Every save |
| Startup diagnostics | +100-200 ms on startup | Once at boot |
| Migration scan | ~1s per 50 messages | Manual only |

**Impact**: Negligible for successful saves (just adds verification), helps recovery on failures

---

## Manual Database Queries

If you need to check the database directly:

### View all records
```python
python3
>>> from utils.database import db
>>> records = db.get_all_cached_backups()
>>> for r in records[:5]:
>>>     print(f"ID {r['id']}: {r['filename']}")
```

### Check a specific record
```python
>>> from utils.database import db
>>> record = db.get_cached_by_id(42)
>>> print(record)
```

### Get database statistics
```python
>>> from utils.database import db
>>> stats = db.check_database_integrity()
>>> print(stats)
```

### Manually add missing record
```python
from utils.database import db

record_id = db.save_backup_record(
    download_id="manual_add_123",
    filename="Recovered_Video.mp4",
    filesize=1000000000,  # 1 GB in bytes
    backup_channel_id=-1001234567890,  # Your backup channel ID
    backup_message_id=12345,            # The message ID in backup channel
    image_src="your_image_url.jpg",
    extra={"manually_added": True}
)
print(f"Created record: {record_id}")
```

---

## Command Reference

```bash
# Start bot (unchanged)
python3 main.py

# Run health check
python3 database_health_check.py

# Count orphaned videos
python3 database_migration.py count [hours]

# Recover orphaned videos (interactive)
python3 database_migration.py migrate [hours]

# Show migration help
python3 database_migration.py help

# Python: Check database status
python3 -c "from utils.database import db; stats = db.check_database_integrity(); print(stats)"
```

---

## Quick Diagnostic Steps

**Step 1**: Check if database is working
```bash
python3 database_health_check.py
```
If any checks fail, note which ones and investigate

**Step 2**: Check if there are orphaned videos
```bash
python3 database_migration.py count
```
If orphan_count > 0, run migration to recover

**Step 3**: Monitor logs on next video upload
Look for `✅ Verified record saved` or `❌ Record failed verification`

**Step 4**: If still broken
- Run health check again
- Try migration
- Check if database is on ephemeral (temporary) filesystem

---

## Summary

✅ **Videos now save with automatic retry** (3 attempts, exponential backoff)
✅ **Saves are verified before posting buttons**
✅ **Startup shows database health**
✅ **Health check script for diagnostics**
✅ **Migration utility to recover old videos**

**Result**: Much higher reliability - videos either save+work or fail gracefully without confusing users

**Next steps**:
1. Run `python3 database_health_check.py` to verify everything works
2. Upload a test video to confirm logs show `✅ Verified record saved`
3. Have users try clicking buttons - should work now! ✅
