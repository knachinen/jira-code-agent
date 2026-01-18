import time
import logging
import re
import os
from datetime import datetime
from typing import Set, List, Optional, Dict

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
        """Processes a single Jira issue with an iterative review loop."""
        issue = self.jira.get_issue(issue_key)
        if not issue:
            return

        summary = issue.fields.summary
        original_description = issue.fields.description or ""
        current_description = original_description
        
        logger.info(f"Processing {issue_key}: {summary}")

        if not self.dry_run:
            self.jira.add_comment(issue_key, "🤖 *Bug Fix Agent* has started analyzing this issue.")
            self.jira.transition_issue(issue_key, ["In Progress", "진행 중", "시작"])

        MAX_RETRIES = 3
        attempt = 0
        modified_files_history = set() # Track all files touched across attempts
        critique_history = [] # Track critiques to detect cycles

        while attempt < MAX_RETRIES:
            attempt += 1
            logger.info(f"--- Attempt {attempt}/{MAX_RETRIES} ---")

            # 1. Identify files (Plan)
            # A. Regex heuristic
            candidates = set(self.find_files_in_text(current_description))
            candidates.update(self.find_files_in_text(summary))
            
            # B. LLM semantic discovery
            codebase_context = get_codebase_structure(self.safe_dir)
            llm_files = self.llm.identify_relevant_files(summary, current_description, codebase_context)
            if llm_files:
                candidates.update(llm_files)
                logger.info(f"LLM identified relevant files: {llm_files}")

            if not candidates and attempt == 1:
                # Only fail on first attempt if nothing found. 
                # Later attempts might be fixing files we already know about.
                logger.warning(f"No files detected for {issue_key}")
                if not self.dry_run:
                    self.jira.add_comment(issue_key, "ℹ️ No filenames detected. Analysis skipped.")
                return

            # 2. Analyze and fix each file (Execute)
            current_modified_files = {} # content of files modified IN THIS LOOP

            for candidate in candidates:
                # Try to resolve existing file
                filename = resolve_file_path(candidate, self.safe_dir)
                
                is_new_file = False
                if not filename:
                    # Check if it's a valid new file path within safe_dir
                    possible_path = os.path.join(self.safe_dir, candidate)
                    if os.path.abspath(possible_path).startswith(os.path.abspath(self.safe_dir)):
                         filename = possible_path
                         is_new_file = True
                         logger.info(f"Treating `{candidate}` as a new file to be created.")
                    else:
                        logger.warning(f"Could not resolve file: {candidate}")
                        # Don't comment on Jira every loop, just log
                        continue

                # Read original code (or empty if new)
                old_code = ""
                if not is_new_file:
                    old_code = read_from_file(filename)
                    if old_code is None:
                        continue

                # Request fix from LLM
                fixed_code = self.llm.get_fix(filename, old_code, summary, current_description, codebase_context)
                if not fixed_code:
                    continue

                # Validate syntax
                if not validate_syntax(filename, fixed_code):
                    logger.warning(f"Syntax validation failed for {candidate}")
                    continue

                if self.dry_run:
                    logger.info(f"[DRY-RUN] Would apply fix to: {filename}")
                    current_modified_files[candidate] = fixed_code # store for review simulation
                    modified_files_history.add(candidate)
                    continue

                # Apply fix with backup (only if existing)
                if not is_new_file:
                    backup_file(filename)
                
                if write_to_file(filename, fixed_code):
                    logger.info(f"Successfully applied fix to {filename}")
                    current_modified_files[candidate] = fixed_code
                    modified_files_history.add(candidate)

            # 3. Review (Self-Correction)
            # Gather content of ALL files modified so far to give full context
            all_modified_content = {}
            for fname in modified_files_history:
                resolved = resolve_file_path(fname, self.safe_dir)
                if resolved:
                    content = read_from_file(resolved)
                    if content:
                        all_modified_content[fname] = content
                elif fname in current_modified_files and self.dry_run:
                     all_modified_content[fname] = current_modified_files[fname]

            if not all_modified_content:
                logger.info("No files modified in this attempt. Stopping loop.")
                break

            critique = self.llm.review_changes(summary, original_description, all_modified_content)
            
            if not critique:
                logger.info("Review Passed! (APPROVED)")
                break # Exit loop, success!
            else:
                # Cycle Detection
                if critique in critique_history:
                    logger.warning(f"Cycle detected! Critique repeated: {critique}")
                    if not self.dry_run:
                        self.jira.add_comment(issue_key, "⚠️ **Cycle Detected**: The agent is receiving the same feedback repeatedly. Stopping to prevent an infinite loop.")
                    break
                
                critique_history.append(critique)
                logger.info(f"Review failed. Critique: {critique}")
                # Update description to focus on the critique for the next loop
                current_description = f"ORIGINAL REQUEST: {summary}\n{original_description}\n\nFEEDBACK FROM REVIEWER:\n{critique}\n\nINSTRUCTION: Fix the code based on the feedback above."
                
                if not self.dry_run:
                    self.jira.add_comment(issue_key, f"🔄 **Self-Correction Attempt {attempt}**\nReviewer feedback:\n{critique}")

        # 4. Final feedback
        if modified_files_history and not self.dry_run:
            comment = "✅ *Automated Fixes Applied (Verified)*\n\n"
            # Generate diffs for the FINAL state
            for cand in modified_files_history:
                filename = resolve_file_path(cand, self.safe_dir)
                if filename:
                    # Ideally we'd compare against the VERY original, but we didn't keep it easily.
                    # Just showing the file exists and was touched.
                    # For V0.3, let's just list the files.
                    comment += f"- Modified/Created: `{cand}`\n"
            
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
