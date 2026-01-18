import logging
import re
from typing import Optional, Tuple
import google.generativeai as genai
from .config import Config

logger = logging.getLogger(__name__)

class GeminiClient:
    """Client for interacting with the Gemini API for code fixes."""

    def __init__(self, api_key: str, model_name: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        logger.info(f"GeminiClient initialized with model: {model_name}")

    def apply_search_replace(self, original_code: str, patch_text: str) -> Optional[str]:
        """Applies SEARCH/REPLACE blocks to the original code."""
        # Regex to find <<<< SEARCH ... ==== REPLACE ... >>>> blocks
        pattern = re.compile(r'<<<< SEARCH\n(.*?)\n==== REPLACE\n(.*?)\n>>>>', re.DOTALL)
        matches = pattern.findall(patch_text)
        
        if not matches:
            return None

        new_code = original_code
        for search_block, replace_block in matches:
            if search_block in new_code:
                # Use replace(..., 1) to ensure we only replace the specific instance
                new_code = new_code.replace(search_block, replace_block, 1)
            else:
                logger.warning("Search block match failed. Mismatch in original code.")
                return None
                
        return new_code

    def _clean_markdown(self, text: str) -> str:
        """Removes markdown code block wrappers if present."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            return "\n".join(lines)
        return text

    def identify_relevant_files(self, summary: str, description: str, codebase_structure: str) -> list[str]:
        """
        Asks the LLM to identify which files need to be modified or created based on the issue.
        Returns a list of filenames.
        """
        prompt = f"""
You are a senior software architect.

CODEBASE STRUCTURE:
{codebase_structure}

BUG REPORT:
Summary: {summary}
Description: {description}

TASK:
Identify the list of files that need to be modified, created, or read to resolve this issue.
- If the issue implies splitting a file, include both the original file and the new destination file.
- If files are not explicitly named but are logically relevant (e.g., "fix the auth login"), identify the likely file (e.g., `auth.py`).

RETURN FORMAT:
Return ONLY a raw JSON list of strings. Example:
["main.py", "utils.py", "new_module.py"]
Do not use Markdown.
"""
        logger.info("Asking Gemini to identify relevant files...")
        try:
            response = self.model.generate_content(prompt)
            text = self._clean_markdown(response.text)
            # Simple heuristic to extract list
            import json
            files = json.loads(text)
            if isinstance(files, list):
                return files
        except Exception as e:
            logger.error(f"Failed to identify files via LLM: {e}")
        
        return []

    def get_fix(self, filename: str, code_content: str, summary: str, description: str, codebase_context: str = "") -> Optional[str]:
        """
        Attempts to get a fix from Gemini, first via patch, then via full rewrite fallback.
        """
        # 1. Attempt Patch
        patch_prompt = f"""
You are an expert software engineer.

CODEBASE STRUCTURE:
{codebase_context}

FILE BEING FIXED: {filename}
---
{code_content}
---

BUG REPORT:
Summary: {summary}
Description: {description}

INSTRUCTION:
Fix the bug described above.
Return the changes using this STRICT block format:

<<<< SEARCH
[exact lines to be replaced from the original file]
==== REPLACE
[new lines to insert]
>>>>

- You can provide multiple blocks.
- The SEARCH block must match the original file content EXACTLY.
- Do not return the entire file.
- Do not use Markdown backticks.
"""
        logger.info(f"Requesting patch for {filename}...")
        try:
            response = self.model.generate_content(patch_prompt)
            fixed_code = self.apply_search_replace(code_content, self._clean_markdown(response.text))
            if fixed_code:
                return fixed_code
        except Exception as e:
            logger.error(f"Patch request failed: {e}")

        # 2. Fallback to Full Rewrite
        logger.warning(f"Patch failed for {filename}. Falling back to full rewrite...")
        rewrite_prompt = f"""
You are an expert software engineer.

CODEBASE STRUCTURE:
{codebase_context}

FILE BEING FIXED: {filename}
---
{code_content}
---

BUG REPORT:
Summary: {summary}
Description: {description}

INSTRUCTION:
Please rewrite the entire file to fix the bug described above.
Return ONLY the raw code. Do not use Markdown backticks.
"""
        try:
            response = self.model.generate_content(rewrite_prompt)
            return self._clean_markdown(response.text)
        except Exception as e:
            logger.error(f"Full rewrite request failed: {e}")
            return None

    def review_changes(self, summary: str, description: str, modified_files: dict[str, str]) -> Optional[str]:
        """
        Reviews the applied changes.
        Returns None if APPROVED.
        Returns a critique string if changes are needed.
        """
        changes_context = ""
        for fname, content in modified_files.items():
            # Truncate large files for context window if necessary, 
            # but for now assume they fit or are small enough.
            changes_context += f"--- FILE: {fname} ---\n{content}\n\n"

        prompt = f"""
You are a senior code reviewer.

BUG REPORT:
Summary: {summary}
Description: {description}

APPLIED CHANGES:
{changes_context}

TASK:
Review the code above.
1. Does it satisfy the Bug Report requirements?
2. Are filenames correct and consistent (e.g., HTML links to the correct CSS/JS files)?
3. Are there any obvious syntax or logic errors?

RESPONSE FORMAT:
- If the changes are correct and complete, return exactly: APPROVED
- If there are issues, return a concise set of instructions to fix them.
"""
        logger.info("Asking Gemini to review changes...")
        try:
            response = self.model.generate_content(prompt)
            text = self._clean_markdown(response.text).strip()
            
            if "APPROVED" in text:
                return None
            else:
                return text
        except Exception as e:
            logger.error(f"Review request failed: {e}")
            return None # Fail open (assume good if review fails to avoid infinite loops)

