"""
Header display module for Jelly Request application.
Shows container start time and app revision information.
"""

import os
import subprocess
from datetime import datetime

def get_git_revision():
    """Get the current git revision/commit hash."""
    try:
        # Try to get the git commit hash
        result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    # Fallback: try to read from environment variable if set during build
    env_revision = os.environ.get('GIT_REVISION', 'unknown')
    if env_revision != 'unknown':
        return env_revision
    
    # Final fallback: try to get from image build time
    return 'latest-build'

def get_branch_name():
    """Get the current git branch name."""
    try:
        # Try to get the git branch name
        result = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    # Fallback: try to read from environment variable if set during build
    env_branch = os.environ.get('GIT_BRANCH', 'unknown')
    if env_branch != 'unknown':
        return env_branch
    
    # Final fallback: determine from repository tag
    return 'main'
    return os.environ.get('GIT_BRANCH', 'unknown')

def display_header():
    """Display the application header with start time and revision info."""
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    revision = get_git_revision()
    branch = get_branch_name()
    
    header = f"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                              JELLY REQUEST                                   ║
║                        IMDb to Jellyseerr Sync Tool                          ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║ Container Started: {start_time:<50} ║
║ App Revision:      {revision:<50} ║
║ Branch:            {branch:<50} ║
║ Repository:        tophat17/jelly-request                                    ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""
    
    print(header)

if __name__ == "__main__":
    display_header()
