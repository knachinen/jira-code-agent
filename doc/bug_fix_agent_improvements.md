# Improvements for `bug_fix_agent.py`

## 1. Safety and Robustness
- **Backup Mechanism**: Before overwriting any file, create a backup (e.g., `filename.bak` or into a `.backup/` directory). This ensures code isn't lost if the LLM generates malformed output.
- **Syntax/Lint Validation**: After generating the code, run a syntax check (e.g., `ast.parse()` for Python or a linter) before writing it to disk to prevent saving broken code.
- **Dry-Run Mode**: Implement a flag (e.g., `--dry-run`) to print the proposed changes or save them to a temporary file without modifying the actual codebase.

## 2. LLM Interaction and Code Generation
- **Refined Prompting**: Instead of asking for a full file rewrite (which is token-expensive and prone to stripping comments/formatting), ask the LLM to generate a `diff` or specific `sed`/`replace` instructions.
- **Context Awareness**: The current regex (`find_files_in_text`) is brittle.
    - Implement a fuzzy search to locate files if the path in the Jira ticket is relative or slightly incorrect.
    - Allow the agent to search the codebase structure if no file is explicitly mentioned.
- **Model Configuration**: Move the model name (`gemini-2.5-flash`) to the `.env` file to allow easy switching without code changes.

## 3. Jira Integration
- **Feedback Loop**: Post a comment back to the Jira ticket indicating that the agent is working on it, and subsequently post the result (success/failure) or the diff of the applied fix.
- **Ticket Status**: Automatically transition the ticket status (e.g., to "In Progress" when starting and "Code Review" or "Done" after applying the fix).
- **Error Reporting**: If the file is not found or the LLM fails, comment on the Jira ticket so the human reporter knows manual intervention is needed.

## 4. Operational Improvements
- **Logging**: Replace `print` statements with the Python `logging` module. This allows for better timestamping, log levels (INFO, ERROR), and file logging (e.g., to `agent.log`).
- **State Persistence**: The `known_issues` set is in-memory. If the script crashes, it resets. Consider saving the "last processed issue creation time" or IDs to a local file (e.g., `.agent_state.json`) to resume correctly after a restart.
- **Graceful Shutdown**: Handle `SIGINT` (Ctrl+C) to finish the current task before exiting.

## 5. Security
- **Input Sanitization**: Be cautious when blindly writing LLM output to files, especially if the Jira ticket content could be malicious prompt injection (though less of a risk in internal setups, still good practice).
- **Scope Limitation**: Restrict the agent's write access to specific directories to prevent it from modifying configuration files or files outside the source tree.
