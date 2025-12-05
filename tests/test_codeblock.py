#!/usr/bin/env python3
"""
Test script for the code block detection function.
Run this locally to test the is_url_in_code_block function without starting the bot.
"""

import sys
import os

# Add the parent directory to Python path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.helpers import is_url_in_code_block


def test_function():
    """Test cases for the is_url_in_code_block function"""
    test_cases = [
        # Test case format: (message_content, url, expected_result, description)
        
        # Single backtick tests
        ("Check out `https://example.com` for more info", "https://example.com", True, "URL in single backticks"),
        ("Visit https://example.com for details", "https://example.com", False, "URL not in code block"),
        ("Use `curl https://api.example.com` to test", "https://api.example.com", True, "URL in inline code"),
        
        # Triple backtick tests
        ("""Here's a code example:
```
curl https://api.example.com/data
echo "done"
```
Visit https://github.com for source""", "https://api.example.com/data", True, "URL in triple backtick block"),
        
        ("""Here's a code example:
```
curl https://api.example.com/data
echo "done"
```
Visit https://github.com for source""", "https://github.com", False, "URL outside triple backtick block"),
        
        # Mixed backticks
        ("""Check `https://docs.com` and also:
```python
import requests
response = requests.get('https://api.example.com')
```
More info at https://help.com""", "https://docs.com", True, "Single backtick URL with triple backticks present"),
        
        ("""Check `https://docs.com` and also:
```python
import requests
response = requests.get('https://api.example.com')
```
More info at https://help.com""", "https://api.example.com", True, "Triple backtick URL with single backticks present"),
        
        ("""Check `https://docs.com` and also:
```python
import requests
response = requests.get('https://api.example.com')
```
More info at https://help.com""", "https://help.com", False, "URL outside any code blocks"),
        
        # Edge cases
        ("No backticks here https://example.com at all", "https://example.com", False, "No backticks"),
        ("`Incomplete backtick https://example.com", "https://example.com", False, "Unclosed single backtick"),
        ("```\nIncomplete triple https://example.com", "https://example.com", False, "Unclosed triple backticks"),
        ("Multiple `code` blocks `https://example.com` here", "https://example.com", True, "URL in second inline code block"),
    ]
    
    print("Testing is_url_in_code_block function...")
    print("=" * 60)
    
    passed = 0
    total = len(test_cases)
    
    for i, (content, url, expected, description) in enumerate(test_cases, 1):
        result = is_url_in_code_block(content, url)
        status = "PASS" if result == expected else "FAIL"
        
        print(f"Test {i:2d}: {status} - {description}")
        if result != expected:
            print(f"         Expected: {expected}, Got: {result}")
            print(f"         Content: {repr(content[:100])}{'...' if len(content) > 100 else ''}")
            print(f"         URL: {url}")
        else:
            passed += 1
        print()
    
    print("=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print(f"❌ {total - passed} tests failed")
    
    return passed == total

def interactive_test():
    """Interactive testing mode"""
    print("\n" + "=" * 60)
    print("Interactive Test Mode")
    print("=" * 60)
    print("Enter a message content and URL to test the function.")
    print("Type 'quit' to exit interactive mode.\n")
    
    while True:
        try:
            content = input("Message content: ").strip()
            if content.lower() == 'quit':
                break
            
            url = input("URL to check: ").strip()
            if url.lower() == 'quit':
                break
            
            result = is_url_in_code_block(content, url)
            print(f"Result: URL {'IS' if result else 'IS NOT'} in a code block\n")
            
        except KeyboardInterrupt:
            print("\nExiting interactive mode...")
            break
        except EOFError:
            break

if __name__ == "__main__":
    # Run automated tests
    all_passed = test_function()
    
    # Offer interactive testing
    if all_passed:
        choice = input("\nWould you like to run interactive tests? (y/n): ").strip().lower()
        if choice in ['y', 'yes']:
            interactive_test()
    else:
        print("\nFix the failing tests before proceeding to interactive mode.")
    
    print("\nDone!")
