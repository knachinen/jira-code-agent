import os
import sys
import logging
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
STATE_FILE = ".agent_state.json"
DEFAULT_MODEL = "gemini-2.5-flash"

class Config:
    """Application configuration and credentials."""
    
    JIRA_SERVER: str = os.getenv("JIRA_SERVER", "")
    JIRA_EMAIL: str = os.getenv("JIRA_EMAIL", "")
    JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)

    @classmethod
    def validate(cls) -> None:
        """Validates that all required environment variables are set."""
        missing = []
        if not cls.JIRA_SERVER: missing.append("JIRA_SERVER")
        if not cls.JIRA_EMAIL: missing.append("JIRA_EMAIL")
        if not cls.JIRA_API_TOKEN: missing.append("JIRA_API_TOKEN")
        if not cls.GEMINI_API_KEY: missing.append("GEMINI_API_KEY")
        
        if missing:
            logging.error(f"Missing environment variables: {', '.join(missing)}")
            sys.exit(1)

def setup_logging(log_file: str = "agent.log", verbose: bool = False) -> logging.Logger:
    """Configures and returns the root logger."""
    
    logging.basicConfig(
        level=logging.INFO if not verbose else logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    # Reduce noise from third-party libs
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
    
    return logging.getLogger("jira_agent")
