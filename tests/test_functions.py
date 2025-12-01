#!/usr/bin/env python3
"""
Local testing script for BradBot functions
Run this to test individual functions without connecting to Discord
"""

import sys
import os

# Add the current directory to Python path so we can import from main.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the functions we want to test
from main import is_url_in_code_block, fix_amp_links

def test_code_block_detection():
    """Test the code block URL detection function"""
    print("🧪 Testing code block detection...")
    
    # Test cases
    test_cases = [
        {
            "name": "URL in triple backticks",
            "content": "Check this out:\n```\nhttps://example.com/api\n```\nEnd",
            "url": "https://example.com/api",
            "expected": True
        },
        {
            "name": "URL in single backticks",
            "content": "Check out `https://example.com` for more info",
            "url": "https://example.com",
            "expected": True
        },
        {
            "name": "URL in normal text",
            "content": "Check out https://example.com for more info",
            "url": "https://example.com",
            "expected": False
        },
        {
            "name": "URL before code block",
            "content": "https://example.com and then ```code here```",
            "url": "https://example.com",
            "expected": False
        },
        {
            "name": "Mixed - URL in code, URL outside",
            "content": "Normal https://normal.com and `https://code.com` in code",
            "url": "https://code.com",
            "expected": True
        },
        {
            "name": "Multiple backticks",
            "content": "First `code` then `https://example.com` then more",
            "url": "https://example.com", 
            "expected": True
        }
    ]
    
    passed = 0
    failed = 0
    
    for test in test_cases:
        result = is_url_in_code_block(test["content"], test["url"])
        if result == test["expected"]:
            print(f"✅ {test['name']}: PASSED")
            passed += 1
        else:
            print(f"❌ {test['name']}: FAILED (expected {test['expected']}, got {result})")
            print(f"   Content: {repr(test['content'])}")
            print(f"   URL: {test['url']}")
            failed += 1
    
    print(f"\n📊 Results: {passed} passed, {failed} failed")
    return failed == 0

async def test_amp_links():
    """Test the AMP link fixing function"""
    print("\n🧪 Testing AMP link fixes...")
    
    test_cases = [
        {
            "name": "Google AMP link",
            "input": "https://www.google.com/amp/s/example.com/article",
            "should_change": True
        },
        {
            "name": "Normal link", 
            "input": "https://example.com/article",
            "should_change": False
        },
        {
            "name": "Multiple links",
            "input": "Check https://normal.com and https://www.google.com/amp/s/amp-site.com",
            "should_change": True
        }
    ]
    
    passed = 0
    failed = 0
    
    for test in test_cases:
        result = await fix_amp_links(test["input"])
        changed = result != test["input"]
        
        if changed == test["should_change"]:
            print(f"✅ {test['name']}: PASSED")
            if changed:
                print(f"   Input:  {test['input']}")
                print(f"   Output: {result}")
            passed += 1
        else:
            print(f"❌ {test['name']}: FAILED")
            print(f"   Input: {test['input']}")
            print(f"   Output: {result}")
            print(f"   Expected change: {test['should_change']}, got change: {changed}")
            failed += 1
    
    print(f"\n📊 Results: {passed} passed, {failed} failed")
    return failed == 0

def test_manual_input():
    """Interactive testing - enter your own content to test"""
    print("\n🎮 Interactive Testing")
    print("Enter message content to test code block detection (or 'quit' to exit):")
    
    while True:
        content = input("\nMessage content: ")
        if content.lower() in ['quit', 'exit', 'q']:
            break
            
        url = input("URL to check: ")
        if url.lower() in ['quit', 'exit', 'q']:
            break
            
        result = is_url_in_code_block(content, url)
        print(f"Result: URL {'IS' if result else 'IS NOT'} in a code block")
        print(f"Content preview: {repr(content[:100])}")

async def main():
    """Run all tests"""
    print("🚀 BradBot Local Function Testing")
    print("=" * 50)
    
    # Test code block detection
    test1_passed = test_code_block_detection()
    
    # Test AMP link fixing
    test2_passed = await test_amp_links()
    
    # Overall result
    print("\n" + "=" * 50)
    if test1_passed and test2_passed:
        print("🎉 All tests PASSED!")
    else:
        print("⚠️  Some tests FAILED - check output above")
    
    # Interactive testing
    print("\nWant to test with custom input? (y/n): ", end="")
    if input().lower().startswith('y'):
        test_manual_input()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
