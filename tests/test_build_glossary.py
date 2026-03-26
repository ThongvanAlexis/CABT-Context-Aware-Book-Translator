"""Unit tests for glossary helper utilities.

Tests cover:
- generate_glossary_template: all 4 genres, language columns, structure
- get_resume_chapter: fresh start, mid-progress, complete states
- check_token_capacity: large chapters, missing env var, no warnings
- CLI interface: template, resume, preflight subcommands
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_metadata():
    """Minimal metadata.json structure for testing."""
    return {
        "title": "Test Book",
        "genre": "LitRPG",
        "source_language": "English",
        "target_language": "French",
        "status": "prepared",
        "total_tokens": 50000,
        "chapters": [
            {"sequence": 1, "output_filename": "chapter-01.xhtml", "token_count": 8000},
            {"sequence": 2, "output_filename": "chapter-02.xhtml", "token_count": 12000},
            {"sequence": 3, "output_filename": "chapter-03.xhtml", "token_count": 15000},
            {"sequence": 4, "output_filename": "chapter-04.xhtml", "token_count": 15000},
        ],
    }


@pytest.fixture
def large_chapter_metadata():
    """Metadata with chapters exceeding 20K tokens."""
    return {
        "title": "Big Book",
        "genre": "Fantasy",
        "source_language": "English",
        "target_language": "German",
        "status": "prepared",
        "total_tokens": 120000,
        "chapters": [
            {"sequence": 1, "output_filename": "chapter-01.xhtml", "token_count": 8000},
            {"sequence": 2, "output_filename": "chapter-02.xhtml", "token_count": 25000},
            {"sequence": 3, "output_filename": "chapter-03.xhtml", "token_count": 30000},
            {"sequence": 4, "output_filename": "chapter-04.xhtml", "token_count": 12000},
        ],
    }


# ---------------------------------------------------------------------------
# generate_glossary_template tests
# ---------------------------------------------------------------------------

class TestGenerateGlossaryTemplate:
    """Tests for generate_glossary_template function."""

    def test_litrpg_has_all_sections(self):
        from glossary_helpers import generate_glossary_template

        result = generate_glossary_template("My Book", "LitRPG", "English", "French")

        assert "# Glossary -- My Book" in result
        assert "## Rules Applied" in result
        assert "See ./glossary-rules.md" in result
        assert "## Characters and Creatures" in result
        assert "## Skills / Spells / Abilities" in result
        assert "## Classes / Titles / Ranks" in result
        assert "## Game Mechanics" in result
        assert "## Notifications and SFX" in result
        assert "## Locations" in result
        assert "## Factions / Organizations" in result
        assert "## Items / Equipment" in result
        assert "## Currency / Units" in result
        assert "## Catchphrases / Expressions" in result
        assert "## World-Specific Terms" in result

    def test_fantasy_has_all_sections(self):
        from glossary_helpers import generate_glossary_template

        result = generate_glossary_template("My Book", "Fantasy", "English", "French")

        assert "## Characters and Creatures" in result
        assert "## Magic / Spells / Enchantments" in result
        assert "## Races / Peoples" in result
        assert "## Titles / Ranks / Nobility" in result
        assert "## Locations / Geography" in result
        assert "## Factions / Kingdoms / Orders" in result
        assert "## Artifacts / Magical Items" in result
        assert "## Currency / Units / Calendar" in result
        assert "## Catchphrases / Expressions" in result
        assert "## World-Specific Terms" in result

    def test_scifi_has_all_sections(self):
        from glossary_helpers import generate_glossary_template

        result = generate_glossary_template("My Book", "Sci-Fi", "English", "French")

        assert "## Characters and Creatures / Species" in result
        assert "## Technologies / Systems" in result
        assert "## Grades / Ranks / Hierarchy" in result
        assert "## Ships / Stations / Vehicles" in result
        assert "## Locations / Planets / Sectors" in result
        assert "## Factions / Corporations / Governments" in result
        assert "## Weapons / Equipment" in result
        assert "## Units / Currency / Measures" in result
        assert "## Catchphrases / Expressions" in result
        assert "## World-Specific Terms / Jargon" in result

    def test_general_has_simplified_sections(self):
        from glossary_helpers import generate_glossary_template

        result = generate_glossary_template("My Book", "General", "English", "French")

        assert "## Characters and Creatures" in result
        assert "## Key Terminology" in result
        assert "## Locations" in result
        assert "## Organizations" in result
        assert "## Items / Objects" in result
        assert "## Catchphrases / Expressions" in result
        assert "## Other Terms" in result
        # General should NOT have genre-specific sections
        assert "Game Mechanics" not in result
        assert "Magic / Spells" not in result
        assert "Technologies / Systems" not in result

    def test_language_names_in_columns(self):
        """Column headers must use actual language names, not Source/Target."""
        from glossary_helpers import generate_glossary_template

        result = generate_glossary_template("Book", "LitRPG", "English", "French")

        assert "| English | French |" in result
        # Must NOT use generic Source/Target or abbreviations
        assert "| Source |" not in result
        assert "| Target |" not in result
        assert "| EN |" not in result
        assert "| FR |" not in result

    def test_different_languages_in_columns(self):
        """Verify different language pairs produce correct column headers."""
        from glossary_helpers import generate_glossary_template

        result = generate_glossary_template("Book", "General", "Japanese", "Korean")

        assert "| Japanese | Korean |" in result

    def test_characters_table_has_register_column(self):
        """Characters table must have a Register column."""
        from glossary_helpers import generate_glossary_template

        result = generate_glossary_template("Book", "LitRPG", "English", "French")

        # Find the Characters section and verify Register column
        lines = result.split("\n")
        in_characters = False
        for line in lines:
            if "## Characters and Creatures" in line:
                in_characters = True
            elif in_characters and line.startswith("| "):
                assert "Register" in line
                break

    def test_non_characters_tables_have_context_column(self):
        """Non-character tables must have Context column (not Register)."""
        from glossary_helpers import generate_glossary_template

        result = generate_glossary_template("Book", "LitRPG", "English", "French")

        lines = result.split("\n")
        in_skills = False
        for line in lines:
            if "## Skills / Spells / Abilities" in line:
                in_skills = True
            elif in_skills and line.startswith("| "):
                assert "Context" in line
                assert "Register" not in line
                break

    def test_title_in_heading(self):
        """Title must appear in the glossary heading."""
        from glossary_helpers import generate_glossary_template

        result = generate_glossary_template(
            "Apocalypse Generic System", "LitRPG", "English", "French"
        )

        assert "# Glossary -- Apocalypse Generic System" in result

    def test_rules_applied_is_first_section(self):
        """Rules Applied must be the first section after the heading."""
        from glossary_helpers import generate_glossary_template

        result = generate_glossary_template("Book", "Fantasy", "English", "French")

        lines = result.strip().split("\n")
        h2_indices = [i for i, line in enumerate(lines) if line.startswith("## ")]
        assert len(h2_indices) > 0
        assert "## Rules Applied" in lines[h2_indices[0]]

    def test_invalid_genre_raises_valueerror(self):
        """Invalid genre must raise ValueError."""
        from glossary_helpers import generate_glossary_template

        with pytest.raises(ValueError, match="Invalid genre"):
            generate_glossary_template("Book", "Horror", "English", "French")


# ---------------------------------------------------------------------------
# get_resume_chapter tests
# ---------------------------------------------------------------------------

class TestGetResumeChapter:
    """Tests for get_resume_chapter function."""

    def test_fresh_start_no_glossary_progress(self, sample_metadata):
        """No glossary_progress field means fresh start."""
        from glossary_helpers import get_resume_chapter

        result = get_resume_chapter(sample_metadata)

        assert result["resume_from"] == 1
        assert result["total"] == 4
        assert result["is_resume"] is False

    def test_complete_status(self, sample_metadata):
        """glossary_progress.status == 'complete' means done."""
        from glossary_helpers import get_resume_chapter

        sample_metadata["glossary_progress"] = {
            "status": "complete",
            "last_chapter_processed": 4,
        }

        result = get_resume_chapter(sample_metadata)

        assert result["resume_from"] is None
        assert result["total"] == 4
        assert result["is_complete"] is True

    def test_mid_progress_resume(self, sample_metadata):
        """Resume from next chapter after last processed."""
        from glossary_helpers import get_resume_chapter

        sample_metadata["glossary_progress"] = {
            "status": "in_progress",
            "last_chapter_processed": 2,
        }

        result = get_resume_chapter(sample_metadata)

        assert result["resume_from"] == 3
        assert result["total"] == 4
        assert result["is_resume"] is True

    def test_last_chapter_zero_means_fresh_start(self, sample_metadata):
        """last_chapter_processed == 0 is effectively a fresh start."""
        from glossary_helpers import get_resume_chapter

        sample_metadata["glossary_progress"] = {
            "status": "in_progress",
            "last_chapter_processed": 0,
        }

        result = get_resume_chapter(sample_metadata)

        assert result["resume_from"] == 1
        assert result["total"] == 4
        assert result["is_resume"] is False

    def test_resume_chapter_12_of_24(self):
        """Specific example: chapter 12 of 24 processed."""
        from glossary_helpers import get_resume_chapter

        metadata = {
            "chapters": [{"sequence": i} for i in range(1, 25)],
            "glossary_progress": {
                "status": "in_progress",
                "last_chapter_processed": 12,
            },
        }

        result = get_resume_chapter(metadata)

        assert result["resume_from"] == 13
        assert result["total"] == 24
        assert result["is_resume"] is True


# ---------------------------------------------------------------------------
# check_token_capacity tests
# ---------------------------------------------------------------------------

class TestCheckTokenCapacity:
    """Tests for check_token_capacity function."""

    def test_no_large_chapters_no_warnings(self, sample_metadata):
        """All chapters under 20K: no warnings."""
        from glossary_helpers import check_token_capacity

        result = check_token_capacity(sample_metadata, max_output_tokens=16000)

        assert result["warnings"] == []
        assert result["large_chapters"] == []
        assert result["max_chapter_tokens"] == 15000

    def test_large_chapters_with_env_var_set(self, large_chapter_metadata):
        """Large chapters but env var is set: only large_chapters listed."""
        from glossary_helpers import check_token_capacity

        result = check_token_capacity(large_chapter_metadata, max_output_tokens=32000)

        assert result["large_chapters"] == [2, 3]
        assert result["max_chapter_tokens"] == 30000
        # No warning about env var since it's set
        env_warnings = [w for w in result["warnings"]
                        if "CLAUDE_CODE_MAX_OUTPUT_TOKENS" in w]
        assert len(env_warnings) == 0

    def test_large_chapters_without_env_var(self, large_chapter_metadata):
        """Large chapters and env var not set: warning about env var."""
        from glossary_helpers import check_token_capacity

        result = check_token_capacity(large_chapter_metadata, max_output_tokens=None)

        assert result["large_chapters"] == [2, 3]
        assert result["max_chapter_tokens"] == 30000
        # Should warn about CLAUDE_CODE_MAX_OUTPUT_TOKENS
        env_warnings = [w for w in result["warnings"]
                        if "CLAUDE_CODE_MAX_OUTPUT_TOKENS" in w]
        assert len(env_warnings) == 1

    def test_no_large_chapters_env_var_not_set(self, sample_metadata):
        """No large chapters and env var not set: no warnings."""
        from glossary_helpers import check_token_capacity

        result = check_token_capacity(sample_metadata, max_output_tokens=None)

        assert result["warnings"] == []
        assert result["large_chapters"] == []


# ---------------------------------------------------------------------------
# CLI interface tests
# ---------------------------------------------------------------------------

class TestCLI:
    """Tests for CLI subcommand interface."""

    @pytest.fixture
    def script_path(self):
        """Path to the glossary_helpers.py script."""
        return str(
            Path(__file__).parent.parent / "cabt-cc" / "scripts" / "glossary_helpers.py"
        )

    def test_cli_template_subcommand(self, script_path):
        """CLI template subcommand outputs glossary markdown to stdout."""
        result = subprocess.run(
            [
                sys.executable, script_path, "template",
                "--title", "CLI Test Book",
                "--genre", "General",
                "--source-language", "English",
                "--target-language", "Spanish",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "# Glossary -- CLI Test Book" in result.stdout
        assert "| English | Spanish |" in result.stdout

    def test_cli_resume_subcommand(self, script_path, sample_metadata, tmp_path):
        """CLI resume subcommand outputs JSON resume info."""
        meta_path = tmp_path / "metadata.json"
        meta_path.write_text(json.dumps(sample_metadata))

        result = subprocess.run(
            [
                sys.executable, script_path, "resume",
                "--metadata-path", str(meta_path),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["resume_from"] == 1
        assert data["total"] == 4
        assert data["is_resume"] is False

    def test_cli_preflight_subcommand(self, script_path, large_chapter_metadata,
                                       tmp_path):
        """CLI preflight subcommand outputs JSON capacity check."""
        meta_path = tmp_path / "metadata.json"
        meta_path.write_text(json.dumps(large_chapter_metadata))

        result = subprocess.run(
            [
                sys.executable, script_path, "preflight",
                "--metadata-path", str(meta_path),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["large_chapters"] == [2, 3]
        assert data["max_chapter_tokens"] == 30000


# ---------------------------------------------------------------------------
# strip_context_references tests
# ---------------------------------------------------------------------------

class TestStripContextReferences:
    """Tests for strip_context_references function."""

    def test_basic_single_context_stripped(self):
        """Basic ch.03 -- note pattern is stripped from Context column."""
        from glossary_helpers import strip_context_references

        glossary = (
            "## Characters and Creatures\n"
            "\n"
            "| English | French | Register | Context |\n"
            "|---|---|---|---|\n"
            "| Hero | Heros | casual | ch.03 -- antagonist introduced |\n"
        )
        result = strip_context_references(glossary)

        assert "| Hero | Heros | casual | antagonist introduced |" in result

    def test_multiple_contexts_with_semicolons(self):
        """Multiple ch.N references separated by semicolons are all stripped."""
        from glossary_helpers import strip_context_references

        glossary = (
            "## Skills / Spells / Abilities\n"
            "\n"
            "| English | French | Context |\n"
            "|---|---|---|\n"
            "| Fireball | Boule de feu | ch.12 -- final battle; ch.03 -- first appearance |\n"
        )
        result = strip_context_references(glossary)

        assert "| Fireball | Boule de feu | final battle; first appearance |" in result

    def test_single_digit_chapter(self):
        """Single-digit chapter number like ch.1 is stripped."""
        from glossary_helpers import strip_context_references

        glossary = (
            "| English | French | Context |\n"
            "|---|---|---|\n"
            "| Intro Term | Terme d'intro | ch.1 -- intro |\n"
        )
        result = strip_context_references(glossary)

        assert "| Intro Term | Terme d'intro | intro |" in result

    def test_triple_digit_chapter(self):
        """Triple-digit chapter number like ch.123 is stripped."""
        from glossary_helpers import strip_context_references

        glossary = (
            "| English | French | Context |\n"
            "|---|---|---|\n"
            "| Deep Term | Terme profond | ch.123 -- deep chapter |\n"
        )
        result = strip_context_references(glossary)

        assert "| Deep Term | Terme profond | deep chapter |" in result

    def test_header_rows_not_modified(self):
        """Table header rows are preserved exactly."""
        from glossary_helpers import strip_context_references

        glossary = (
            "| English | French | Context |\n"
            "|---|---|---|\n"
            "| Term | Terme | ch.03 -- note |\n"
        )
        result = strip_context_references(glossary)

        assert "| English | French | Context |" in result

    def test_separator_rows_not_modified(self):
        """Table separator rows (|---|---|) are preserved exactly."""
        from glossary_helpers import strip_context_references

        glossary = (
            "| English | French | Context |\n"
            "|---|---|---|\n"
            "| Term | Terme | ch.03 -- note |\n"
        )
        result = strip_context_references(glossary)

        assert "|---|---|---|" in result

    def test_non_table_content_not_modified(self):
        """Headings and prose outside tables are not touched."""
        from glossary_helpers import strip_context_references

        glossary = (
            "# Glossary -- My Book\n"
            "\n"
            "## Rules Applied\n"
            "\n"
            "See ./glossary-rules.md\n"
            "\n"
            "## Characters and Creatures\n"
            "\n"
            "| English | French | Register | Context |\n"
            "|---|---|---|---|\n"
            "| Hero | Heros | casual | ch.03 -- main char |\n"
        )
        result = strip_context_references(glossary)

        assert "# Glossary -- My Book" in result
        assert "## Rules Applied" in result
        assert "See ./glossary-rules.md" in result
        assert "## Characters and Creatures" in result

    def test_question_mark_markers_preserved(self):
        """(?) markers in translation columns are preserved exactly."""
        from glossary_helpers import strip_context_references

        glossary = (
            "| English | French | Context |\n"
            "|---|---|---|\n"
            "| Skill Name | Nom de comp (?) | ch.05 -- first use |\n"
        )
        result = strip_context_references(glossary)

        assert "Nom de comp (?)" in result
        assert "first use" in result

    def test_empty_context_after_stripping(self):
        """Context cell that becomes empty after stripping is left with just spaces."""
        from glossary_helpers import strip_context_references

        glossary = (
            "| English | French | Context |\n"
            "|---|---|---|\n"
            "| Term | Terme | ch.03 |\n"
        )
        result = strip_context_references(glossary)

        # The context cell should be empty (just whitespace between pipes)
        lines = result.strip().split("\n")
        data_line = [l for l in lines if "Term" in l and "Terme" in l][0]
        cells = [c.strip() for c in data_line.split("|")]
        # cells[0] and cells[-1] are empty (outside pipes), cells[1]=Term, cells[2]=Terme, cells[3]=context
        context_cell = cells[3]
        assert context_cell == ""

    def test_non_context_columns_untouched(self):
        """ch.03 appearing in term or translation columns is NOT stripped."""
        from glossary_helpers import strip_context_references

        glossary = (
            "| English | French | Context |\n"
            "|---|---|---|\n"
            "| ch.03 boss | chef ch.03 | ch.05 -- boss fight |\n"
        )
        result = strip_context_references(glossary)

        assert "ch.03 boss" in result
        assert "chef ch.03" in result
        assert "boss fight" in result
        # ch.05 should be stripped from context column
        assert "ch.05" not in result

    def test_register_table_context_stripped(self):
        """4-column tables (with Register) also get Context column stripped."""
        from glossary_helpers import strip_context_references

        glossary = (
            "| English | French | Register | Context |\n"
            "|---|---|---|---|\n"
            "| King | Roi | formal | ch.01 -- coronation scene |\n"
            "| Thief | Voleur | slang | ch.07 -- heist chapter |\n"
        )
        result = strip_context_references(glossary)

        assert "| King | Roi | formal | coronation scene |" in result
        assert "| Thief | Voleur | slang | heist chapter |" in result

    def test_em_dash_style_also_stripped(self):
        """Both -- (double hyphen) and the em-dash character are handled."""
        from glossary_helpers import strip_context_references

        glossary = (
            "| English | French | Context |\n"
            "|---|---|---|\n"
            "| Term1 | Terme1 | ch.03 \u2014 em dash note |\n"
            "| Term2 | Terme2 | ch.05 -- double hyphen note |\n"
        )
        result = strip_context_references(glossary)

        assert "em dash note" in result
        assert "double hyphen note" in result
        assert "ch.03" not in result
        assert "ch.05" not in result

    def test_multiple_tables_all_stripped(self):
        """Multiple tables in a glossary all get their Context columns stripped."""
        from glossary_helpers import strip_context_references

        glossary = (
            "## Characters and Creatures\n"
            "\n"
            "| English | French | Register | Context |\n"
            "|---|---|---|---|\n"
            "| Hero | Heros | casual | ch.01 -- intro |\n"
            "\n"
            "## Locations\n"
            "\n"
            "| English | French | Context |\n"
            "|---|---|---|\n"
            "| Castle | Chateau | ch.02 -- described |\n"
        )
        result = strip_context_references(glossary)

        assert "ch.01" not in result
        assert "ch.02" not in result
        assert "intro" in result
        assert "described" in result

    def test_row_with_no_chapter_reference_unchanged(self):
        """Data rows without ch.N references are left as-is."""
        from glossary_helpers import strip_context_references

        glossary = (
            "| English | French | Context |\n"
            "|---|---|---|\n"
            "| Term | Terme | general note |\n"
        )
        result = strip_context_references(glossary)

        assert "| Term | Terme | general note |" in result


# ---------------------------------------------------------------------------
# CLI strip-context tests
# ---------------------------------------------------------------------------

class TestCLIStripContext:
    """Tests for CLI strip-context subcommand."""

    @pytest.fixture
    def script_path(self):
        """Path to the glossary_helpers.py script."""
        return str(
            Path(__file__).parent.parent / "cabt-cc" / "scripts" / "glossary_helpers.py"
        )

    def test_cli_strip_context_reads_file_and_outputs_stripped(self, script_path, tmp_path):
        """CLI strip-context reads a glossary file and prints stripped content to stdout."""
        glossary_content = (
            "## Characters\n"
            "\n"
            "| English | French | Context |\n"
            "|---|---|---|\n"
            "| Hero | Heros | ch.03 -- main char |\n"
        )
        glossary_file = tmp_path / "glossary.md"
        glossary_file.write_text(glossary_content, encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable, script_path, "strip-context",
                "--input-path", str(glossary_file),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "main char" in result.stdout
        assert "ch.03" not in result.stdout

    def test_cli_strip_context_file_not_found(self, script_path):
        """CLI strip-context returns non-zero exit code for missing file."""
        result = subprocess.run(
            [
                sys.executable, script_path, "strip-context",
                "--input-path", "/nonexistent/glossary.md",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
