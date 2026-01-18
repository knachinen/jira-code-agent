import argparse
import signal
import sys
import logging
from jira_agent.config import Config, setup_logging
from jira_agent.jira_client import JiraClient
from jira_agent.llm_client import GeminiClient
from jira_agent.agent import BugFixAgent

def main():
    parser = argparse.ArgumentParser(description="Jira Bug Fix Agent v0.3 (Modular)")
    parser.add_argument("--interval", type=int, default=10, help="Jira check interval (seconds)")
    parser.add_argument("--dry-run", action="store_true", help="Monitor and analyze without modifying files")
    parser.add_argument("--safe-dir", type=str, default=".", help="Restrict modifications to this directory")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    # Setup Logging
    logger = setup_logging(verbose=args.verbose)
    
    # Load and Validate Config
    Config.validate()

    # Initialize Services
    try:
        jira_client = JiraClient(Config.JIRA_SERVER, Config.JIRA_EMAIL, Config.JIRA_API_TOKEN)
        llm_client = GeminiClient(Config.GEMINI_API_KEY, Config.GEMINI_MODEL)
    except Exception as e:
        logger.critical(f"Failed to initialize services: {e}")
        sys.exit(1)

    # Initialize Agent
    agent = BugFixAgent(
        jira=jira_client,
        llm=llm_client,
        safe_dir=args.safe_dir,
        dry_run=args.dry_run
    )

    # Signal Handling for Graceful Shutdown
    def handle_interrupt(sig, frame):
        logger.info("Interrupt received. Stopping agent...")
        agent.stop()

    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)

    # Run Agent
    agent.run(interval=args.interval)

if __name__ == "__main__":
    main()
