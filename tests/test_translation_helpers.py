"""Tests for translation_helpers.py: glossary stripping, new-terms merging, style brief generation."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# strip_uncertain_markers tests
# ---------------------------------------------------------------------------


class TestStripUncertainMarkers:
    """Tests for strip_uncertain_markers function."""

    def test_strips_single_marker(self):
        from translation_helpers import strip_uncertain_markers

        inp = "| Sword of Light | Epee de Lumiere | (?)"
        out = strip_uncertain_markers(inp)
        assert out == "| Sword of Light | Epee de Lumiere |"

    def test_strips_multiple_markers_same_line(self):
        from translation_helpers import strip_uncertain_markers

        inp = "| Term1 | Trans1 | (?) | Term2 | Trans2 | (?)"
        out = strip_uncertain_markers(inp)
        assert "(?)" not in out
        assert out == "| Term1 | Trans1 | | Term2 | Trans2 |"

    def test_strips_markers_across_multiple_lines(self):
        from translation_helpers import strip_uncertain_markers

        inp = "| T1 | Tr1 | (?)\n| T2 | Tr2 |\n| T3 | Tr3 | (?)"
        out = strip_uncertain_markers(inp)
        assert "(?)" not in out
        assert "| T2 | Tr2 |" in out

    def test_no_markers_returns_unchanged(self):
        from translation_helpers import strip_uncertain_markers

        inp = "| Term | Translation | Context |"
        out = strip_uncertain_markers(inp)
        assert out == inp

    def test_empty_string(self):
        from translation_helpers import strip_uncertain_markers

        assert strip_uncertain_markers("") == ""

    def test_does_not_strip_without_leading_space(self):
        from translation_helpers import strip_uncertain_markers

        # "(?" and "(?)" without leading space should NOT be stripped
        inp = "some text(?) and more(?)"
        out = strip_uncertain_markers(inp)
        assert out == inp

    def test_only_strips_space_question_mark_pattern(self):
        from translation_helpers import strip_uncertain_markers

        # " (?)" with leading space is stripped; "(?" alone is not
        inp = "text (?) more(? stuff"
        out = strip_uncertain_markers(inp)
        assert out == "text more(? stuff"


# ---------------------------------------------------------------------------
# merge_new_terms tests
# ---------------------------------------------------------------------------


class TestMergeNewTerms:
    """Tests for merge_new_terms function."""

    def test_merges_single_chapter_file(self, tmp_path):
        from translation_helpers import merge_new_terms

        terms_dir = tmp_path / "terms"
        terms_dir.mkdir()

        content = (
            "| Source | Translation | Context |\n"
            "|---|---|---|\n"
            "| Dragon | Drache | A creature |\n"
            "| Elf | Elfe | A race |\n"
        )
        (terms_dir / "chapter-01-terms.md").write_text(content, encoding="utf-8")

        result = merge_new_terms(str(terms_dir))
        assert "Dragon" in result
        assert "Elf" in result
        assert "01" in result  # chapter reference
        assert "(auto-added, validate)" in result

    def test_deduplicates_across_chapters(self, tmp_path):
        from translation_helpers import merge_new_terms

        terms_dir = tmp_path / "terms"
        terms_dir.mkdir()

        ch1 = (
            "| Source | Translation | Context |\n"
            "|---|---|---|\n"
            "| Dragon | Drache | Ch1 context |\n"
        )
        ch2 = (
            "| Source | Translation | Context |\n"
            "|---|---|---|\n"
            "| Dragon | Drache | Ch2 context |\n"
            "| Sword | Schwert | Ch2 weapon |\n"
        )
        (terms_dir / "chapter-01-terms.md").write_text(ch1, encoding="utf-8")
        (terms_dir / "chapter-02-terms.md").write_text(ch2, encoding="utf-8")

        result = merge_new_terms(str(terms_dir))
        # Dragon should appear once with both chapter references
        lines = [l for l in result.split("\n") if "Dragon" in l]
        assert len(lines) == 1
        assert "01" in lines[0]
        assert "02" in lines[0]

    def test_sorts_alphabetically(self, tmp_path):
        from translation_helpers import merge_new_terms

        terms_dir = tmp_path / "terms"
        terms_dir.mkdir()

        content = (
            "| Source | Translation | Context |\n"
            "|---|---|---|\n"
            "| Zebra | Zebra | Animal |\n"
            "| Apple | Pomme | Fruit |\n"
            "| Mango | Mangue | Fruit |\n"
        )
        (terms_dir / "chapter-01-terms.md").write_text(content, encoding="utf-8")

        result = merge_new_terms(str(terms_dir))
        lines = [l for l in result.split("\n") if l.startswith("|") and "---" not in l and "Source" not in l]
        # Extract first column (source term)
        terms = [l.split("|")[1].strip() for l in lines if l.strip()]
        assert terms == sorted(terms)

    def test_empty_directory(self, tmp_path):
        from translation_helpers import merge_new_terms

        terms_dir = tmp_path / "terms"
        terms_dir.mkdir()

        result = merge_new_terms(str(terms_dir))
        assert "No new terms discovered" in result

    def test_ignores_non_matching_files(self, tmp_path):
        from translation_helpers import merge_new_terms

        terms_dir = tmp_path / "terms"
        terms_dir.mkdir()

        (terms_dir / "notes.md").write_text("Some notes", encoding="utf-8")
        (terms_dir / "glossary.md").write_text("Glossary stuff", encoding="utf-8")

        result = merge_new_terms(str(terms_dir))
        assert "No new terms discovered" in result

    def test_skips_malformed_rows(self, tmp_path):
        from translation_helpers import merge_new_terms

        terms_dir = tmp_path / "terms"
        terms_dir.mkdir()

        content = (
            "| Source | Translation | Context |\n"
            "|---|---|---|\n"
            "| Good | Bon | Valid row |\n"
            "| Missing column\n"
            "| Also Good | Aussi Bon | Another valid |\n"
        )
        (terms_dir / "chapter-01-terms.md").write_text(content, encoding="utf-8")

        result = merge_new_terms(str(terms_dir))
        assert "Good" in result
        assert "Also Good" in result
        # Malformed row should be skipped
        assert "Missing column" not in result

    def test_case_sensitive_dedup(self, tmp_path):
        from translation_helpers import merge_new_terms

        terms_dir = tmp_path / "terms"
        terms_dir.mkdir()

        content = (
            "| Source | Translation | Context |\n"
            "|---|---|---|\n"
            "| dragon | drache | lowercase |\n"
            "| Dragon | Drache | uppercase |\n"
        )
        (terms_dir / "chapter-01-terms.md").write_text(content, encoding="utf-8")

        result = merge_new_terms(str(terms_dir))
        lines = [l for l in result.split("\n") if "ragon" in l.lower()]
        # Both should be present (case-sensitive)
        assert len(lines) == 2

    def test_output_has_correct_columns(self, tmp_path):
        from translation_helpers import merge_new_terms

        terms_dir = tmp_path / "terms"
        terms_dir.mkdir()

        content = (
            "| Source | Translation | Context |\n"
            "|---|---|---|\n"
            "| Term | Trans | Ctx |\n"
        )
        (terms_dir / "chapter-01-terms.md").write_text(content, encoding="utf-8")

        result = merge_new_terms(str(terms_dir))
        # Should have Source | Translation | Chapters | Status columns
        assert "Source" in result
        assert "Translation" in result
        assert "Chapters" in result
        assert "Status" in result


# ---------------------------------------------------------------------------
# generate_style_brief tests
# ---------------------------------------------------------------------------


class TestGenerateStyleBrief:
    """Tests for generate_style_brief function."""

    def test_basic_generation(self):
        from translation_helpers import generate_style_brief

        result = generate_style_brief(
            genre="LitRPG",
            source_language="English",
            target_language="French",
            book_title="Test Book",
            book_research="This is a LitRPG book about a hero.",
            qa_answers={"How literal?": "Keep it natural."},
        )
        assert "# Translation Style Brief" in result or "Translation" in result
        assert "Test Book" in result
        assert "LitRPG" in result or "combat" in result.lower()

    def test_contains_required_sections(self):
        from translation_helpers import generate_style_brief

        result = generate_style_brief(
            genre="Fantasy",
            source_language="English",
            target_language="German",
            book_title="Fantasy Epic",
            book_research="A fantasy novel.",
            qa_answers={"Tone?": "Formal"},
        )
        assert "Book Overview" in result
        assert "Translation Philosophy" in result
        assert "Genre-Specific Rules" in result or "Genre" in result
        assert "Key Guidelines" in result

    def test_no_research_message(self):
        from translation_helpers import generate_style_brief

        result = generate_style_brief(
            genre="General",
            source_language="English",
            target_language="Spanish",
            book_title="Some Book",
            book_research=None,
            qa_answers={},
        )
        assert "No research available" in result

    def test_dict_book_research(self):
        from translation_helpers import generate_style_brief

        result = generate_style_brief(
            genre="General",
            source_language="English",
            target_language="Spanish",
            book_title="Some Book",
            book_research={"summary": "A great adventure", "themes": "courage and friendship"},
            qa_answers={},
        )
        assert "**Summary:** A great adventure" in result
        assert "**Themes:** courage and friendship" in result

    def test_empty_qa_omits_section(self):
        from translation_helpers import generate_style_brief

        result = generate_style_brief(
            genre="Sci-Fi",
            source_language="English",
            target_language="Japanese",
            book_title="Space Opera",
            book_research="Sci-fi novel in space.",
            qa_answers={},
        )
        assert "Style Q&A" not in result

    def test_qa_answers_included(self):
        from translation_helpers import generate_style_brief

        qa = {
            "How formal should the language be?": "Use informal register.",
            "How to handle humor?": "Adapt to local culture.",
        }
        result = generate_style_brief(
            genre="LitRPG",
            source_language="English",
            target_language="French",
            book_title="Funny Book",
            book_research="Comedy LitRPG",
            qa_answers=qa,
        )
        assert "How formal should the language be?" in result
        assert "Use informal register." in result
        assert "How to handle humor?" in result

    def test_litrpg_genre_rules(self):
        from translation_helpers import generate_style_brief

        result = generate_style_brief(
            genre="LitRPG",
            source_language="English",
            target_language="French",
            book_title="LitRPG Book",
            book_research="A LitRPG.",
            qa_answers={},
        )
        lower = result.lower()
        assert "combat" in lower or "game" in lower or "notification" in lower

    def test_fantasy_genre_rules(self):
        from translation_helpers import generate_style_brief

        result = generate_style_brief(
            genre="Fantasy",
            source_language="English",
            target_language="French",
            book_title="Fantasy Book",
            book_research="A fantasy novel.",
            qa_answers={},
        )
        lower = result.lower()
        assert "literary" in lower or "world-building" in lower or "formal" in lower or "archaic" in lower

    def test_scifi_genre_rules(self):
        from translation_helpers import generate_style_brief

        result = generate_style_brief(
            genre="Sci-Fi",
            source_language="English",
            target_language="French",
            book_title="Sci-Fi Book",
            book_research="A sci-fi novel.",
            qa_answers={},
        )
        lower = result.lower()
        assert "technical" in lower or "precision" in lower or "military" in lower or "measurement" in lower

    def test_general_genre_rules(self):
        from translation_helpers import generate_style_brief

        result = generate_style_brief(
            genre="General",
            source_language="English",
            target_language="French",
            book_title="General Book",
            book_research="A general book.",
            qa_answers={},
        )
        lower = result.lower()
        assert "balanced" in lower or "natural" in lower or "literary" in lower

    def test_markdown_formatting(self):
        from translation_helpers import generate_style_brief

        result = generate_style_brief(
            genre="LitRPG",
            source_language="English",
            target_language="French",
            book_title="Book",
            book_research="Research.",
            qa_answers={"Q1?": "A1"},
        )
        # Should use markdown headers
        assert result.count("#") >= 3
        # Should use bullet points
        assert "- " in result


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    """Tests for CLI subcommands."""

    def _run_cli(self, args, cwd=None):
        """Helper to run the CLI script."""
        scripts_dir = str(Path(__file__).parent.parent / "cabt-cc" / "scripts")
        script_path = os.path.join(scripts_dir, "translation_helpers.py")
        cmd = [sys.executable, script_path] + args
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=30
        )
        return result

    def test_strip_glossary_cli(self, tmp_path):
        input_file = tmp_path / "glossary.md"
        input_file.write_text("| Term | Trans | (?)\n| T2 | Tr2 |", encoding="utf-8")
        output_file = tmp_path / "clean.md"

        result = self._run_cli([
            "strip-glossary",
            "--input", str(input_file),
            "--output", str(output_file),
        ])
        assert result.returncode == 0
        content = output_file.read_text(encoding="utf-8")
        assert "(?)" not in content
        assert "| Term | Trans |" in content

    def test_strip_glossary_missing_input(self, tmp_path):
        result = self._run_cli([
            "strip-glossary",
            "--input", str(tmp_path / "nonexistent.md"),
            "--output", str(tmp_path / "out.md"),
        ])
        assert result.returncode == 1
        assert result.stderr.strip() != ""

    def test_merge_terms_cli(self, tmp_path):
        terms_dir = tmp_path / "terms"
        terms_dir.mkdir()
        content = (
            "| Source | Translation | Context |\n"
            "|---|---|---|\n"
            "| Hero | Heros | Main char |\n"
        )
        (terms_dir / "chapter-01-terms.md").write_text(content, encoding="utf-8")
        output_file = tmp_path / "merged.md"

        result = self._run_cli([
            "merge-terms",
            "--terms-dir", str(terms_dir),
            "--output", str(output_file),
        ])
        assert result.returncode == 0
        content = output_file.read_text(encoding="utf-8")
        assert "Hero" in content

    def test_generate_brief_cli(self, tmp_path):
        metadata = {
            "title": "Test Book",
            "genre": "LitRPG",
            "source_language": "English",
            "target_language": "French",
            "book_research": "A LitRPG novel.",
        }
        meta_file = tmp_path / "metadata.json"
        meta_file.write_text(json.dumps(metadata), encoding="utf-8")
        output_file = tmp_path / "brief.md"

        result = self._run_cli([
            "generate-brief",
            "--metadata-path", str(meta_file),
            "--qa-json", json.dumps({"Q1?": "A1"}),
            "--output", str(output_file),
        ])
        assert result.returncode == 0
        content = output_file.read_text(encoding="utf-8")
        assert "Test Book" in content

    def test_generate_brief_missing_metadata(self, tmp_path):
        result = self._run_cli([
            "generate-brief",
            "--metadata-path", str(tmp_path / "missing.json"),
            "--qa-json", "{}",
            "--output", str(tmp_path / "brief.md"),
        ])
        assert result.returncode == 1
        assert result.stderr.strip() != ""
