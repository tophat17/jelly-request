"""
Utility functions for Jelly Request application.
Contains common helpers, HTTP session management, and retry logic.
"""

import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def normalize_title(title):
    """Normalize titles by removing special characters, spaces, and numbers."""
    if not title:
        return ""
    # Remove special characters, keep letters and numbers
    title = re.sub(r'[^\w\s]', '', title.lower())
    # Remove extra spaces
    title = ' '.join(title.split())
    return title

def create_session_with_retries():
    """Create a requests session with retry configuration."""
    session = requests.Session()
    retries = Retry(
        total=3, 
        backoff_factor=1, 
        status_forcelist=[429, 500, 502, 503, 504]
    )
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session
