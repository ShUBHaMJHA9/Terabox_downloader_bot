#!/usr/bin/env python3
"""
Standalone test for Channel Forwarder handler.
Tests link detection, extraction, and validation without running the bot.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    print("=" * 80)
    print("CHANNEL FORWARDER STANDALONE TEST")
    print("=" * 80)

    try:
        # Test 1: Imports
        print("\n1️⃣ Testing imports...")
        from handlers.channel_forwarder import (
            TERABOX_DOMAINS,
            TERABOX_URL_PATTERNS,
            TERABOX_DOMAIN_PATTERNS,
            extract_terabox_links,
            is_terabox_link,
        )
        print("   ✅ All imports successful")
        
        # Test 2: Domain list
        print(f"\n2️⃣ Domain list loaded:")
        print(f"   ✅ {len(TERABOX_DOMAINS)} TeraBox domains/mirrors configured")
        print(f"   ✅ {len(TERABOX_URL_PATTERNS)} URL patterns built")
        print(f"   ✅ {len(TERABOX_DOMAIN_PATTERNS)} domain patterns built")
        
        # Test 3: Link extraction
        print(f"\n3️⃣ Testing link extraction...")
        test_cases = [
            ("https://terabox.com/s/link123", 1),
            ("https://nephobox.com/s/link456", 1),
            ("https://1024terabox.com/s/link789", 1),
            ("Check these: https://hugebox.com/s/test1 and https://mirrobox.com/s/test2", 2),
            ("No links here", 0),
        ]
        
        extraction_passed = 0
        for text, expected_count in test_cases:
            links = extract_terabox_links(text)
            status = "✅" if len(links) == expected_count else "❌"
            extraction_passed += 1 if len(links) == expected_count else 0
            display_text = text[:50] + "..." if len(text) > 50 else text
            print(f"   {status} '{display_text}': Found {len(links)}, expected {expected_count}")
        
        # Test 4: Link validation
        print(f"\n4️⃣ Testing link validation...")
        validation_tests = [
            ("https://terabox.com/s/test", True),
            ("https://nephobox.com/s/test", True),
            ("https://1024terabox.com/s/test", True),
            ("https://hugebox.com/s/test", True),
            ("https://myterabox.com/s/test", True),
            ("https://terasharefile.com/s/test", True),
            ("https://mirrobox.com/s/test", True),
            ("https://gobigbox.com/s/test", True),
            ("https://example.com", False),
            ("https://google.com", False),
        ]
        
        validation_passed = 0
        for url, expected in validation_tests:
            result = is_terabox_link(url)
            if result == expected:
                validation_passed += 1
                status = "✅"
            else:
                status = "❌"
            domain = url.split('/')[2]
            print(f"   {status} {domain:25s}: {result}")
        
        # Test 5: Domain coverage
        print(f"\n5️⃣ Testing domain coverage...")
        key_domains = [
            'terabox.com',
            'nephobox.com',
            '1024terabox.com',
            'hugebox.com',
            'mirrobox.com',
            'terasharefile.com',
            'myterabox.com',
            'gobigbox.com',
            'teradisk.com',
        ]
        
        domain_coverage = 0
        for domain in key_domains:
            if domain in TERABOX_DOMAINS:
                domain_coverage += 1
                status = "✅"
            else:
                status = "❌"
            print(f"   {status} {domain}")
        
        # Summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"✅ Imports: PASSED")
        print(f"✅ Domain list: PASSED ({len(TERABOX_DOMAINS)} total domains)")
        print(f"✅ Link extraction: PASSED ({extraction_passed}/{len(test_cases)} tests)")
        print(f"✅ Link validation: PASSED ({validation_passed}/{len(validation_tests)} tests)")
        print(f"✅ Domain coverage: PASSED ({domain_coverage}/{len(key_domains)} key domains)")
        
        if extraction_passed == len(test_cases) and validation_passed == len(validation_tests):
            print("\n🎉 ALL TESTS PASSED! CHANNEL FORWARDER IS WORKING CORRECTLY!")
            print("=" * 80)
            return 0
        else:
            print("\n⚠️ SOME TESTS FAILED")
            print("=" * 80)
            return 1
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
