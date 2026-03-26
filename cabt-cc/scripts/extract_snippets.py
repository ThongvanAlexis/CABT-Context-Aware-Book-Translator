"""
Extract text snippets from chapter files for LLM classification.

Reads source/ XHTML files, strips HTML tags, returns first 500 chars and
last 200 chars of text content as JSON.

Usage:
    python extract_snippets.py <workspace_path>
"""

import argparse
import json
import os
import re
import sys


def extract_snippets(workspace_path):
    """Extract text snippets from chapter source files in a workspace.

    Reads metadata.json to find chapters, then reads each chapter's source
    file, strips HTML/XML tags, and returns the first 500 characters and
    last 200 characters of text content.

    Args:
        workspace_path: Path to the workspace directory containing
            metadata.json and source/ subdirectory.

    Returns:
        List of dicts with keys: sequence, output_filename, detected_title,
        snippet, snippet_end, detection_notes.

    Raises:
        FileNotFoundError: If metadata.json is not found in workspace_path.
    """
    meta_path = os.path.join(workspace_path, "metadata.json")
    if not os.path.isfile(meta_path):
        raise FileNotFoundError(
            f"metadata.json not found in {workspace_path}"
        )

    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    source_dir = os.path.join(workspace_path, "source")
    results = []

    for chapter in metadata["chapters"]:
        chapter_path = os.path.join(source_dir, chapter["output_filename"])

        if not os.path.isfile(chapter_path):
            results.append({
                "sequence": chapter["sequence"],
                "output_filename": chapter["output_filename"],
                "detected_title": chapter["detected_title"],
                "snippet": "[file not found]",
                "snippet_end": "",
                "detection_notes": chapter.get("detection_notes", ""),
            })
            continue

        # Read file content with encoding fallback
        content = None
        for encoding in ("utf-8", "latin-1"):
            try:
                with open(chapter_path, "r", encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            results.append({
                "sequence": chapter["sequence"],
                "output_filename": chapter["output_filename"],
                "detected_title": chapter["detected_title"],
                "snippet": "[encoding error]",
                "snippet_end": "",
                "detection_notes": chapter.get("detection_notes", ""),
            })
            continue

        # Strip HTML/XML tags and collapse whitespace
        text = re.sub(r'<[^>]+>', ' ', content)
        text = re.sub(r'\s+', ' ', text).strip()

        # Take first 500 characters and last 200 characters
        snippet = text[:500]
        snippet_end = text[-200:] if len(text) > 700 else ""

        results.append({
            "sequence": chapter["sequence"],
            "output_filename": chapter["output_filename"],
            "detected_title": chapter["detected_title"],
            "snippet": snippet,
            "snippet_end": snippet_end,
            "detection_notes": chapter.get("detection_notes", ""),
        })

    return results


def main():
    """CLI entry point for snippet extraction."""
    parser = argparse.ArgumentParser(
        description="Extract text snippets from chapter files for LLM classification."
    )
    parser.add_argument(
        "workspace_path",
        help="Path to the workspace directory"
    )
    args = parser.parse_args()

    try:
        snippets = extract_snippets(args.workspace_path)
        print(json.dumps(snippets, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
