"""
Workspace reuse for CABT prepare-book command.

Copies glossary, rules, and style brief from a previous workspace
to a new one.  Glossary context references (ch.N -- note) are stripped
so the imported glossary starts clean for the new book.

Usage:
    python reuse_workspace.py --source-workspace <path> --target-workspace <path>

Output (stdout):
    JSON with keys: source_path, had_glossary, had_rules, had_brief

Errors go to stderr with exit code 1.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# Add scripts directory to path for sibling imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from glossary_helpers import strip_context_references
from prepare_workspace import language_to_dirname


def reuse_workspace(source_workspace, target_workspace):
    """Copy reusable files from a previous workspace to a new one.

    Copies glossary.md (with chapter references stripped),
    glossary-rules.md (as-is), and translation-style-brief.md (as-is)
    from the source workspace to the target workspace root.

    Missing source files are silently skipped (had_X = false).

    Also writes a glossary_reuse field to the target workspace's
    metadata.json recording what was imported and from where.

    Args:
        source_workspace: Path to previous workspace (must have metadata.json).
        target_workspace: Path to new workspace (must have metadata.json).

    Returns:
        Dict with keys:
        - source_path: str (absolute path to source workspace)
        - had_glossary: bool
        - had_rules: bool
        - had_brief: bool

    Raises:
        FileNotFoundError: If source or target workspace lacks metadata.json.
    """
    source_workspace = os.path.abspath(source_workspace)
    target_workspace = os.path.abspath(target_workspace)

    # Validate both workspaces have metadata.json
    source_meta_path = os.path.join(source_workspace, "metadata.json")
    if not os.path.isfile(source_meta_path):
        raise FileNotFoundError(
            f"Source workspace missing metadata.json: {source_meta_path}"
        )

    target_meta_path = os.path.join(target_workspace, "metadata.json")
    if not os.path.isfile(target_meta_path):
        raise FileNotFoundError(
            f"Target workspace missing metadata.json: {target_meta_path}"
        )

    # Read source metadata for book info and language directory
    with open(source_meta_path, "r", encoding="utf-8") as f:
        source_meta = json.load(f)

    source_title = source_meta.get("title", "Unknown")
    target_language = source_meta.get("target_language", "")
    lang_dir = language_to_dirname(target_language) if target_language else ""

    # Track what was copied
    had_glossary = False
    had_rules = False
    had_brief = False
    imported_files = []

    # --- glossary.md: read, strip context references, write to target root ---
    glossary_src = os.path.join(source_workspace, "glossary.md")
    if os.path.isfile(glossary_src):
        with open(glossary_src, "r", encoding="utf-8") as f:
            glossary_text = f.read()
        stripped = strip_context_references(glossary_text)
        glossary_dst = os.path.join(target_workspace, "glossary.md")
        with open(glossary_dst, "w", encoding="utf-8") as f:
            f.write(stripped)
        had_glossary = True
        imported_files.append("glossary.md")

    # --- glossary-rules.md: copy as-is to target root ---
    rules_src = os.path.join(source_workspace, "glossary-rules.md")
    if os.path.isfile(rules_src):
        with open(rules_src, "r", encoding="utf-8") as f:
            rules_text = f.read()
        rules_dst = os.path.join(target_workspace, "glossary-rules.md")
        with open(rules_dst, "w", encoding="utf-8") as f:
            f.write(rules_text)
        had_rules = True
        imported_files.append("glossary-rules.md")

    # --- translation-style-brief.md: find in output/{lang}/, copy to target root ---
    brief_src = None
    if lang_dir:
        brief_src = os.path.join(
            source_workspace, "output", lang_dir, "translation-style-brief.md"
        )
    if brief_src and os.path.isfile(brief_src):
        with open(brief_src, "r", encoding="utf-8") as f:
            brief_text = f.read()
        brief_dst = os.path.join(target_workspace, "translation-style-brief.md")
        with open(brief_dst, "w", encoding="utf-8") as f:
            f.write(brief_text)
        had_brief = True
        imported_files.append("translation-style-brief.md")

    # --- Write glossary_reuse field to target metadata.json ---
    with open(target_meta_path, "r", encoding="utf-8") as f:
        target_meta = json.load(f)

    target_meta["glossary_reuse"] = {
        "source_workspace": source_workspace,
        "source_book_title": source_title,
        "imported_files": imported_files,
        "imported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    with open(target_meta_path, "w", encoding="utf-8") as f:
        json.dump(target_meta, f, indent=2, ensure_ascii=False)

    return {
        "source_path": source_workspace,
        "had_glossary": had_glossary,
        "had_rules": had_rules,
        "had_brief": had_brief,
    }


def main():
    """CLI entry point for workspace reuse."""
    parser = argparse.ArgumentParser(
        description="Copy glossary, rules, and style brief from a previous workspace."
    )
    parser.add_argument(
        "--source-workspace",
        required=True,
        help="Path to previous workspace (must contain metadata.json)",
    )
    parser.add_argument(
        "--target-workspace",
        required=True,
        help="Path to new workspace (must contain metadata.json)",
    )

    args = parser.parse_args()

    try:
        result = reuse_workspace(
            source_workspace=args.source_workspace,
            target_workspace=args.target_workspace,
        )
        print(json.dumps(result, indent=2))

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
