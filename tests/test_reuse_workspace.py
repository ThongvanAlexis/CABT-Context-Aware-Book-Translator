"""Tests for reuse_workspace.py -- workspace reuse script.

Tests the core reuse_workspace() function and CLI entry point.
Covers: file copying, glossary context stripping, metadata recording,
missing file handling, and error cases.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_metadata(title="Previous Book", genre="LitRPG",
                   source_language="English", target_language="French"):
    """Create a minimal metadata.json dict."""
    return {
        "title": title,
        "genre": genre,
        "source_language": source_language,
        "target_language": target_language,
        "chapters": [],
    }


def _write_metadata(workspace, metadata):
    """Write metadata.json to a workspace directory."""
    meta_path = workspace / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def _make_source_workspace(tmp_path, metadata=None, glossary=None,
                           rules=None, brief=None):
    """Create a source workspace with optional files.

    Args:
        tmp_path: pytest tmp_path fixture.
        metadata: metadata dict (defaults to standard test metadata).
        glossary: glossary.md content string, or None to skip.
        rules: glossary-rules.md content string, or None to skip.
        brief: translation-style-brief.md content string, or None to skip.

    Returns:
        Path to the source workspace directory.
    """
    source = tmp_path / "source-workspace"
    source.mkdir()

    if metadata is None:
        metadata = _make_metadata()
    _write_metadata(source, metadata)

    if glossary is not None:
        (source / "glossary.md").write_text(glossary, encoding="utf-8")

    if rules is not None:
        (source / "glossary-rules.md").write_text(rules, encoding="utf-8")

    if brief is not None:
        # Brief lives in output/{lang}/translation-style-brief.md
        lang_dir = metadata["target_language"].lower().replace(" ", "-")
        brief_dir = source / "output" / lang_dir
        brief_dir.mkdir(parents=True)
        (brief_dir / "translation-style-brief.md").write_text(
            brief, encoding="utf-8"
        )

    return source


def _make_target_workspace(tmp_path):
    """Create an empty target workspace with metadata.json."""
    target = tmp_path / "target-workspace"
    target.mkdir()
    _write_metadata(target, _make_metadata(title="New Book"))
    return target


# ---------------------------------------------------------------------------
# Tests: All three files present
# ---------------------------------------------------------------------------

class TestAllFilesPresent:
    """When source has glossary, rules, and brief -- all are copied."""

    def test_all_files_copied(self, tmp_path):
        """All three files copied, had_* all true."""
        from reuse_workspace import reuse_workspace

        glossary_text = (
            "# Glossary -- Previous Book\n\n"
            "## Characters and Creatures\n\n"
            "| English | French | Register | Context |\n"
            "|---|---|---|---|\n"
            "| Hero | Heros | formal | ch.03 -- main character |\n"
        )
        rules_text = "# Glossary Rules\n\nRule 1: Be consistent."
        brief_text = "# Translation Style Brief\n\nTone: formal."

        source = _make_source_workspace(
            tmp_path, glossary=glossary_text, rules=rules_text, brief=brief_text
        )
        target = _make_target_workspace(tmp_path)

        result = reuse_workspace(str(source), str(target))

        assert result["had_glossary"] is True
        assert result["had_rules"] is True
        assert result["had_brief"] is True
        assert result["source_path"] == str(source)

    def test_glossary_is_stripped(self, tmp_path):
        """glossary.md has chapter references stripped."""
        from reuse_workspace import reuse_workspace

        glossary_text = (
            "# Glossary -- Previous Book\n\n"
            "## Characters and Creatures\n\n"
            "| English | French | Register | Context |\n"
            "|---|---|---|---|\n"
            "| Hero | Heros | formal | ch.03 -- main character |\n"
            "| Villain | Mechant | neutral | ch.05 -- antagonist |\n"
        )

        source = _make_source_workspace(tmp_path, glossary=glossary_text)
        target = _make_target_workspace(tmp_path)

        reuse_workspace(str(source), str(target))

        copied_glossary = (Path(target) / "glossary.md").read_text(encoding="utf-8")
        # ch.03 and ch.05 references should be stripped
        assert "ch.03" not in copied_glossary
        assert "ch.05" not in copied_glossary
        # Content notes should remain
        assert "main character" in copied_glossary
        assert "antagonist" in copied_glossary

    def test_rules_copied_as_is(self, tmp_path):
        """glossary-rules.md is copied without modification."""
        from reuse_workspace import reuse_workspace

        rules_text = "# Glossary Rules\n\nRule 1: Be consistent.\nRule 2: Preserve tone."

        source = _make_source_workspace(tmp_path, rules=rules_text)
        target = _make_target_workspace(tmp_path)

        reuse_workspace(str(source), str(target))

        copied_rules = (Path(target) / "glossary-rules.md").read_text(encoding="utf-8")
        assert copied_rules == rules_text

    def test_brief_copied_to_root(self, tmp_path):
        """translation-style-brief.md is copied to target root (not output/)."""
        from reuse_workspace import reuse_workspace

        brief_text = "# Translation Style Brief\n\nTone: formal and literary."

        source = _make_source_workspace(tmp_path, brief=brief_text)
        target = _make_target_workspace(tmp_path)

        reuse_workspace(str(source), str(target))

        copied_brief = (Path(target) / "translation-style-brief.md").read_text(
            encoding="utf-8"
        )
        assert copied_brief == brief_text
        # Should NOT be in output/{lang}/ in target
        assert not (Path(target) / "output").exists()


# ---------------------------------------------------------------------------
# Tests: Partial files present
# ---------------------------------------------------------------------------

class TestPartialFiles:
    """When only some source files exist, missing ones are silently skipped."""

    def test_only_glossary(self, tmp_path):
        """Only glossary.md present -- copied with strip, others false."""
        from reuse_workspace import reuse_workspace

        glossary_text = "# Glossary\n\n| English | French | Context |\n|---|---|---|\n| Word | Mot | ch.01 -- note |\n"
        source = _make_source_workspace(tmp_path, glossary=glossary_text)
        target = _make_target_workspace(tmp_path)

        result = reuse_workspace(str(source), str(target))

        assert result["had_glossary"] is True
        assert result["had_rules"] is False
        assert result["had_brief"] is False
        assert (Path(target) / "glossary.md").exists()
        assert not (Path(target) / "glossary-rules.md").exists()
        assert not (Path(target) / "translation-style-brief.md").exists()

    def test_only_rules(self, tmp_path):
        """Only glossary-rules.md present -- copied, others false."""
        from reuse_workspace import reuse_workspace

        rules_text = "# Rules\n\nKeep it simple."
        source = _make_source_workspace(tmp_path, rules=rules_text)
        target = _make_target_workspace(tmp_path)

        result = reuse_workspace(str(source), str(target))

        assert result["had_glossary"] is False
        assert result["had_rules"] is True
        assert result["had_brief"] is False

    def test_only_brief(self, tmp_path):
        """Only translation-style-brief.md present -- copied to target root."""
        from reuse_workspace import reuse_workspace

        brief_text = "# Brief\n\nFormal tone."
        source = _make_source_workspace(tmp_path, brief=brief_text)
        target = _make_target_workspace(tmp_path)

        result = reuse_workspace(str(source), str(target))

        assert result["had_glossary"] is False
        assert result["had_rules"] is False
        assert result["had_brief"] is True
        assert (Path(target) / "translation-style-brief.md").exists()

    def test_brief_at_root_fallback(self, tmp_path):
        """Brief at workspace root (from a previous reuse import) is found and copied."""
        from reuse_workspace import reuse_workspace

        brief_text = "# Brief\n\nImported from earlier book."
        # Place brief at source root instead of output/{lang}/
        source = _make_source_workspace(tmp_path)
        (source / "translation-style-brief.md").write_text(brief_text, encoding="utf-8")
        target = _make_target_workspace(tmp_path)

        result = reuse_workspace(str(source), str(target))

        assert result["had_brief"] is True
        copied = (Path(target) / "translation-style-brief.md").read_text(encoding="utf-8")
        assert copied == brief_text

    def test_brief_in_output_preferred_over_root(self, tmp_path):
        """Brief in output/{lang}/ takes priority over one at root."""
        from reuse_workspace import reuse_workspace

        root_brief = "# Brief at root"
        output_brief = "# Brief in output dir"
        source = _make_source_workspace(tmp_path, brief=output_brief)
        # Also place a different brief at root
        (source / "translation-style-brief.md").write_text(root_brief, encoding="utf-8")
        target = _make_target_workspace(tmp_path)

        result = reuse_workspace(str(source), str(target))

        assert result["had_brief"] is True
        copied = (Path(target) / "translation-style-brief.md").read_text(encoding="utf-8")
        assert copied == output_brief

    def test_no_reusable_files(self, tmp_path):
        """No reusable files present -- all had_* false, no error."""
        from reuse_workspace import reuse_workspace

        source = _make_source_workspace(tmp_path)
        target = _make_target_workspace(tmp_path)

        result = reuse_workspace(str(source), str(target))

        assert result["had_glossary"] is False
        assert result["had_rules"] is False
        assert result["had_brief"] is False


# ---------------------------------------------------------------------------
# Tests: Error cases
# ---------------------------------------------------------------------------

class TestErrorCases:
    """Error handling for missing metadata and invalid workspaces."""

    def test_source_missing_metadata(self, tmp_path):
        """Source workspace without metadata.json raises error."""
        from reuse_workspace import reuse_workspace

        source = tmp_path / "no-meta-source"
        source.mkdir()
        target = _make_target_workspace(tmp_path)

        with pytest.raises(FileNotFoundError, match="metadata.json"):
            reuse_workspace(str(source), str(target))

    def test_target_missing_metadata(self, tmp_path):
        """Target workspace without metadata.json raises error."""
        from reuse_workspace import reuse_workspace

        source = _make_source_workspace(tmp_path)
        target = tmp_path / "no-meta-target"
        target.mkdir()

        with pytest.raises(FileNotFoundError, match="metadata.json"):
            reuse_workspace(str(source), str(target))


# ---------------------------------------------------------------------------
# Tests: Metadata recording
# ---------------------------------------------------------------------------

class TestMetadataRecording:
    """Target metadata.json gets glossary_reuse field."""

    def test_glossary_reuse_field_written(self, tmp_path):
        """glossary_reuse field written to target metadata.json."""
        from reuse_workspace import reuse_workspace

        glossary_text = "# Glossary\n"
        rules_text = "# Rules\n"

        source = _make_source_workspace(
            tmp_path, glossary=glossary_text, rules=rules_text
        )
        target = _make_target_workspace(tmp_path)

        reuse_workspace(str(source), str(target))

        meta = json.loads((Path(target) / "metadata.json").read_text(encoding="utf-8"))
        reuse = meta["glossary_reuse"]

        assert reuse["source_workspace"] == str(source)
        assert reuse["source_book_title"] == "Previous Book"
        assert "imported_at" in reuse
        assert "glossary.md" in reuse["imported_files"]
        assert "glossary-rules.md" in reuse["imported_files"]
        # brief was NOT provided, so it should NOT be in imported_files
        assert "translation-style-brief.md" not in reuse["imported_files"]

    def test_imported_files_only_lists_copied(self, tmp_path):
        """imported_files only lists files that were actually copied."""
        from reuse_workspace import reuse_workspace

        brief_text = "# Brief\n"
        source = _make_source_workspace(tmp_path, brief=brief_text)
        target = _make_target_workspace(tmp_path)

        reuse_workspace(str(source), str(target))

        meta = json.loads((Path(target) / "metadata.json").read_text(encoding="utf-8"))
        reuse = meta["glossary_reuse"]

        assert reuse["imported_files"] == ["translation-style-brief.md"]

    def test_no_files_empty_imported_list(self, tmp_path):
        """When no files copied, imported_files is empty list."""
        from reuse_workspace import reuse_workspace

        source = _make_source_workspace(tmp_path)
        target = _make_target_workspace(tmp_path)

        reuse_workspace(str(source), str(target))

        meta = json.loads((Path(target) / "metadata.json").read_text(encoding="utf-8"))
        reuse = meta["glossary_reuse"]

        assert reuse["imported_files"] == []

    def test_existing_metadata_preserved(self, tmp_path):
        """Existing target metadata fields are preserved when adding reuse field."""
        from reuse_workspace import reuse_workspace

        source = _make_source_workspace(tmp_path)
        target = _make_target_workspace(tmp_path)

        reuse_workspace(str(source), str(target))

        meta = json.loads((Path(target) / "metadata.json").read_text(encoding="utf-8"))
        # Original fields should still be there
        assert meta["title"] == "New Book"
        assert "glossary_reuse" in meta


# ---------------------------------------------------------------------------
# Tests: CLI
# ---------------------------------------------------------------------------

class TestCLI:
    """CLI entry point outputs JSON to stdout, errors to stderr."""

    def test_cli_outputs_json(self, tmp_path):
        """CLI prints valid JSON to stdout on success."""
        glossary_text = "# Glossary\n"
        source = _make_source_workspace(tmp_path, glossary=glossary_text)
        target = _make_target_workspace(tmp_path)

        script_path = str(
            Path(__file__).parent.parent / "cabt-cc" / "scripts" / "reuse_workspace.py"
        )
        result = subprocess.run(
            [
                sys.executable, script_path,
                "--source-workspace", str(source),
                "--target-workspace", str(target),
            ],
            capture_output=True, text=True,
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["had_glossary"] is True

    def test_cli_error_missing_source_metadata(self, tmp_path):
        """CLI exits 1 with error when source lacks metadata.json."""
        source = tmp_path / "bad-source"
        source.mkdir()
        target = _make_target_workspace(tmp_path)

        script_path = str(
            Path(__file__).parent.parent / "cabt-cc" / "scripts" / "reuse_workspace.py"
        )
        result = subprocess.run(
            [
                sys.executable, script_path,
                "--source-workspace", str(source),
                "--target-workspace", str(target),
            ],
            capture_output=True, text=True,
        )

        assert result.returncode == 1
        assert "metadata.json" in result.stderr.lower() or "metadata.json" in result.stderr

    def test_cli_error_missing_target_metadata(self, tmp_path):
        """CLI exits 1 with error when target lacks metadata.json."""
        source = _make_source_workspace(tmp_path)
        target = tmp_path / "bad-target"
        target.mkdir()

        script_path = str(
            Path(__file__).parent.parent / "cabt-cc" / "scripts" / "reuse_workspace.py"
        )
        result = subprocess.run(
            [
                sys.executable, script_path,
                "--source-workspace", str(source),
                "--target-workspace", str(target),
            ],
            capture_output=True, text=True,
        )

        assert result.returncode == 1
        assert "metadata.json" in result.stderr.lower() or "metadata.json" in result.stderr
