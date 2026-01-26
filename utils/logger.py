"""
Logging configuration for BradBot
Provides consistent logging across the application
"""
import logging
import sys
from typing import Optional

# Create logger
logger = logging.getLogger('bradbot')
logger.setLevel(logging.INFO)

# Create console handler with formatting
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_handler.setFormatter(formatter)

# Add handler to logger
logger.addHandler(console_handler)

def setup_logging(level: Optional[int] = None):
    """
    Setup logging configuration
    
    Args:
        level: Optional logging level (e.g., logging.DEBUG, logging.INFO)
    """
    if level:
        logger.setLevel(level)
        console_handler.setLevel(level)
