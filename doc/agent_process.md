# Agent Process & Architecture

This document describes the internal workflow of the **Jira Bug Fix Agent (v0.3)**. It is designed to be an autonomous developer that can find, analyze, and fix bugs based on Jira tickets.

## 1. Monitoring & Discovery

The agent runs a continuous polling loop (`agent.run`) that checks for Jira issues created after the agent started.

### Ticket Detection
- **Query**: It fetches recent tickets using JQL (`created >= start_time`).
- **Reprocessing**: It maintains a local state (`.agent_state.json`) of processed tickets (`known_issues`).
    - If a ticket is **New** (not in state): It is processed immediately.
    - If a ticket is **Known** but its status is **"To Do" / "Reopened"**: It is removed from the known list and reprocessed. This allows humans to trigger a retry by reopening a ticket and adding comments with further instructions.

## 2. Planning Phase

Once a ticket is picked up, the agent attempts to understand *where* the change needs to happen.

### Context Gathering
The agent combines the following into a single "Instruction" for the LLM:
1. **Summary**: The Jira ticket title.
2. **Description**: The main ticket body.
3. **Comments**: All non-bot comments are appended to provide additional context or updated instructions from users.

### File Identification
It uses a two-step approach to find relevant files:
1.  **Regex Heuristic**: Scans the ticket summary and description for file extensions (`.py`, `.js`, etc.).
2.  **Semantic Discovery (LLM)**: If the codebase structure is available, it sends the file tree and the bug report to the LLM. The LLM infers logically relevant files (e.g., "The user mentioned 'login', so I should check `auth.py`").

### Path Resolution
The agent resolves these filename candidates to actual paths on disk within the configured `--safe-dir`.
- It handles relative paths (`src/utils.py`).
- It handles partial matches (`utils.py` -> `src/core/utils.py`).
- **New Files**: If a file doesn't exist but is within the safe directory, the agent treats it as a "New File" creation request.

## 3. Execution Phase (Iterative Loop)

The agent enters a **Plan-Execute-Review** loop. This loop runs up to 3 times (if `--auto-review` is enabled) to ensure quality.

### Step A: Code Generation
The agent asks the LLM to fix the file.
- **Context**: It provides the *current* content of the file (or empty if new) and the project structure.
- **Prompt Strategy**:
    1.  **Patch Request**: It first asks for a `SEARCH/REPLACE` block. This is token-efficient and precise.
    2.  **Fallback**: If the patch fails (e.g., search block mismatch), it asks for a **Full Rewrite** of the file.
- **Safety**: Before writing to disk, it validates the syntax (e.g., `ast.parse` for Python) to prevent saving broken code.

### Step B: Application
- **Backup**: It creates a `.bak` copy of the original file.
- **Write**: It writes the new content to disk.

### Step C: Self-Correction (Review)
After applying changes, the agent gathers the *new* content of all modified files and sends them back to the LLM with the persona of a **Senior Code Reviewer**.
- **Prompt**: "Does this code satisfy the bug report? Are filenames correct?"
- **Outcome**:
    - **APPROVED**: The loop ends successfully.
    - **CRITIQUE**: The LLM provides feedback (e.g., "You forgot to import `os`"). The agent updates its internal instruction with this critique and loops back to **Step A** to fix its own mistake.
    - **Cycle Detection**: If the LLM repeats the exact same critique twice, the loop is broken to prevent infinite loops.

## 4. Finalization & Reporting

Once the loop completes (either via approval or max retries):

1.  **Diff Generation**: The agent calculates a Unified Diff between the original code and the final fixed code.
2.  **Jira Comment**: It posts a consolidated comment containing:
    - A summary of actions.
    - The diffs for all modified files (formatted in Jira code blocks).
3.  **Transition**: It moves the Jira ticket status to **"Done"** or **"Resolved"**.
4.  **State Save**: The issue ID is saved to `.agent_state.json` so it isn't processed again unless reopened.
