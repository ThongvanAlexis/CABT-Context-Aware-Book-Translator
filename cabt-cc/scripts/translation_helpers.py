"""
Translation helper utilities for CABT translate command.

Provides testable utility functions for:
- Glossary (?) marker stripping before passing to translation agents
- Per-chapter new-terms merging into a single deduplicated file
- Translation style brief generation from metadata and Q&A answers

Usage as module:
    from translation_helpers import strip_uncertain_markers, merge_new_terms, generate_style_brief

Usage as CLI:
    python translation_helpers.py strip-glossary --input glossary.md --output cleaned.md
    python translation_helpers.py merge-terms --terms-dir ./new-terms/ --output new-terms.md
    python translation_helpers.py generate-brief --metadata-path ./metadata.json --qa-json '{"q1":"a1"}' --output brief.md
"""

import argparse
import json
import os
import re
import sys


# ---------------------------------------------------------------------------
# Glossary marker stripping
# ---------------------------------------------------------------------------


def strip_uncertain_markers(content):
    """Strip ' (?)' markers from glossary content.

    Removes the pattern ' (?)' (with leading space) from all occurrences
    in the content string. Does not strip '(?)' without a leading space.

    Args:
        content: Glossary content string.

    Returns:
        Content with all ' (?)' markers removed.
    """
    return content.replace(" (?)", "")


# ---------------------------------------------------------------------------
# New-terms merging
# ---------------------------------------------------------------------------


def _parse_chapter_number(filename):
    """Extract chapter number from a chapter-NN-terms.md filename.

    Args:
        filename: Filename string (e.g., 'chapter-03-terms.md').

    Returns:
        Chapter number string (e.g., '03') or None if pattern doesn't match.
    """
    match = re.match(r"chapter-(\d+)-terms\.md$", filename)
    if match:
        return match.group(1)
    return None


def _parse_terms_table(content):
    """Parse a markdown table with Source | Translation | Context columns.

    Args:
        content: File content string with a markdown table.

    Returns:
        List of dicts with keys 'source', 'translation', 'context'.
        Malformed rows (missing columns) are skipped.
    """
    terms = []
    for line in content.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        # Skip separator rows
        if re.match(r"^\|[\s\-|]+\|$", line):
            continue
        parts = [p.strip() for p in line.split("|")]
        # Split by | produces empty strings at start/end for well-formed rows
        # Filter out empty strings from split
        parts = [p for p in parts if p != ""]
        # Skip header row
        if len(parts) >= 1 and parts[0] == "Source":
            continue
        # Need at least Source, Translation, Context
        if len(parts) < 3:
            continue
        terms.append({
            "source": parts[0],
            "translation": parts[1],
            "context": parts[2],
        })
    return terms


def merge_new_terms(terms_dir):
    """Merge per-chapter new-terms files into a single deduplicated output.

    Reads all chapter-NN-terms.md files from terms_dir. Deduplicates by
    source term (case-sensitive). When the same source term appears in
    multiple chapters, lists all chapter numbers. Output is sorted
    alphabetically by source term.

    Args:
        terms_dir: Path to directory containing chapter-NN-terms.md files.

    Returns:
        Merged markdown string with columns: Source | Translation | Chapters | Status.
        If no terms files found, returns a header-only file with message.
    """
    # Collect all terms files sorted by name
    all_files = sorted(os.listdir(terms_dir))
    terms_files = []
    for fname in all_files:
        chapter_num = _parse_chapter_number(fname)
        if chapter_num is not None:
            terms_files.append((chapter_num, fname))

    if not terms_files:
        lines = [
            "# New Terms",
            "",
            "| Source | Translation | Chapters | Status |",
            "|---|---|---|---|",
            "",
            "No new terms discovered.",
            "",
        ]
        return "\n".join(lines)

    # Aggregate terms: key = source term, value = {translation, chapters set}
    merged = {}
    for chapter_num, fname in terms_files:
        filepath = os.path.join(terms_dir, fname)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        terms = _parse_terms_table(content)
        for term in terms:
            source = term["source"]
            if source in merged:
                merged[source]["chapters"].add(chapter_num)
            else:
                merged[source] = {
                    "translation": term["translation"],
                    "chapters": {chapter_num},
                }

    # Build output sorted alphabetically by source
    lines = [
        "# New Terms",
        "",
        "| Source | Translation | Chapters | Status |",
        "|---|---|---|---|",
    ]
    for source in sorted(merged.keys()):
        entry = merged[source]
        chapters = ", ".join(sorted(entry["chapters"]))
        lines.append(
            f"| {source} | {entry['translation']} | {chapters} | (auto-added, validate) |"
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Genre-specific translation rules
# ---------------------------------------------------------------------------

# Each genre maps to a list of principle strings describing translation
# BEHAVIORS, not specific terms. These principles apply to any language pair.

GENRE_RULES = {
    "LitRPG": [
        "Maintain the fast-paced, punchy rhythm of combat descriptions -- action sequences should feel dynamic and immediate in the target language",
        "Preserve game mechanic formatting (stats, levels, skills) as close to the original structure as possible while adapting terminology naturally",
        "System notifications, status windows, and game UI text should maintain a consistent, distinct voice that feels artificial/mechanical compared to narrative prose",
        "Keep the balance between game-world immersion and literary narrative -- the translation should feel like reading a game-infused novel, not a game manual",
        "Adapt gaming jargon and internet culture references to equivalents familiar to the target audience rather than translating literally",
    ],
    "Fantasy": [
        "Maintain the literary register appropriate to the world -- use elevated or archaic speech patterns where the original employs them, and casual speech where it does not",
        "Preserve world-building terminology consistently -- invented terms, place names, and cultural concepts should be translated or transliterated with a single consistent approach",
        "Formal/archaic speech patterns for nobility, deities, or ancient beings should feel naturally elevated in the target language, not awkwardly literal",
        "Magic system terminology should be internally consistent -- if a term is translated one way, it must remain that way throughout",
        "Poetic or prophetic passages should prioritize rhythm and tone over word-for-word accuracy",
    ],
    "Sci-Fi": [
        "Maintain technical precision for scientific and engineering terminology -- translations should be accurate and consistent with established target-language conventions",
        "Military ranks, organizational hierarchies, and chain-of-command jargon should follow the target language's own military conventions where applicable",
        "Measurement systems (distance, time, temperature) should be adapted to what the target audience expects, unless the original uses fictional units",
        "Technological and scientific neologisms should be translated to feel plausible and natural in the target language",
        "Dialogue between technical characters should maintain the appropriate level of expertise without over-explaining concepts that the characters would take for granted",
    ],
    "General": [
        "Maintain a balanced literary style that prioritizes natural flow in the target language over literal accuracy",
        "Adapt idioms, cultural references, and humor to equivalents that resonate with the target audience",
        "Preserve the author's voice and narrative style -- if the original is sparse, keep it sparse; if flowery, maintain that richness",
        "Dialogue should sound natural and authentic to how speakers of the target language actually communicate",
    ],
}


# ---------------------------------------------------------------------------
# Style brief generation
# ---------------------------------------------------------------------------


def generate_style_brief(genre, source_language, target_language, book_title,
                         book_research, qa_answers):
    """Generate a translation style brief markdown document.

    Creates a genre+language-specific markdown file from metadata and
    Q&A answers. The brief provides consistent translation guidance
    for all parallel translation agents.

    Args:
        genre: Book genre (LitRPG, Fantasy, Sci-Fi, General).
        source_language: Source language name (e.g., 'English').
        target_language: Target language name (e.g., 'French').
        book_title: Title of the book being translated.
        book_research: Research context string, or None if unavailable.
        qa_answers: Dict mapping question strings to answer strings.
            Empty dict means no Q&A was performed.

    Returns:
        Complete style brief as a markdown string.
    """
    sections = []

    # Title
    sections.append(f"# Translation Style Brief -- {book_title}")
    sections.append("")
    sections.append(f"**Source Language:** {source_language}")
    sections.append(f"**Target Language:** {target_language}")
    sections.append(f"**Genre:** {genre}")
    sections.append("")

    # Book Overview
    sections.append("## Book Overview")
    sections.append("")
    if book_research is None:
        sections.append("No research available; rely on the source text for context.")
    elif isinstance(book_research, str):
        sections.append(book_research)
    elif isinstance(book_research, dict):
        for key, value in book_research.items():
            label = key.replace("_", " ").title()
            sections.append(f"**{label}:** {value}")
    else:
        sections.append(str(book_research))
    sections.append("")

    # Translation Philosophy
    sections.append("## Translation Philosophy")
    sections.append("")
    sections.append(
        f"This translation aims to faithfully convey the original {source_language} text "
        f"into natural, idiomatic {target_language}. The goal is to match the tone and soul "
        f"of the original while feeling completely natural to a native {target_language} reader."
    )
    sections.append("")
    sections.append("- Prioritize readability and natural flow over literal word-for-word accuracy")
    sections.append("- Adapt idioms to existing equivalents in the target language when they exist")
    sections.append("- Swear words, humor, and cultural references should be adapted naturally, not translated literally")
    sections.append("- Creative freedom is encouraged when no direct equivalent exists -- the translation should feel alive, not mechanical")
    sections.append("")

    # Genre-Specific Rules
    sections.append("## Genre-Specific Rules")
    sections.append("")
    rules = GENRE_RULES.get(genre, GENRE_RULES["General"])
    for rule in rules:
        sections.append(f"- {rule}")
    sections.append("")

    # Style Q&A Decisions (omitted if empty)
    if qa_answers:
        sections.append("## Style Q&A Decisions")
        sections.append("")
        for question, answer in qa_answers.items():
            sections.append(f"**{question}**")
            sections.append(f"- {answer}")
            sections.append("")

    # Key Guidelines
    sections.append("## Key Guidelines")
    sections.append("")
    sections.append("- Use the glossary for all established terms -- consistency is paramount")
    sections.append("- Flag any new terms not in the glossary in the per-chapter new-terms file")
    sections.append("- Preserve all XHTML formatting and structure exactly as in the source")
    sections.append("- When in doubt between literal accuracy and natural flow, choose natural flow")
    sections.append(f"- Every sentence in the source must have a corresponding translation -- do not omit or summarize")
    sections.append("")

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------


def _cmd_strip_glossary(args):
    """Handle the 'strip-glossary' subcommand."""
    if not os.path.isfile(args.input):
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        content = f.read()

    cleaned = strip_uncertain_markers(content)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(cleaned)


def _cmd_merge_terms(args):
    """Handle the 'merge-terms' subcommand."""
    if not os.path.isdir(args.terms_dir):
        print(f"Error: Terms directory not found: {args.terms_dir}", file=sys.stderr)
        sys.exit(1)

    result = merge_new_terms(args.terms_dir)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(result)


def _cmd_generate_brief(args):
    """Handle the 'generate-brief' subcommand."""
    if not os.path.isfile(args.metadata_path):
        print(f"Error: Metadata file not found: {args.metadata_path}", file=sys.stderr)
        sys.exit(1)

    with open(args.metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    genre = metadata.get("genre", "General")
    source_language = metadata.get("source_language", "English")
    target_language = metadata.get("target_language", "")
    book_title = metadata.get("title", "Untitled")
    book_research = metadata.get("book_research")

    qa_answers = json.loads(args.qa_json) if args.qa_json else {}

    brief = generate_style_brief(
        genre=genre,
        source_language=source_language,
        target_language=target_language,
        book_title=book_title,
        book_research=book_research,
        qa_answers=qa_answers,
    )

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(brief)


def main():
    """CLI entry point with subcommands for translation helpers."""
    parser = argparse.ArgumentParser(
        description="Translation helper utilities for CABT translate."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # strip-glossary subcommand
    strip = subparsers.add_parser(
        "strip-glossary",
        help="Strip (?) markers from glossary content",
    )
    strip.add_argument("--input", required=True, help="Path to glossary input file")
    strip.add_argument("--output", required=True, help="Path to cleaned output file")
    strip.set_defaults(func=_cmd_strip_glossary)

    # merge-terms subcommand
    merge = subparsers.add_parser(
        "merge-terms",
        help="Merge per-chapter new-terms files into one",
    )
    merge.add_argument(
        "--terms-dir", required=True,
        help="Directory containing chapter-NN-terms.md files",
    )
    merge.add_argument("--output", required=True, help="Path to merged output file")
    merge.set_defaults(func=_cmd_merge_terms)

    # generate-brief subcommand
    brief = subparsers.add_parser(
        "generate-brief",
        help="Generate translation style brief from metadata",
    )
    brief.add_argument(
        "--metadata-path", required=True,
        help="Path to metadata.json",
    )
    brief.add_argument(
        "--qa-json", default="{}",
        help="JSON string of question->answer pairs",
    )
    brief.add_argument("--output", required=True, help="Path to style brief output file")
    brief.set_defaults(func=_cmd_generate_brief)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
