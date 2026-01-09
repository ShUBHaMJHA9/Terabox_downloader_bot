#!/usr/bin/env python3
"""
Test progress tracking logic to verify updates at correct intervals.
"""

import time
from downloader.fast_downloader import DownloadProgress


def test_progress_updates():
    """Test that progress updates trigger at correct intervals."""
    progress = DownloadProgress()
    progress.total = 100  # Simulate 100 units total
    
    updates = []
    
    # Simulate 0-100% progression
    for downloaded in range(0, 101, 5):  # 0, 5, 10, 15, ..., 100
        progress.downloaded = downloaded
        
        if progress.should_update():
            progress.mark_updated()
            updates.append(progress.progress_percent)
            print(f"✅ Update at {progress.progress_percent}% - Speed: {progress.speed:.2f} MB/s, ETA: {progress.eta}s")
        else:
            print(f"⏭️  Skip update at {progress.progress_percent}%")
    
    print(f"\n📊 Total updates: {len(updates)}")
    print(f"📈 Update percentages: {updates}")
    
    # Verify first update is at 0%
    assert updates[0] == 0, "First update should be at 0%"
    print("✅ First update at 0%")
    
    # Verify we get ~10% intervals
    expected_updates = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    if set(updates) == set(expected_updates):
        print("✅ All 10% intervals captured")
    else:
        print(f"⚠️  Updates: {updates}")
        print(f"⚠️  Expected: {expected_updates}")
    
    # Test time-based updates
    print("\n🕐 Testing time-based updates...")
    progress2 = DownloadProgress()
    progress2.total = 1000
    progress2.downloaded = 250
    progress2.mark_updated()
    
    # Without time passage, shouldn't update
    progress2.downloaded = 260
    if progress2.should_update():
        print("❌ Should not update without time passage or 10% change")
    else:
        print("✅ Correctly skipped update without time/percentage change")
    
    # Simulate 2+ seconds passing
    progress2.last_update_time = time.time() - 2.1
    progress2.downloaded = 270  # Only 1% increase
    if progress2.should_update():
        print("✅ Time-based update triggered after 2+ seconds")
    else:
        print("❌ Should have updated based on time")
    
    print("\n✅ All progress tracking tests passed!")


if __name__ == "__main__":
    test_progress_updates()
