import json
import os
import logging
from datetime import datetime
from typing import Set, Tuple, Optional, List
from .config import STATE_FILE

logger = logging.getLogger(__name__)

def save_state(start_time: datetime, known_issues: Set[str]) -> None:
    """Saves the agent's progress to a JSON file."""
    try:
        state = {
            "start_time": start_time.isoformat(),
            "known_issues": list(known_issues)
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        logger.error(f"Failed to save state: {e}")

def load_state() -> Tuple[Optional[datetime], Set[str]]:
    """Loads the agent's progress from a JSON file."""
    if not os.path.exists(STATE_FILE):
        return None, set()

    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            start_time = datetime.fromisoformat(state["start_time"])
            known_issues = set(state.get("known_issues", []))
            return start_time, known_issues
    except Exception as e:
        logger.error(f"Failed to load state: {e}")
        return None, set()
