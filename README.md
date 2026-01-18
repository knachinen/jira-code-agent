# 🐞 Jira Bug Fix Agent (v0.3)

Welcome! This is an intelligent, automated agent designed to help your team squash bugs faster. It monitors your Jira project for new bug reports, analyzes the relevant code using Google's Gemini LLM, and automatically proposes fixes—all while keeping your codebase safe.

## ✨ Key Features

*   **Automated Monitoring**: Continuously watches Jira for new bug tickets.
*   **Smart Analysis**: Uses Gemini to understand the bug report and your codebase context.
*   **Safe Execution**:
    *   🔒 **Scope Protection**: Only modifies files in your specified safe directory.
    *   💾 **Automatic Backups**: Creates `.bak` files before making any changes.
    *   ✅ **Syntax Validation**: Ensures generated code is valid Python before saving.
    *   🔄 **Loop Protection**: Detects repetitive feedback cycles and enforces a 3-attempt limit for self-correction.
*   **Jira Integration**:
    *   updates ticket status (In Progress -> Done).
    *   posts comments with "In Progress" notifications.
    *   provides a **Unified Diff** of the fix directly in the ticket.
*   **Modular Design**: Clean, maintainable code structure (`jira_agent` package).

## 🛠️ Prerequisites

*   Python 3.10 or higher
*   A Jira account (Email & API Token)
*   A Google Gemini API Key

## ⚙️ Configuration

1.  **Environment Variables**: Create a `.env` file in the root directory with the following credentials:

    ```env
    JIRA_SERVER=https://your-domain.atlassian.net
    JIRA_EMAIL=your-email@example.com
    JIRA_API_TOKEN=your-jira-api-token
    GEMINI_API_KEY=your-gemini-api-key
    GEMINI_MODEL=gemini-2.5-flash
    ```

2.  **Dependencies**: Ensure you have the required Python packages installed:
    ```bash
    pip install jira google-generativeai python-dotenv
    ```

## 🚀 Usage

To start the agent, run the following command:

```bash
python agent_runner.py --safe-dir .
```

### Command Line Arguments

*   `--safe-dir <path>`: **(Required)** The directory where the agent is allowed to modify files. Use `.` for the current directory.
*   `--auto-review`: Enable the iterative **Plan-Execute-Review** cycle. If set, the agent will critique its own work and self-correct (up to 3 times) before finishing. Default: Disabled (One-shot mode).
*   `--dry-run`: Run in "read-only" mode. The agent will analyze and log what it *would* do, but won't modify files or update Jira. Great for testing!
*   `--interval <seconds>`: How often to check Jira (default: 10 seconds).
*   `--verbose`: Enable detailed debug logging.

### Example

Test the agent without making changes:
```bash
python agent_runner.py --safe-dir . --dry-run --verbose
```

Run with self-correction enabled:
```bash
python agent_runner.py --safe-dir . --auto-review
```

## 🔄 How It Works

1.  **Watch**: The agent polls Jira for tickets created after it started.
2.  **Identify**: It parses the ticket description to find relevant filenames.
3.  **Resolve**: It locates these files within your project structure.
4.  **Patch**: It asks Gemini to generate a fix (using efficient search/replace blocks).
5.  **Verify**: It checks the syntax of the new code.
6.  **Apply**: It backs up the original file and writes the fix.
7.  **Report**: It posts a diff of the changes to Jira and marks the ticket as "Done".

## 🛑 Stopping the Agent

To stop the agent gracefully, simply press `Ctrl+C` in your terminal. It will finish its current task, save its state, and exit.

---
*Happy Coding!* 🤖
