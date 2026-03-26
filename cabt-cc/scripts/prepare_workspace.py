"""
Workspace creation for CABT prepare-book command.

Creates a named workspace folder, extracts chapters, runs round-trip
validation, and writes augmented metadata.json.

Usage:
    python prepare_workspace.py <epub_path> --genre <genre> \
        --source-language <lang> --target-language <lang>
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Add scripts directory to path for sibling imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tiktoken

from extract_epub import extract_epub
from rebuild_epub import rebuild_epub, validate_roundtrip


# Valid genre choices
VALID_GENRES = {"LitRPG", "Fantasy", "Sci-Fi", "General"}


def sanitize_title(title):
    """Convert book title to a filesystem-safe folder name.

    Strips special characters (keeping alphanumeric, spaces, hyphens),
    collapses whitespace, replaces spaces with hyphens, strips
    leading/trailing hyphens.

    Args:
        title: Book title string.

    Returns:
        Sanitized string suitable for use as a directory name.

    Raises:
        ValueError: If title is empty or produces an empty result after
            sanitization.

    Examples:
        >>> sanitize_title("Apocalypse: Generic System (The Stitched Worlds Book 1)")
        'Apocalypse-Generic-System-The-Stitched-Worlds-Book-1'
        >>> sanitize_title("L'Apocalypse du Monde")
        'LApocalypse-du-Monde'
    """
    if not title or not title.strip():
        raise ValueError("Title cannot be empty")

    # Remove characters that are not alphanumeric, space, or hyphen
    sanitized = re.sub(r'[^a-zA-Z0-9\s\-]', '', title)
    # Collapse multiple spaces/hyphens into a single space
    sanitized = re.sub(r'[\s\-]+', ' ', sanitized).strip()
    # Replace spaces with hyphens
    sanitized = sanitized.replace(' ', '-')
    # Strip leading/trailing hyphens (edge case after collapsing)
    sanitized = sanitized.strip('-')

    if not sanitized:
        raise ValueError(
            f"Title '{title}' produces an empty folder name after sanitization"
        )

    return sanitized


def language_to_dirname(language):
    """Convert language name to a directory-safe lowercase name.

    Lowercases and replaces spaces with hyphens.

    Args:
        language: Language name (e.g., "French", "Brazilian Portuguese").

    Returns:
        Lowercase, hyphenated string (e.g., "french", "brazilian-portuguese").
    """
    return language.lower().replace(' ', '-')


def prepare_workspace(epub_path, genre, source_language, target_language,
                      base_dir="."):
    """Create a translation workspace from an EPUB file.

    Extracts chapters, runs round-trip validation, and writes augmented
    metadata.json. The workspace directory is named with a timestamp prefix
    followed by the sanitized EPUB title (e.g., 20260324_1902_Book-Title).

    Args:
        epub_path: Path to the EPUB file.
        genre: Book genre -- one of "LitRPG", "Fantasy", "Sci-Fi", "General".
        source_language: Source language name (e.g., "English").
        target_language: Target language name (e.g., "French").
        base_dir: Parent directory for the workspace (default: current dir).

    Returns:
        Tuple of (metadata_dict, workspace_name) where metadata_dict is
        the augmented metadata and workspace_name is the timestamped
        folder name.

    Raises:
        ValueError: If genre is invalid or title is empty.
        FileExistsError: If workspace directory already exists.
        FileNotFoundError: If EPUB file doesn't exist.
        RuntimeError: If round-trip validation fails.
    """
    # Validate genre before any filesystem operations
    if genre not in VALID_GENRES:
        raise ValueError(
            f"Invalid genre '{genre}'. Must be one of: {sorted(VALID_GENRES)}"
        )

    # Validate EPUB file exists
    if not os.path.isfile(epub_path):
        raise FileNotFoundError(f"EPUB file not found: {epub_path}")

    # Step 1: Extract chapters to get metadata (specifically the title)
    # We need the title to create the workspace directory name, but
    # extract_epub needs the workspace directory to write to.
    # Solution: do a lightweight EPUB read to get the title first.
    import ebooklib
    from ebooklib import epub as epub_reader
    book = epub_reader.read_epub(str(epub_path))
    title_meta = book.get_metadata("DC", "title")
    title = title_meta[0][0] if title_meta else "Unknown"

    # Step 2: Create workspace directory with timestamp prefix
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    workspace_name = f"{timestamp}_{sanitize_title(title)}"
    workspace_dir = os.path.join(base_dir, workspace_name)

    # Re-run protection: error if workspace already exists
    if os.path.exists(workspace_dir):
        raise FileExistsError(
            f"Workspace already exists: {workspace_dir}. "
            "Delete it first or use a different location."
        )

    os.makedirs(workspace_dir)

    # Step 3: Extract chapters into workspace
    metadata = extract_epub(epub_path, workspace_dir)

    # Step 4: Augment metadata with Phase 2 fields
    # Override source_language with user-provided value (NOT EPUB metadata)
    metadata["source_language"] = source_language
    metadata["target_language"] = target_language
    metadata["genre"] = genre
    metadata["status"] = "prepared"

    # Determine translation_mode from detection_notes
    has_spine_fallback = any(
        "spine_fallback" in (ch.get("detection_notes", "") or "")
        for ch in metadata["chapters"]
    )
    metadata["translation_mode"] = "files_from_spine" if has_spine_fallback else "chapters_from_toc"

    # Step 5: Create output/[language]/ directory
    lang_dirname = language_to_dirname(target_language)
    output_lang_dir = os.path.join(workspace_dir, "output", lang_dirname)
    os.makedirs(output_lang_dir)

    # Step 6: Write augmented metadata.json
    meta_path = os.path.join(workspace_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # Step 7: Run round-trip validation
    source_dir = os.path.join(workspace_dir, "source")
    roundtrip_path = os.path.join(workspace_dir, "test-roundtrip.epub")

    rebuild_epub(
        original_epub_path=str(epub_path),
        chapter_dir=source_dir,
        output_epub_path=roundtrip_path,
        metadata=metadata,
    )

    validation = validate_roundtrip(str(epub_path), roundtrip_path)
    if not validation["passed"]:
        raise RuntimeError(
            f"Round-trip validation failed: {validation['errors']}"
        )

    # Step 8: Count tokens per chapter (rough estimate via tiktoken p50k_base)
    enc = tiktoken.get_encoding("p50k_base")
    total_tokens = 0
    for chapter in metadata["chapters"]:
        chapter_path = os.path.join(source_dir, chapter["output_filename"])
        with open(chapter_path, "r", encoding="utf-8") as f:
            content = f.read()
        token_count = len(enc.encode(content))
        chapter["token_count"] = token_count
        total_tokens += token_count
    metadata["total_tokens"] = total_tokens

    # Re-write metadata.json with token counts
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return metadata, workspace_name


def main():
    """CLI entry point for workspace creation."""
    parser = argparse.ArgumentParser(
        description="Create a translation workspace from an EPUB file."
    )
    parser.add_argument("epub_path", help="Path to the EPUB file")
    parser.add_argument(
        "--genre",
        required=True,
        choices=sorted(VALID_GENRES),
        help="Book genre",
    )
    parser.add_argument(
        "--source-language",
        required=True,
        help="Source language (e.g., English)",
    )
    parser.add_argument(
        "--target-language",
        required=True,
        help="Target language (e.g., French)",
    )
    parser.add_argument(
        "--base-dir",
        default=".",
        help="Parent directory for the workspace (default: current dir)",
    )

    args = parser.parse_args()

    try:
        metadata, ws_name = prepare_workspace(
            epub_path=args.epub_path,
            genre=args.genre,
            source_language=args.source_language,
            target_language=args.target_language,
            base_dir=args.base_dir,
        )

        # Print JSON summary to stdout
        summary = {
            "workspace_path": os.path.join(args.base_dir, ws_name),
            "title": metadata["title"],
            "chapter_count": len(metadata["chapters"]),
            "total_tokens": metadata["total_tokens"],
        }
        print(json.dumps(summary, indent=2))

    except (ValueError, FileExistsError, FileNotFoundError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
