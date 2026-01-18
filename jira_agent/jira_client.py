import logging
from typing import List, Optional, Dict, Any
from jira import JIRA, Issue
from .config import Config

logger = logging.getLogger(__name__)

class JiraClient:
    """Wrapper for Jira API interactions."""

    def __init__(self, server: str, email: str, token: str):
        try:
            self.client = JIRA(server=server, basic_auth=(email, token))
            logger.info(f"Connected to Jira server: {server}")
        except Exception as e:
            logger.error(f"Failed to connect to Jira: {e}")
            raise

    def search_issues(self, jql: str) -> List[Issue]:
        """Searches for issues using JQL."""
        try:
            return self.client.search_issues(jql)
        except Exception as e:
            logger.error(f"Jira search failed: {e}")
            return []

    def add_comment(self, issue_key: str, comment: str) -> bool:
        """Adds a comment to an issue."""
        try:
            self.client.add_comment(issue_key, comment)
            return True
        except Exception as e:
            logger.error(f"Failed to add comment to {issue_key}: {e}")
            return False

    def transition_issue(self, issue_key: str, target_names: List[str]) -> bool:
        """
        Attempts to transition an issue to one of the target states.
        target_names: list of possible status names (case-insensitive).
        """
        try:
            transitions = self.client.transitions(issue_key)
            target_names_lower = [name.lower() for name in target_names]
            
            for t in transitions:
                if t['name'].lower() in target_names_lower:
                    self.client.transition_issue(issue_key, t['id'])
                    logger.info(f"Transitioned {issue_key} to '{t['name']}'")
                    return True
            
            logger.warning(f"No matching transition found for {issue_key} among: {target_names}")
            return False
        except Exception as e:
            logger.error(f"Failed to transition {issue_key}: {e}")
            return False

    def get_issue(self, issue_key: str) -> Optional[Issue]:
        """Retrieves a single issue by key."""
        try:
            return self.client.issue(issue_key)
        except Exception as e:
            logger.error(f"Failed to fetch issue {issue_key}: {e}")
            return None
