# TeraBox Downloader - Timeout Issue Fix

## Problem
The downloader was experiencing request timeout errors when downloading large files, particularly files over 100MB. The error was:
```
ERROR - [TeraBox API] ❌ Request timeout (30s)
```

## Root Cause
Multiple HTTP timeout configurations were set to only **30 seconds**, which is insufficient for:
- Large file downloads (e.g., 131MB files)
- Slow or unstable network conditions
- Remote API responses that take time to process

## Solutions Implemented

### 1. **Increased API Call Timeouts** (`terabox_api.py`)
- Changed POST request timeout from `total=30` to `total=120` (2 minutes)
- Used proper socket timeout configuration:
  - `sock_connect=30` - Max time to establish connection
  - `sock_read=30` - Max time to read data from socket per chunk
  - `total=120` - Max total time for entire request

**Before:**
```python
timeout=aiohttp.ClientTimeout(total=30)
```

**After:**
```python
timeout=aiohttp.ClientTimeout(total=120, sock_connect=30, sock_read=30)
```

### 2. **Optimized Download Timeout** (`manager.py`)
- Changed from fixed total timeout to unlimited total timeout with socket-level timeout
- This allows large downloads to take as long as needed, but requires data to arrive within 60 seconds
- Socket connect timeout remains 30 seconds

**Before:**
```python
timeout=aiohttp.ClientTimeout(total=settings.download_timeout)
```

**After:**
```python
timeout=aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=60)
```

### 3. **Fixed Stream Worker Timeout** (`manager.py`)
- Increased stream worker POST timeout from `total=30` to `total=120`

### 4. **Added Retry Logic with Exponential Backoff**
Both API calls and downloads now support automatic retries:
- **3 retry attempts** on timeout or error
- **Exponential backoff**: 1s, 2s, 4s between retries
- **Detailed logging** of retry attempts

#### API Retry Logic:
```python
for attempt in range(max_retries):  # max_retries=3
    try:
        # Make API call
    except Exception as e:
        if attempt < max_retries - 1:
            wait_time = 2 ** attempt  # 1s, 2s, 4s
            await asyncio.sleep(wait_time)
            continue
```

#### Download Retry Logic:
- Retries failed downloads automatically
- Logs warning messages with retry information
- Returns success on first successful attempt

## Impact

### ✅ Benefits
1. **Large file support**: Now handles files of any size (limited only by disk/RAM)
2. **Network resilience**: Automatically retries on timeout/error
3. **Better UX**: More informative logging about retry attempts
4. **Proper timeout handling**: Socket timeouts don't accumulate to total timeout

### 📊 Timeout Configuration Summary
| Component | Old Timeout | New Timeout | Improvement |
|-----------|-------------|-------------|------------|
| TeraBox API | 30s (total) | 120s (total) + socket timeouts | 4x longer + proper socket handling |
| Download | Fixed total | Unlimited total + 60s socket | Better for large files |
| Stream Worker | 30s (total) | 120s (total) + socket timeouts | 4x longer |
| Retry Logic | None | 3 attempts with backoff | Much more resilient |

## Testing Recommendations

1. **Test with large files**: Download files >100MB to verify no timeouts
2. **Test with slow connections**: Simulate network delays to verify retry logic
3. **Test with API delays**: Monitor logs for retry attempts and verify they work
4. **Monitor logs**: Check for retry messages to understand retry behavior

## Configuration Notes

All timeout values are configured as follows:
- `sock_connect=30`: Connection establishment must complete within 30 seconds
- `sock_read=30-60`: Data must be received from socket within this interval (per chunk/read)
- `total=120` or `total=None`: Total request time (None = unlimited)

This separation allows:
- Quick failure detection for connection issues (30s)
- Flexible time for actual data transfer (unlimited with per-chunk monitoring)
- Automatic recovery with exponential backoff

## Files Modified
1. `/downloader/terabox_api.py` - API timeout + retry logic
2. `/downloader/manager.py` - Download timeout + download retry logic
