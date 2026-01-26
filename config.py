"""
Configuration constants for BradBot
Centralizes magic strings, database settings, and other constants
"""

# Database Configuration
DB_SCHEMA = "main"
DB_CONNECTION_POOL_MIN = 1
DB_CONNECTION_POOL_MAX = 10
DB_CONNECTION_TIMEOUT = 10

# Bot Configuration
BOT_PREFIX = ":"

# Task Check Intervals (in seconds)
BOOSTER_ROLE_CHECK_INTERVAL = 3600  # 1 hour
POLL_AUTO_CLOSE_INTERVAL = 60  # 1 minute
POLL_RESULTS_REFRESH_INTERVAL = 300  # 5 minutes
REMINDER_CHECK_INTERVAL = 60  # 1 minute
TIMER_CHECK_INTERVAL = 1  # 1 second
BIRTHDAY_CHECK_INTERVAL = 3600  # 1 hour
COUNTING_PENALTY_INTERVAL = 60  # 1 minute
SCHEDULED_ROLE_CHECK_INTERVAL = 60  # 1 minute

# Panel Types
PANEL_TYPE_ADMIN_SETTINGS = "admin_settings"
PANEL_TYPE_COMMAND_SETTINGS = "command_settings"
PANEL_TYPE_ISSUE_PANEL = "issue_panel"

# Feature Settings Keys
SETTING_AUTO_KICK_SINGLE_SERVER = "auto_kick_single_server"
SETTING_AUTO_BAN_SINGLE_SERVER = "auto_ban_single_server"

# Default Values
DEFAULT_FALSE = "false"
DEFAULT_TRUE = "true"
