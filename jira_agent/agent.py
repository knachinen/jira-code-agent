import time
import logging
import re
from datetime import datetime
from typing import Set, List, Optional

from .config import Config
from .file_utils import (
    resolve_file_path, validate_syntax, generate_diff, 
    get_codebase_structure, backup_file, write_to_file, read_from_file
)
from .jira_client import JiraClient
from .llm_client import GeminiClient
from .state import load_state, save_state

logger = logging.getLogger(__name__)

class BugFixAgent:
    """The core agent that monitors Jira and applies fixes."""

    def __init__(
        self, 
        jira: JiraClient, 
        llm: GeminiClient, 
        safe_dir: str = ".", 
        dry_run: bool = False
    ):
        self.jira = jira
        self.llm = llm
        self.safe_dir = safe_dir
        self.dry_run = dry_run
        self.running = True
        
        # Load persisted state
        self.start_time, self.known_issues = load_state()
        if not self.start_time:
            self.start_time = datetime.now()
            
        logger.info(f"Agent initialized. Safe directory: {self.safe_dir}")
        if self.dry_run:
            logger.info("DRY-RUN mode enabled.")

    def stop(self) -> None:
        """Signals the agent to stop after the current loop."""
        self.running = False

    def find_files_in_text(self, text: str) -> List[str]:
        """Extracts filenames from a block of text."""
        matches = re.findall(r'\b[\w\-\/]+\.(?:py|js|ts|html|css|json)\b', text)
        return list(set(matches))

    def process_issue(self, issue_key: str) -> None:
        """Processes a single Jira issue."""
        issue = self.jira.get_issue(issue_key)
        if not issue:
            return

        summary = issue.fields.summary
        description = issue.fields.description or ""
        logger.info(f"Processing {issue_key}: {summary}")

        if not self.dry_run:
            self.jira.add_comment(issue_key, "🤖 *Bug Fix Agent* has started analyzing this issue.")
            self.jira.transition_issue(issue_key, ["In Progress", "진행 중", "시작"])

        # 1. Identify files
        candidates = self.find_files_in_text(description)
        if not candidates:
            candidates = self.find_files_in_text(summary)

        if not candidates:
            logger.warning(f"No files detected for {issue_key}")
            if not self.dry_run:
                self.jira.add_comment(issue_key, "ℹ️ No filenames detected. Analysis skipped.")
            return

        # 2. Analyze and fix each file
        modified_files = []
        codebase_context = get_codebase_structure(self.safe_dir)

        for candidate in candidates:
            filename = resolve_file_path(candidate, self.safe_dir)
            if not filename:
                logger.warning(f"Could not resolve file: {candidate}")
                if not self.dry_run:
                    self.jira.add_comment(issue_key, f"⚠️ Could not locate `{candidate}` in safe directory.")
                continue

            # Read original code
            old_code = read_from_file(filename)
            if old_code is None:
                continue

            # Request fix from LLM
            fixed_code = self.llm.get_fix(filename, old_code, summary, description, codebase_context)
            if not fixed_code:
                continue

            # Validate syntax
            if not validate_syntax(filename, fixed_code):
                if not self.dry_run:
                    self.jira.add_comment(issue_key, f"❌ Failed to fix `{candidate}`: Syntax error in generated code.")
                continue

            if self.dry_run:
                logger.info(f"[DRY-RUN] Would apply fix to: {filename}")
                continue

            # Apply fix with backup
            if backup_file(filename):
                if write_to_file(filename, fixed_code):
                    diff = generate_diff(candidate, old_code, fixed_code)
                    modified_files.append((candidate, diff))
                    logger.info(f"Successfully applied fix to {filename}")

        # 3. Final feedback
        if modified_files:
            if not self.dry_run:
                comment = "✅ *Automated Fixes Applied*\n\n"
                for cand, diff in modified_files:
                    comment += f"Fixed `{cand}`. Diff:\n{{code:diff}}\n{diff}\n{{code}}\n\n"
                self.jira.add_comment(issue_key, comment)
                self.jira.transition_issue(issue_key, ["Done", "Resolved", "완료", "해결됨"])
        elif not self.dry_run:
            self.jira.add_comment(issue_key, "ℹ️ No modifications were applied after analysis.")

    def run(self, interval: int = 10) -> None:
        """Main monitoring loop."""
        logger.info(f"Monitoring Jira for bugs created after {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        while self.running:
            try:
                jql_time = self.start_time.strftime('%Y-%m-%d %H:%M')
                jql = f'created >= "{jql_time}" ORDER BY created DESC'
                issues = self.jira.search_issues(jql)

                # Process in reverse order (oldest first)
                for issue in reversed(issues):
                    if not self.running:
                        break
                    if issue.key not in self.known_issues:
                        self.known_issues.add(issue.key)
                        self.process_issue(issue.key)
                
                save_state(self.start_time, self.known_issues)

                if self.running:
                    time.sleep(interval)

            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                if self.running:
                    time.sleep(interval)
        
        logger.info("Agent shutdown sequence complete.")
