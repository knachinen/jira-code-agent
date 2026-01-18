# TODO: Bug Fix Agent Refactoring (Modularization)

## Phase 1: Package Structure & Configuration
- [x] **Initialize Package**: Create the `jira_agent` directory and `__init__.py`.
- [x] **Modularize Config**: Create `jira_agent/config.py` to handle environment variables, logging setup, and global constants. Add type hints.

## Phase 2: Service Modules (Logic Separation)
- [x] **File Service**: Create `jira_agent/file_utils.py`. Implement path resolution, safety checks, syntax validation, diff generation, and codebase structure listing. Use type hints.
- [x] **LLM Service**: Create `jira_agent/llm_client.py`. Create a `GeminiClient` class to handle prompting (patch vs. rewrite) and the SEARCH/REPLACE logic.
- [x] **Jira Service**: Create `jira_agent/jira_client.py`. Create a `JiraClient` class to wrap searches, comments, and transitions.
- [x] **State Management**: Create `jira_agent/state.py` for saving/loading the JSON state file.

## Phase 3: Core Orchestration
- [x] **Agent Module**: Create `jira_agent/agent.py`. Define a `BugFixAgent` class that uses the above services to watch and process issues. Refactor the main loop and `process_issue` logic.
- [x] **Main Entry Point**: Create `run_agent_v3.py` in the root directory to handle CLI arguments and start the agent.

## Phase 4: Finalization
- [x] **Verify & Cleanup**: Ensure all imports are correct and the modular version works as expected. Add documentation/docstrings to the new classes.