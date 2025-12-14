"""
Cookie handling utilities for BradBot
"""
import os
import json
import tempfile
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time


def get_chrome_driver():
    """Get a Chrome WebDriver instance configured for headless operation."""
    # Set display for GUI mode
    os.environ.setdefault('DISPLAY', ':1')
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Set Chrome binary location
    chrome_options.binary_location = "/usr/bin/google-chrome"
    
    # Anti-detection measures
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")

    # Use webdriver-manager to automatically download correct ChromeDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Execute script to remove webdriver property
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver


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

        driver = get_chrome_driver()

        # Navigate to YouTube
        print("[COOKIES] Navigating to YouTube...")
        driver.get("https://www.youtube.com")

        # Wait for page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Take screenshot for debugging
        driver.save_screenshot("/tmp/youtube_homepage.png")
        print("[COOKIES] Saved screenshot of YouTube homepage")

        # Check if we need to log in
        logged_in = False
        try:
            # Look for sign-in button - if it exists, we're not logged in
            sign_in_button = driver.find_element(By.XPATH, "//a[contains(@href, 'signin')]")
            print("[COOKIES] Sign-in button found - attempting login")

            # Click sign-in button
            sign_in_button.click()
            print("[COOKIES] Clicked sign-in button")
            time.sleep(2)
            driver.save_screenshot("/tmp/signin_clicked.png")

            # Wait for login page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "identifierId"))
            )
            print("[COOKIES] Login page loaded")
            driver.save_screenshot("/tmp/login_page.png")

            # Enter email/username
            email_input = driver.find_element(By.ID, "identifierId")
            email_input.clear()
            email_input.send_keys(username)
            print("[COOKIES] Entered username")
            driver.save_screenshot("/tmp/username_entered.png")

            # Click Next
            next_button = driver.find_element(By.ID, "identifierNext")
            next_button.click()
            print("[COOKIES] Clicked Next after username")
            time.sleep(3)
            driver.save_screenshot("/tmp/next_clicked.png")

            # Wait for password field
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "password"))
            )
            print("[COOKIES] Password field loaded")

            # Enter password
            password_input = driver.find_element(By.NAME, "password")
            password_input.clear()
            password_input.send_keys(password)
            print("[COOKIES] Entered password")

            # Click Next
            next_button = driver.find_element(By.ID, "passwordNext")
            next_button.click()
            print("[COOKIES] Clicked Next after password")

            # Wait for login to complete - look for YouTube homepage or avatar
            try:
                WebDriverWait(driver, 30).until(
                    lambda d: "youtube.com" in d.current_url and not "signin" in d.current_url
                )
                logged_in = True
                print("[COOKIES] Login successful - on YouTube homepage")
            except Exception as e:
                print(f"[COOKIES] Login completion check failed: {e}")
                # Check if we're on a 2FA or verification page
                if "challenge" in driver.current_url or "verify" in driver.current_url:
                    print("[COOKIES] 2FA/Verification required - cannot proceed automatically")
                    return None
                else:
                    print("[COOKIES] Assuming login succeeded despite timeout")                # Navigate back to YouTube if we got redirected
                if "accounts.google.com" in driver.current_url:
                    driver.get("https://www.youtube.com")
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )

            else:
                print("[COOKIES] No credentials provided - will try to get basic cookies without login")

        except Exception as e:
            # No sign-in button found, assume we're already logged in or can get basic cookies
            print(f"[COOKIES] No sign-in button found: {e} - assuming already logged in or can get basic cookies")
            logged_in = True

        # Get cookies
        cookies = driver.get_cookies()
        print(f"[COOKIES] Retrieved {len(cookies)} cookies")

        if not cookies:
            print("[COOKIES] No cookies found")
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
                expiry = str(int(cookie.get('expiry', 0))) if cookie.get('expiry') else '0'

                line = f"{domain}\tTRUE\t{cookie.get('path', '/')}\t{secure}\t{expiry}\t{cookie.get('name')}\t{cookie.get('value')}\n"
                f.write(line)

        print(f"[COOKIES] Saved {len(cookies)} cookies to {cookie_file}")
        return cookie_file

    except Exception as e:
        print(f"[COOKIES] Failed to fetch cookies: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        if driver:
            try:
                driver.quit()
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