# TODO: Bug Fix Agent Improvements

## Phase 1: Operational & Configuration (Foundation)
- [x] **Logging Implementation**: Replace all `print()` calls with the `logging` module. Configure logging to both console and a file (`agent.log`).
- [x] **Configurable Model**: Move the model name string to `.env` (e.g., `GEMINI_MODEL=gemini-2.5-flash`) and update the code to load it.
- [x] **State Persistence**: Implement a simple JSON state file (e.g., `.agent_state.json`) to store `known_issues` or the `last_checked_timestamp` to handle script restarts.
- [x] **Graceful Shutdown**: Add a signal handler for `SIGINT` to allow the agent to finish its current processing loop before exiting.

## Phase 2: Safety & Reliability
- [x] **Backup Mechanism**: Modify `process_issue` to create a `.bak` copy of any file before it is modified.
- [x] **Dry-Run Mode**: Add a command-line argument parser (using `argparse`) to support a `--dry-run` flag that skips the file writing step.
- [x] **Syntax Validation**: Implement a check (e.g., using `ast.parse` for `.py` files) to verify the LLM's output is syntactically correct before saving.
- [x] **Scope Limitation**: Define a "safe directory" list or prefix and ensure the agent only modifies files within those paths.

## Phase 3: Enhanced Jira Integration
- [x] **Start Notification**: Add logic to post a Jira comment ("Agent starting analysis...") and transition the ticket to "In Progress".
- [x] **Completion Feedback**: Post a final comment on the Jira ticket with a summary of changes or the specific diff applied.

## Phase 4: LLM Optimization & Context
- [x] **Refine Prompting**: Update the prompt to ask for specific code blocks or a diff format instead of a full file rewrite to preserve formatting and reduce token usage.
- [x] **Robust File Detection**: Improve `find_files_in_text` to handle absolute vs relative paths and implement a basic fuzzy search if the exact filename isn't found in the root.
- [x] **Codebase Awareness**: Allow the agent to list files in the current directory to provide better context to the LLM if the ticket is vague.
