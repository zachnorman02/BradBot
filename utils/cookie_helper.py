"""
Cookie handling utilities for BradBot
"""
import os
import json
import tempfile
from playwright.sync_api import sync_playwright
import time


def get_browser():
    """Get a Playwright browser instance configured for headless operation."""
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-plugins",
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",
        ]
    )
    return browser, playwright


def fetch_youtube_cookies():
    """
    Fetch YouTube cookies by logging in automatically if credentials are provided.
    Uses YOUTUBE_USERNAME and YOUTUBE_PASSWORD environment variables.
    Returns path to cookie file, or None if failed.
    """
    driver = None
    cookie_file = None

    try:
        print("[COOKIES] Starting YouTube cookie fetch...")

        # Get credentials from environment
        username = os.getenv('YOUTUBE_USERNAME')
        password = os.getenv('YOUTUBE_PASSWORD')

        print(f"[COOKIES] Username provided: {bool(username)}")
        print(f"[COOKIES] Password provided: {bool(password)}")

        if not username or not password:
            print("[COOKIES] No credentials provided - skipping login")
            return None

        browser, playwright = get_browser()
        context = browser.new_context()
        page = context.new_page()

        # Navigate to YouTube
        print("[COOKIES] Navigating to YouTube...")
        page.goto("https://www.youtube.com")

        # Wait for page to load
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Take screenshot for debugging
        page.screenshot(path="/tmp/youtube_homepage.png")
        print("[COOKIES] Saved screenshot of YouTube homepage")

        # Check if we need to log in
        logged_in = False
        try:
            # Look for sign-in button - if it exists, we're not logged in
            sign_in_locator = page.locator("a[href*='signin']")
            if sign_in_locator.count() > 0:
                print("[COOKIES] Sign-in button found - attempting login")

                # Click sign-in button
                sign_in_locator.click()
                print("[COOKIES] Clicked sign-in button")
                page.wait_for_load_state("networkidle")
                time.sleep(2)
                page.screenshot(path="/tmp/signin_clicked.png")

                # Wait for login page to load
                page.wait_for_url("**/accounts.google.com/**", timeout=10000)
                print("[COOKIES] Login page loaded")
                page.screenshot(path="/tmp/login_page.png")

                # Enter email/username
                email_input = page.locator("#identifierId")
                email_input.fill(username)
                print("[COOKIES] Entered username")
                page.screenshot(path="/tmp/username_entered.png")

                # Click Next
                next_button = page.locator("#identifierNext")
                next_button.click()
                print("[COOKIES] Clicked Next after username")
                time.sleep(3)
                page.screenshot(path="/tmp/next_clicked.png")

                # Wait for password field
                page.wait_for_selector("input[name='password']", timeout=10000)
                print("[COOKIES] Password field loaded")

                # Enter password
                password_input = page.locator("input[name='password']")
                password_input.fill(password)
                print("[COOKIES] Entered password")

                # Click Next
                next_button = page.locator("#passwordNext")
                next_button.click()
                print("[COOKIES] Clicked Next after password")

                # Wait for login to complete
                try:
                    page.wait_for_url("https://www.youtube.com/**", timeout=30000)
                    logged_in = True
                    print("[COOKIES] Login successful - on YouTube homepage")
                except Exception as e:
                    print(f"[COOKIES] Login completion check failed: {e}")
                    # Check if we're on a 2FA or verification page
                    if "challenge" in page.url or "verify" in page.url:
                        print("[COOKIES] 2FA/Verification required - cannot proceed automatically")
                        browser.close()
                        playwright.stop()
                        return None
                    else:
                        print("[COOKIES] Assuming login succeeded despite timeout")
                        logged_in = True
                        # Navigate back to YouTube if we got redirected
                        if "accounts.google.com" in page.url:
                            page.goto("https://www.youtube.com")
                            page.wait_for_load_state("networkidle")

            else:
                print("[COOKIES] No credentials provided - will try to get basic cookies without login")

        except Exception as e:
            # No sign-in button found, assume we're already logged in or can get basic cookies
            print(f"[COOKIES] No sign-in button found: {e} - assuming already logged in or can get basic cookies")
            logged_in = True

        # Get cookies
        cookies = context.cookies()
        print(f"[COOKIES] Retrieved {len(cookies)} cookies")

        if not cookies:
            print("[COOKIES] No cookies found")
            browser.close()
            playwright.stop()
            return None

        # Save cookies to temporary file
        cookie_file = tempfile.mktemp(suffix='.txt')
        with open(cookie_file, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# Generated by BradBot\n")
            for cookie in cookies:
                # Convert to Netscape format for yt-dlp
                domain = cookie.get('domain', '')
                if not domain.startswith('.'):
                    domain = '.' + domain

                secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                http_only = 'TRUE' if cookie.get('httpOnly', False) else 'FALSE'
                expiry = str(int(cookie.get('expires', 0))) if cookie.get('expires') else '0'

                line = f"{domain}\tTRUE\t{cookie.get('path', '/')}\t{secure}\t{expiry}\t{cookie.get('name')}\t{cookie.get('value')}\n"
                f.write(line)

        print(f"[COOKIES] Saved {len(cookies)} cookies to {cookie_file}")
        browser.close()
        playwright.stop()
        return cookie_file

    except Exception as e:
        print(f"[COOKIES] Failed to fetch cookies: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        if 'browser' in locals():
            try:
                browser.close()
                playwright.stop()
            except:
                pass


def validate_cookies_file(cookie_file_path):
    """Check if cookie file exists and is readable."""
    if not cookie_file_path or not os.path.exists(cookie_file_path):
        return False

    try:
        with open(cookie_file_path, 'r') as f:
            content = f.read()
            return len(content.strip()) > 0
    except:
        return False