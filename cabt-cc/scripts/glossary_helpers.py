"""
Glossary helper utilities for CABT build-glossary command.

Provides testable utility functions for:
- Genre-specific glossary template generation
- Checkpoint/resume logic from metadata.json
- Token capacity pre-flight checks
- Strip chapter-context references from imported glossaries

Usage as module:
    from glossary_helpers import generate_glossary_template, get_resume_chapter, check_token_capacity
    from glossary_helpers import strip_context_references

Usage as CLI:
    python glossary_helpers.py template --title T --genre G --source-language SL --target-language TL
    python glossary_helpers.py resume --metadata-path P
    python glossary_helpers.py preflight --metadata-path P
    python glossary_helpers.py strip-context --input-path ./glossary.md
"""

import argparse
import json
import os
import re
import sys


# ---------------------------------------------------------------------------
# Genre section definitions
# ---------------------------------------------------------------------------

# Each genre maps to an ordered list of (section_name, has_register).
# has_register=True means the table gets a Register column (Characters only);
# has_register=False means the table gets a Context column.

LITRPG_SECTIONS = [
    ("Characters and Creatures", True),
    ("Skills / Spells / Abilities", False),
    ("Classes / Titles / Ranks", False),
    ("Game Mechanics", False),
    ("Notifications and SFX", False),
    ("Locations", False),
    ("Factions / Organizations", False),
    ("Items / Equipment", False),
    ("Currency / Units", False),
    ("Catchphrases / Expressions", False),
    ("World-Specific Terms", False),
]

FANTASY_SECTIONS = [
    ("Characters and Creatures", True),
    ("Magic / Spells / Enchantments", False),
    ("Races / Peoples", False),
    ("Titles / Ranks / Nobility", False),
    ("Locations / Geography", False),
    ("Factions / Kingdoms / Orders", False),
    ("Artifacts / Magical Items", False),
    ("Currency / Units / Calendar", False),
    ("Catchphrases / Expressions", False),
    ("World-Specific Terms", False),
]

SCIFI_SECTIONS = [
    ("Characters and Creatures / Species", True),
    ("Technologies / Systems", False),
    ("Grades / Ranks / Hierarchy", False),
    ("Ships / Stations / Vehicles", False),
    ("Locations / Planets / Sectors", False),
    ("Factions / Corporations / Governments", False),
    ("Weapons / Equipment", False),
    ("Units / Currency / Measures", False),
    ("Catchphrases / Expressions", False),
    ("World-Specific Terms / Jargon", False),
]

GENERAL_SECTIONS = [
    ("Characters and Creatures", True),
    ("Key Terminology", False),
    ("Locations", False),
    ("Organizations", False),
    ("Items / Objects", False),
    ("Catchphrases / Expressions", False),
    ("Other Terms", False),
]

GENRE_MAP = {
    "LitRPG": LITRPG_SECTIONS,
    "Fantasy": FANTASY_SECTIONS,
    "Sci-Fi": SCIFI_SECTIONS,
    "General": GENERAL_SECTIONS,
}

VALID_GENRES = set(GENRE_MAP.keys())


# ---------------------------------------------------------------------------
# Template generation
# ---------------------------------------------------------------------------

def _build_table(source_language, target_language, has_register):
    """Build a markdown table header + separator for a glossary section.

    Args:
        source_language: Source language name for column header.
        target_language: Target language name for column header.
        has_register: If True, include Register column; otherwise Context.

    Returns:
        Multi-line string with the table header and separator.
    """
    if has_register:
        header = f"| {source_language} | {target_language} | Register | Context |"
        separator = "|---|---|---|---|"
    else:
        header = f"| {source_language} | {target_language} | Context |"
        separator = "|---|---|---|"
    return f"{header}\n{separator}\n"


def generate_glossary_template(title, genre, source_language, target_language):
    """Generate a genre-specific glossary markdown template.

    Args:
        title: Book title for the glossary heading.
        genre: One of "LitRPG", "Fantasy", "Sci-Fi", "General".
        source_language: Source language name (e.g., "English").
        target_language: Target language name (e.g., "French").

    Returns:
        Complete glossary markdown template as a string.

    Raises:
        ValueError: If genre is not one of the valid genres.
    """
    if genre not in VALID_GENRES:
        raise ValueError(
            f"Invalid genre '{genre}'. Must be one of: {sorted(VALID_GENRES)}"
        )

    sections = GENRE_MAP[genre]

    lines = []
    lines.append(f"# Glossary -- {title}")
    lines.append("")
    lines.append("## Rules Applied")
    lines.append("")
    lines.append("See ./glossary-rules.md")
    lines.append("")

    for section_name, has_register in sections:
        lines.append(f"## {section_name}")
        lines.append("")
        lines.append(_build_table(source_language, target_language, has_register))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Checkpoint / resume
# ---------------------------------------------------------------------------

def get_resume_chapter(metadata):
    """Determine which chapter to resume glossary building from.

    Args:
        metadata: Parsed metadata.json dict.

    Returns:
        Dict with keys:
        - resume_from: int (next chapter to process) or None if complete
        - total: int (total chapter count)
        - is_resume: bool (True if resuming from a checkpoint)
        - is_complete: bool (True if glossary is already complete)
    """
    total = len(metadata.get("chapters", []))
    progress = metadata.get("glossary_progress")

    if progress is None:
        return {
            "resume_from": 1,
            "total": total,
            "is_resume": False,
        }

    if progress.get("status") == "complete":
        return {
            "resume_from": None,
            "total": total,
            "is_complete": True,
        }

    last_processed = progress.get("last_chapter_processed", 0)

    if last_processed == 0:
        return {
            "resume_from": 1,
            "total": total,
            "is_resume": False,
        }

    return {
        "resume_from": last_processed + 1,
        "total": total,
        "is_resume": True,
    }


# ---------------------------------------------------------------------------
# Token pre-flight
# ---------------------------------------------------------------------------

def check_token_capacity(metadata, max_output_tokens=None):
    """Check chapter token counts and warn about capacity issues.

    Args:
        metadata: Parsed metadata.json dict with chapters[].token_count.
        max_output_tokens: int or None. None means the
            CLAUDE_CODE_MAX_OUTPUT_TOKENS env var is not set.

    Returns:
        Dict with keys:
        - warnings: list of warning strings
        - large_chapters: list of chapter sequence numbers with >20K tokens
        - max_chapter_tokens: int (highest token count across all chapters)
    """
    threshold = 20000
    warnings = []
    large_chapters = []
    max_tokens = 0

    for chapter in metadata.get("chapters", []):
        token_count = chapter.get("token_count", 0)
        if token_count > max_tokens:
            max_tokens = token_count
        if token_count > threshold:
            large_chapters.append(chapter["sequence"])

    if large_chapters and max_output_tokens is None:
        chapter_list = ", ".join(str(c) for c in large_chapters)
        warnings.append(
            f"Chapters [{chapter_list}] exceed {threshold} tokens. "
            f"Set CLAUDE_CODE_MAX_OUTPUT_TOKENS environment variable to ensure "
            f"sufficient output capacity for glossary generation."
        )

    return {
        "warnings": warnings,
        "large_chapters": large_chapters,
        "max_chapter_tokens": max_tokens,
    }


# ---------------------------------------------------------------------------
# Strip context references
# ---------------------------------------------------------------------------

# Matches "ch.N -- " or "ch.N — " where N is 1+ digits, with optional
# trailing whitespace after the dash.  Also matches bare "ch.N" (no dash)
# when the chapter reference stands alone without a following note.
_CH_REF_PATTERN = re.compile(r"ch\.\d+\s*(?:(?:--|—)\s*)?")


def strip_context_references(glossary_text):
    """Remove chapter-context references from a glossary markdown string.

    Strips patterns like ``ch.03 -- note`` from Context columns only,
    preserving all other columns, table structure, and non-table content.

    Args:
        glossary_text: Full glossary.md content as a string.

    Returns:
        The same content with chapter references removed from Context columns.
    """
    lines = glossary_text.split("\n")
    result_lines = []
    context_col_index = None  # which column (0-based) is "Context"

    for line in lines:
        # Detect table header row to find the Context column index
        if line.startswith("|") and "Context" in line:
            cells = line.split("|")
            # cells[0] is empty (before first pipe), cells[-1] is empty (after last pipe)
            for i, cell in enumerate(cells):
                if cell.strip().lower() == "context":
                    context_col_index = i
                    break
            result_lines.append(line)
            continue

        # Detect separator row (|---|---|...) — pass through, keep context_col_index
        if line.startswith("|") and context_col_index is not None:
            stripped = line.replace(" ", "").replace("-", "").replace("|", "")
            if stripped == "":
                # This is a separator row
                result_lines.append(line)
                continue

        # Process data rows when we know the context column
        if (
            line.startswith("|")
            and context_col_index is not None
            and "---" not in line
        ):
            cells = line.split("|")
            if context_col_index < len(cells):
                context_cell = cells[context_col_index]
                # Strip ch.N -- pattern from context cell
                stripped_cell = _CH_REF_PATTERN.sub("", context_cell)
                # Clean up whitespace: strip leading/trailing, normalize internal
                stripped_cell = stripped_cell.strip()
                # Handle semicolons: clean up whitespace around them
                if ";" in stripped_cell:
                    parts = [p.strip() for p in stripped_cell.split(";")]
                    stripped_cell = "; ".join(parts)
                # Pad with spaces for readability in table
                cells[context_col_index] = f" {stripped_cell} " if stripped_cell else "  "
                line = "|".join(cells)
            result_lines.append(line)
            continue

        # Non-table line or table line before we've seen a header: reset context tracking
        if not line.startswith("|"):
            context_col_index = None

        result_lines.append(line)

    return "\n".join(result_lines)


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------

def _cmd_template(args):
    """Handle the 'template' subcommand."""
    template = generate_glossary_template(
        title=args.title,
        genre=args.genre,
        source_language=args.source_language,
        target_language=args.target_language,
    )
    print(template)


def _cmd_resume(args):
    """Handle the 'resume' subcommand."""
    with open(args.metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    result = get_resume_chapter(metadata)
    print(json.dumps(result, indent=2))


def _cmd_strip_context(args):
    """Handle the 'strip-context' subcommand."""
    try:
        with open(args.input_path, "r", encoding="utf-8") as f:
            glossary_text = f.read()
    except FileNotFoundError:
        print(f"Error: file not found: {args.input_path}", file=sys.stderr)
        sys.exit(1)
    result = strip_context_references(glossary_text)
    sys.stdout.buffer.write(result.encode("utf-8"))


def _cmd_preflight(args):
    """Handle the 'preflight' subcommand."""
    with open(args.metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # Check if the env var is set
    env_val = os.environ.get("CLAUDE_CODE_MAX_OUTPUT_TOKENS")
    max_output_tokens = int(env_val) if env_val else None

    result = check_token_capacity(metadata, max_output_tokens=max_output_tokens)
    print(json.dumps(result, indent=2))


def main():
    """CLI entry point with subcommands for glossary helpers."""
    parser = argparse.ArgumentParser(
        description="Glossary helper utilities for CABT build-glossary."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # template subcommand
    tpl = subparsers.add_parser("template", help="Generate a glossary template")
    tpl.add_argument("--title", required=True, help="Book title")
    tpl.add_argument(
        "--genre", required=True,
        choices=sorted(VALID_GENRES),
        help="Book genre",
    )
    tpl.add_argument("--source-language", required=True, help="Source language name")
    tpl.add_argument("--target-language", required=True, help="Target language name")
    tpl.set_defaults(func=_cmd_template)

    # resume subcommand
    res = subparsers.add_parser("resume", help="Check glossary resume state")
    res.add_argument("--metadata-path", required=True, help="Path to metadata.json")
    res.set_defaults(func=_cmd_resume)

    # preflight subcommand
    pre = subparsers.add_parser("preflight", help="Run token capacity pre-flight")
    pre.add_argument("--metadata-path", required=True, help="Path to metadata.json")
    pre.set_defaults(func=_cmd_preflight)

    # strip-context subcommand
    sc = subparsers.add_parser(
        "strip-context",
        help="Strip chapter-context references from a glossary file",
    )
    sc.add_argument(
        "--input-path", required=True,
        help="Path to glossary.md file to strip",
    )
    sc.set_defaults(func=_cmd_strip_context)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
