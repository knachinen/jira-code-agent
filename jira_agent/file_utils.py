import os
import shutil
import ast
import difflib
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

def is_safe_path(filename: str, safe_dir: str) -> bool:
    """Checks if the filename is within the designated safe directory."""
    abs_safe_dir = os.path.abspath(safe_dir)
    abs_file_path = os.path.abspath(filename)
    return abs_file_path.startswith(abs_safe_dir)

def resolve_file_path(candidate: str, safe_dir: str) -> Optional[str]:
    """
    Attempts to resolve a filename candidate to an actual file path within safe_dir.
    """
    # 1. Direct check
    if os.path.isfile(candidate) and is_safe_path(candidate, safe_dir):
        return os.path.abspath(candidate)
    
    # 2. Relative to safe_dir
    try:
        joined_path = os.path.join(safe_dir, candidate)
        if os.path.isfile(joined_path):
            return os.path.abspath(joined_path)
    except Exception:
        pass
    
    # 3. Recursive search (fuzzy-ish)
    abs_safe = os.path.abspath(safe_dir)
    candidate_norm = candidate.replace('\\', '/').lstrip('/')
    
    for root, _, filenames in os.walk(abs_safe):
        # Basic filtering to avoid deep scans of irrelevant folders
        if any(ignore in root for ignore in ['.venv', '.git', '__pycache__']):
            continue
            
        for f in filenames:
            full_path = os.path.join(root, f)
            if full_path.replace('\\', '/').endswith(candidate_norm):
                return full_path
                
    return None

def validate_syntax(filename: str, code: str) -> bool:
    """Validates the syntax of the generated code based on its extension."""
    if filename.endswith(".py"):
        try:
            ast.parse(code)
            return True
        except SyntaxError as e:
            logger.error(f"Syntax validation failed for {filename}: {e}")
            return False
    # Extend for other languages if needed
    return True

def generate_diff(filename: str, old_code: str, new_code: str) -> str:
    """Generates a unified diff between old and new code."""
    diff = difflib.unified_diff(
        old_code.splitlines(keepends=True),
        new_code.splitlines(keepends=True),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}"
    )
    return "".join(diff)

def get_codebase_structure(safe_dir: str) -> str:
    """Returns a list of all relevant files in the safe_dir for context."""
    structure: List[str] = []
    abs_safe = os.path.abspath(safe_dir)
    ignore_dirs = {'.venv', '.git', '__pycache__', '.pytest_cache', 'node_modules'}
    ignore_files = {'.agent_state.json', 'agent.log'}
    
    for root, dirs, files in os.walk(abs_safe):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        
        for f in files:
            if f in ignore_files:
                continue
            if f.endswith(('.py', '.js', '.ts', '.html', '.css', '.json', '.md')):
                full_path = os.path.join(root, f)
                relative_path = os.path.relpath(full_path, abs_safe)
                structure.append(relative_path)
                
    return "\n".join(structure)

def backup_file(filename: str) -> Optional[str]:
    """Creates a .bak copy of the file."""
    try:
        backup_path = f"{filename}.bak"
        shutil.copy2(filename, backup_path)
        logger.info(f"Created backup: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to create backup for {filename}: {e}")
        return None

def write_to_file(filename: str, content: str) -> bool:
    """Writes content to a file."""
    try:
        with open(filename, 'w') as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error(f"Failed to write to {filename}: {e}")
        return False

def read_from_file(filename: str) -> Optional[str]:
    """Reads content from a file."""
    try:
        with open(filename, 'r') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to read from {filename}: {e}")
        return None
