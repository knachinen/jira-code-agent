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
        """Applies SEARCH/REPLACE blocks with whitespace-tolerant matching."""
        pattern = re.compile(r'<<<< SEARCH\n(.*?)\n==== REPLACE\n(.*?)\n>>>>', re.DOTALL)
        matches = pattern.findall(patch_text)
        
        if not matches:
            logger.warning("No SEARCH/REPLACE blocks found.")
            return None

        new_code = original_code
        
        for i, (search_block, replace_block) in enumerate(matches):
            if search_block in new_code:
                new_code = new_code.replace(search_block, replace_block, 1)
                continue
            
            # Fuzzy Strategy: Match lines stripping whitespace
            search_lines = [l.strip() for l in search_block.splitlines() if l.strip()]
            if not search_lines:
                continue # Skip empty blocks

            original_lines = new_code.splitlines(keepends=True)
            
            # Find where the sequence of search_lines appears in original_lines
            match_index = -1
            for idx in range(len(original_lines)):
                # Check if search sequence starts here
                if idx + len(search_lines) > len(original_lines):
                    break
                
                # Compare snippet
                snippet = original_lines[idx : idx + len(search_lines)]
                # Normalize snippet for comparison
                snippet_stripped = [l.strip() for l in snippet if l.strip()]
                
                if snippet_stripped == search_lines:
                    match_index = idx
                    break
            
            if match_index != -1:
                # We found the block! Now replace it.
                logger.info(f"Block {i+1}: Fuzzy match success at line {match_index}.")
                
                # Construct the pre-match and post-match parts
                pre_match = "".join(original_lines[:match_index])
                # The actual raw text that matched (preserving its original indentation)
                # Note: We assumed the 'search_lines' covered contiguous lines in original.
                # If 'snippet_stripped' matched, we replace the RAW lines from original_lines.
                
                # Careful: We need to know exactly how many raw lines were consumed.
                # The 'snippet' variable above contains the raw lines including whitespace.
                matched_raw_chunk = "".join(original_lines[idx : idx + len(search_lines)])
                
                post_match = "".join(original_lines[idx + len(search_lines):])
                
                new_code = pre_match + replace_block + "\n" + post_match
            else:
                logger.warning(f"Block {i+1}: Patch failed. Could not find search block even with fuzzy match.")
                # Log snippet for debugging
                logger.debug(f"Search Block Snippet: {search_lines[:3]}...")
                return None # Fail to safe full-rewrite

        return new_code

    def _clean_markdown(self, text: str) -> str:
        """
        Extracts code from markdown blocks more robustly.
        Finds the first block between ``` and ```.
        """
        # Regex to find content between triple backticks
        pattern = re.compile(r'```(?:\w+)?\n(.*?)\n```', re.DOTALL)
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
        
        # Fallback: if no backticks found, return text as is (might be raw code)
        return text.strip()

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

    def generate_plan(self, summary: str, description: str, codebase_structure: str, relevant_files: List[str]) -> str:
        """
        Generates a concise step-by-step plan for the fix.
        """
        prompt = f"""
You are a technical lead.

BUG REPORT:
Summary: {summary}
Description: {description}

TARGET FILES:
{json.dumps(relevant_files)}

CODEBASE CONTEXT:
{codebase_structure}

TASK:
Create a concise, step-by-step plan to resolve this issue.
Focus on WHAT needs to be done in each file.
Do not include code snippets, just logical steps.

RETURN FORMAT:
Return a simple markdown list (bullets).
"""
        logger.info("Asking LLM to generate plan...")
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            return self._clean_markdown(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Failed to generate plan: {e}")
            return "Could not generate detailed plan."

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