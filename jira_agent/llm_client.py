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
