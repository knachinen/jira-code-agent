import logging
import re
import json
import time
from typing import Optional, List
from openai import OpenAI
from .config import Config

logger = logging.getLogger(__name__)

class LLMClient:
    """Client for interacting with OpenRouter API (OpenAI-compatible)."""

    def __init__(self, api_key: str, model_name: str, timeout: float = 60.0):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=timeout
        )
        self.model_name = model_name
        logger.info(f"LLMClient initialized with OpenRouter model: {model_name} (Timeout: {timeout}s)")

    def apply_search_replace(self, original_code: str, patch_text: str) -> Optional[str]:
        """Applies SEARCH/REPLACE blocks to the original code."""
        pattern = re.compile(r'<<<< SEARCH\n(.*?)\n==== REPLACE\n(.*?)\n>>>>', re.DOTALL)
        matches = pattern.findall(patch_text)
        
        if not matches:
            return None

        new_code = original_code
        for search_block, replace_block in matches:
            if search_block in new_code:
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

    def identify_relevant_files(self, summary: str, description: str, codebase_structure: str) -> List[str]:
        """
        Asks the LLM to identify which files need to be modified or created.
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
- If files are not explicitly named but are logically relevant, identify the likely file.

RETURN FORMAT:
Return ONLY a raw JSON list of strings. Example:
["main.py", "utils.py", "new_module.py"]
Do not use Markdown.
"""
        logger.info("Asking LLM to identify relevant files...")
        start_time = time.time()
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            elapsed = time.time() - start_time
            logger.info(f"File identification took {elapsed:.2f}s")
            text = self._clean_markdown(response.choices[0].message.content)
            files = json.loads(text)
            if isinstance(files, list):
                return files
        except Exception as e:
            logger.error(f"Failed to identify files via LLM: {e}")
        
        return []

    def get_fix(self, filename: str, code_content: str, summary: str, description: str, codebase_context: str = "") -> Optional[str]:
        """
        Attempts to get a fix from the LLM, first via patch, then via full rewrite fallback.
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
        start_time = time.time()
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": patch_prompt}]
            )
            elapsed = time.time() - start_time
            logger.info(f"Patch request took {elapsed:.2f}s")
            fixed_code = self.apply_search_replace(code_content, self._clean_markdown(response.choices[0].message.content))
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
        start_time = time.time()
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": rewrite_prompt}]
            )
            elapsed = time.time() - start_time
            logger.info(f"Full rewrite took {elapsed:.2f}s")
            return self._clean_markdown(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Full rewrite request failed: {e}")
            return None

    def review_changes(self, summary: str, description: str, modified_files: dict[str, str]) -> Optional[str]:
        """
        Reviews the applied changes.
        """
        changes_context = ""
        for fname, content in modified_files.items():
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
2. Are filenames correct and consistent?
3. Are there any obvious syntax or logic errors?

RESPONSE FORMAT:
- If the changes are correct and complete, return exactly: APPROVED
- If there are issues, return a concise set of instructions to fix them.
"""
        logger.info("Asking LLM to review changes...")
        start_time = time.time()
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            elapsed = time.time() - start_time
            logger.info(f"Review took {elapsed:.2f}s")
            text = self._clean_markdown(response.choices[0].message.content).strip()
            
            if "APPROVED" in text:
                return None
            else:
                return text
        except Exception as e:
            logger.error(f"Review request failed: {e}")
            return None