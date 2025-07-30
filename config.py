"""
Configuration management for Jelly Request application.
Handles environment variables, logging setup, and application settings.
"""

import os
import sys
import logging

# === ENVIRONMENT VARIABLES ===
JELLYSEERR_URL = os.environ.get('JELLYSEERR_URL', 'http://192.168.0.29:5054')
API_KEY = os.environ.get('API_KEY', 'MTY3MzkzMTU4MjI1NzNmZWQ4OGQ1LWQ1NDMtNDY0OC1hYzI3LWQ3ODAyMTM5OWUwNyk=')
IMDB_URL = os.environ.get('IMDB_URL', 'https://www.imdb.com/chart/moviemeter')
MOVIE_LIMIT = int(os.environ.get('MOVIE_LIMIT', 50))
RUN_INTERVAL_DAYS = int(os.environ.get('RUN_INTERVAL_DAYS', 7))
DEBUG_MODE = os.environ.get('DEBUG_MODE', 'SIMPLE').upper()
IS_4K_REQUEST = os.environ.get('IS_4K_REQUEST', 'true').lower() == 'true'
LOG_FILE = "/logs/imdb_jellyseerr.log"

# === LOGGING SETUP ===
def setup_logging():
    """Configure logging for the application."""
    logging_level = logging.DEBUG if DEBUG_MODE == 'VERBOSE' else logging.INFO
    logger = logging.getLogger(__name__)
    logger.setLevel(logging_level)

    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # File handler
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(file_handler)

    # Console handler to duplicate logs to stdout
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(console_handler)

    return logger

# Initialize logger
logger = setup_logging()
