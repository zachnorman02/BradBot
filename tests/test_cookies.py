#!/usr/bin/env python3
"""
Test script for YouTube cookie fetching
Run this on the EC2 instance to test cookie authentication
"""

import os
from utils.cookie_helper import fetch_youtube_cookies

def main():
    # Set credentials from environment or prompt
    username = os.getenv('YOUTUBE_USERNAME')
    password = os.getenv('YOUTUBE_PASSWORD')
    
    if not username:
        username = input("Enter YouTube username/email: ").strip()
        os.environ['YOUTUBE_USERNAME'] = username
    
    if not password:
        password = input("Enter YouTube password: ").strip()
        os.environ['YOUTUBE_PASSWORD'] = password
    
    print("Starting YouTube cookie fetch...")
    print(f"Username: {username}")
    print(f"Password: {'*' * len(password) if password else 'Not set'}")
    
    result = fetch_youtube_cookies()
    
    if result:
        print(f"✅ Cookies saved to: {result}")
        print("You can check screenshots in /tmp/ for debugging")
    else:
        print("❌ Failed to fetch cookies")
        print("Check screenshots in /tmp/ for what went wrong")

if __name__ == "__main__":
    main()