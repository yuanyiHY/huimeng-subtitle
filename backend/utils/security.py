"""Security utilities: path validation, filename sanitization."""
from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Optional


# Maximum filename length in UTF-8 bytes (conservative limit for most filesystems)
MAX_FILENAME_BYTES = 200


def is_safe_filename(name: str) -> bool:
    """
    Check if a filename is safe (no path traversal, no special chars).
    
    Allows:
    - Unicode letters for all languages (CJK, Latin, etc.)
    - Unicode digits
    - Safe punctuation: space, dash, underscore, parentheses (ASCII and fullwidth)
    
    Rejects:
    - Path separators (/ \\)
    - Parent directory (..)
    - Control characters
    - Leading/trailing dots or spaces
    - NUL bytes
    - Names that are too long
    - Reserved Windows names
    """
    if not name or not name.strip():
        return False
    
    # Reject path separators and parent directory
    if '/' in name or '\\' in name or '..' in name:
        return False
    
    # Reject NUL bytes
    if '\x00' in name:
        return False
    
    # Reject control characters (0x00-0x1F, 0x7F-0x9F)
    if any(ord(c) < 0x20 or (0x7F <= ord(c) < 0xA0) for c in name):
        return False
    
    # Reject leading/trailing dots or spaces
    if name.startswith('.') or name.startswith(' '):
        return False
    if name.endswith('.') or name.endswith(' '):
        return False
    
    # Reject reserved Windows names
    base = name.split('.')[0].upper()
    if base in ('CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
                'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2',
                'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'):
        return False
    
    # Check length
    if len(name.encode('utf-8')) > MAX_FILENAME_BYTES:
        return False
    
    # Check that all characters are safe Unicode categories
    for char in name:
        cat = unicodedata.category(char)
        # Allow:
        # - Letters (L*)
        # - Numbers (N*)
        # - Punctuation connectors (Pc: underscore, etc.)
        # - Dash punctuation (Pd)
        # - Space separator (Zs)
        # - Parentheses and brackets (Ps, Pe)
        # - Other punctuation that's commonly safe (Po: dot, etc.)
        if not (cat.startswith('L') or  # Letters
                cat.startswith('N') or  # Numbers
                cat in ('Pc', 'Pd', 'Zs', 'Ps', 'Pe') or  # Safe punctuation
                char in '.（）()'):  # Explicitly allow dots and parens
            return False
    
    return True


def sanitize_filename(name: str, strip_extension: bool = False) -> str:
    """
    Sanitize a filename by removing/replacing unsafe characters.
    
    Args:
        name: The filename to sanitize
        strip_extension: If True, remove .wav/.json extensions
    
    Returns:
        A safe filename
    
    Raises:
        ValueError: If the result is empty or invalid
    """
    if not name:
        raise ValueError("文件名不能为空")
    
    # Strip common audio/metadata extensions if requested
    if strip_extension:
        for ext in ('.wav', '.WAV', '.json', '.JSON'):
            if name.endswith(ext):
                name = name[:-len(ext)]
                break
    
    # Normalize to NFC form (canonical composition)
    name = unicodedata.normalize('NFC', name)
    
    # Remove control characters
    name = ''.join(c for c in name if ord(c) >= 0x20 and not (0x7F <= ord(c) < 0xA0))
    
    # Replace path separators and parent directory markers
    name = name.replace('/', '_').replace('\\', '_').replace('..', '_')
    
    # Replace NUL bytes
    name = name.replace('\x00', '')
    
    # Keep only safe Unicode characters
    result = []
    for char in name:
        cat = unicodedata.category(char)
        if (cat.startswith('L') or cat.startswith('N') or
            cat in ('Pc', 'Pd', 'Zs', 'Ps', 'Pe') or
            char in '.（）()'):
            result.append(char)
    
    name = ''.join(result)
    
    # Strip leading/trailing spaces and dots
    name = name.strip(' .')
    
    if not name:
        raise ValueError("文件名无有效字符")
    
    # Truncate if too long
    while len(name.encode('utf-8')) > MAX_FILENAME_BYTES:
        name = name[:-1]
        if not name:
            raise ValueError("文件名过长")
    
    return name


def validate_path_in_directory(path: Path, base_dir: Path) -> Path:
    """
    Validate that a resolved path is within the base directory.
    
    Args:
        path: The path to validate (can be relative or absolute)
        base_dir: The base directory that should contain the path
    
    Returns:
        The resolved absolute path
    
    Raises:
        ValueError: If the path escapes the base directory
    """
    try:
        resolved_path = path.resolve()
        resolved_base = base_dir.resolve()
        
        # Check if the path is relative to the base directory
        if not resolved_path.is_relative_to(resolved_base):
            raise ValueError(f"路径不在允许的目录范围内")
        
        return resolved_path
    except (RuntimeError, OSError) as e:
        raise ValueError(f"路径无效: {e}")


def safe_path_join(base_dir: Path, filename: str) -> Path:
    """
    Safely join a base directory with a filename after validation.
    
    Args:
        base_dir: The base directory
        filename: The filename (will be validated)
    
    Returns:
        The validated absolute path
    
    Raises:
        ValueError: If the filename is unsafe or the result escapes base_dir
    """
    if not is_safe_filename(filename):
        raise ValueError(f"文件名包含非法字符: {filename}")
    
    candidate = base_dir / filename
    return validate_path_in_directory(candidate, base_dir)
