"""Tests for prepare_workspace.py -- workspace creation for translation pipeline."""
import json
import os
import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# TestSanitizeTitle
# ---------------------------------------------------------------------------


class TestSanitizeTitle:
    """Test title sanitization edge cases."""

    def test_strips_special_chars_and_parentheses(self):
        from prepare_workspace import sanitize_title

        result = sanitize_title(
            "Apocalypse: Generic System (The Stitched Worlds Book 1)"
        )
        assert result == "Apocalypse-Generic-System-The-Stitched-Worlds-Book-1"

    def test_strips_apostrophes_and_unicode(self):
        from prepare_workspace import sanitize_title

        result = sanitize_title("L'Apocalypse du Monde")
        assert result == "LApocalypse-du-Monde"

    def test_collapses_extra_spaces(self):
        from prepare_workspace import sanitize_title

        result = sanitize_title("  Extra   Spaces  ")
        assert result == "Extra-Spaces"

    def test_strips_leading_trailing_hyphens(self):
        from prepare_workspace import sanitize_title

        result = sanitize_title("---Hyphens---")
        assert result == "Hyphens"

    def test_empty_string_raises_value_error(self):
        from prepare_workspace import sanitize_title

        with pytest.raises(ValueError):
            sanitize_title("")

    def test_only_special_chars_raises_value_error(self):
        from prepare_workspace import sanitize_title

        with pytest.raises(ValueError):
            sanitize_title("!@#$%^&*()")

    def test_preserves_numbers(self):
        from prepare_workspace import sanitize_title

        result = sanitize_title("Book 42 of 100")
        assert result == "Book-42-of-100"

    def test_mixed_hyphens_and_spaces(self):
        from prepare_workspace import sanitize_title

        result = sanitize_title("Word - Another - Third")
        assert result == "Word-Another-Third"


# ---------------------------------------------------------------------------
# TestTimestampPrefix
# ---------------------------------------------------------------------------


class TestTimestampPrefix:
    """Test that workspace names include yyyymmdd_hhmm_ timestamp prefix."""

    def test_workspace_name_starts_with_timestamp_pattern(self, test_epub_path, tmp_path, workspace_args):
        """Workspace folder name should start with yyyymmdd_hhmm_ pattern."""
        from prepare_workspace import prepare_workspace

        _result, ws_name = prepare_workspace(
            epub_path=str(test_epub_path),
            base_dir=str(tmp_path),
            **workspace_args,
        )
        assert re.match(r'^\d{8}_\d{4}_', ws_name), \
            f"Workspace name '{ws_name}' does not start with yyyymmdd_hhmm_ prefix"

    def test_workspace_name_contains_sanitized_title_after_prefix(self, test_epub_path, tmp_path, workspace_args):
        """Workspace folder name should contain the sanitized title after the timestamp prefix."""
        from prepare_workspace import prepare_workspace, sanitize_title

        result, ws_name = prepare_workspace(
            epub_path=str(test_epub_path),
            base_dir=str(tmp_path),
            **workspace_args,
        )
        sanitized = sanitize_title(result["title"])
        # After removing the timestamp prefix, the rest should be the sanitized title
        suffix = re.sub(r'^\d{8}_\d{4}_', '', ws_name)
        assert suffix == sanitized, \
            f"Expected sanitized title '{sanitized}' after prefix, got '{suffix}'"

    def test_json_output_workspace_path_includes_timestamp(self, test_epub_path, tmp_path, workspace_args):
        """JSON output workspace_path should include the timestamp prefix."""
        from prepare_workspace import prepare_workspace

        _result, ws_name = prepare_workspace(
            epub_path=str(test_epub_path),
            base_dir=str(tmp_path),
            **workspace_args,
        )
        # The workspace_path should contain the timestamped workspace name
        workspace_path = os.path.join(str(tmp_path), ws_name)
        assert os.path.isdir(workspace_path), \
            f"Workspace directory not found at {workspace_path}"


# ---------------------------------------------------------------------------
# TestLanguageToDirname
# ---------------------------------------------------------------------------


class TestLanguageToDirname:
    """Test language name to directory conversion."""

    def test_single_word_lowercase(self):
        from prepare_workspace import language_to_dirname

        assert language_to_dirname("French") == "french"

    def test_multi_word_hyphenated(self):
        from prepare_workspace import language_to_dirname

        assert language_to_dirname("Brazilian Portuguese") == "brazilian-portuguese"

    def test_already_lowercase(self):
        from prepare_workspace import language_to_dirname

        assert language_to_dirname("japanese") == "japanese"

    def test_mixed_case(self):
        from prepare_workspace import language_to_dirname

        assert language_to_dirname("Traditional Chinese") == "traditional-chinese"


# ---------------------------------------------------------------------------
# TestGenreValidation
# ---------------------------------------------------------------------------


class TestGenreValidation:
    """Test valid and invalid genre values."""

    @pytest.mark.parametrize("genre", ["LitRPG", "Fantasy", "Sci-Fi", "General"])
    def test_valid_genres_accepted(self, genre, test_epub_path, tmp_path, workspace_args):
        """Valid genres should not raise."""
        from prepare_workspace import prepare_workspace

        workspace_args["genre"] = genre
        result, ws_name = prepare_workspace(
            epub_path=str(test_epub_path),
            base_dir=str(tmp_path),
            **workspace_args,
        )
        assert result is not None

    def test_invalid_genre_raises_value_error(self, test_epub_path, tmp_path, workspace_args):
        from prepare_workspace import prepare_workspace

        workspace_args["genre"] = "Romance"
        with pytest.raises(ValueError, match="genre"):
            prepare_workspace(
                epub_path=str(test_epub_path),
                base_dir=str(tmp_path),
                **workspace_args,
            )


# ---------------------------------------------------------------------------
# TestRerunProtection
# ---------------------------------------------------------------------------


class TestRerunProtection:
    """Test that existing workspace raises FileExistsError."""

    def test_existing_workspace_raises_file_exists_error(
        self, test_epub_path, tmp_path, workspace_args
    ):
        from prepare_workspace import prepare_workspace

        # First run -- should succeed
        _result, ws_name = prepare_workspace(
            epub_path=str(test_epub_path),
            base_dir=str(tmp_path),
            **workspace_args,
        )
        # Second run within the same minute -- same timestamp prefix,
        # so folder name collides and FileExistsError is raised
        with pytest.raises(FileExistsError, match="already exists"):
            prepare_workspace(
                epub_path=str(test_epub_path),
                base_dir=str(tmp_path),
                **workspace_args,
            )


# ---------------------------------------------------------------------------
# TestMetadataSchema
# ---------------------------------------------------------------------------


class TestMetadataSchema:
    """Test metadata.json contains all required fields with correct values."""

    @pytest.fixture
    def workspace_metadata(self, test_epub_path, tmp_path, workspace_args):
        """Run prepare_workspace and return the metadata.json contents."""
        from prepare_workspace import prepare_workspace

        _result, _ws_name = prepare_workspace(
            epub_path=str(test_epub_path),
            base_dir=str(tmp_path),
            **workspace_args,
        )
        # Find the workspace directory (should be the only dir in tmp_path)
        workspace_dirs = [
            d for d in tmp_path.iterdir() if d.is_dir()
        ]
        assert len(workspace_dirs) == 1, f"Expected 1 workspace dir, found {len(workspace_dirs)}"
        meta_path = workspace_dirs[0] / "metadata.json"
        assert meta_path.is_file(), "metadata.json not found"
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_has_title(self, workspace_metadata):
        assert "title" in workspace_metadata
        assert isinstance(workspace_metadata["title"], str)
        assert len(workspace_metadata["title"]) > 0

    def test_has_source_language_from_user(self, workspace_metadata):
        """source_language should be the user-provided value, NOT EPUB metadata."""
        assert workspace_metadata["source_language"] == "English"

    def test_has_target_language(self, workspace_metadata):
        assert workspace_metadata["target_language"] == "French"

    def test_has_genre(self, workspace_metadata):
        assert workspace_metadata["genre"] == "General"

    def test_has_status_prepared(self, workspace_metadata):
        assert workspace_metadata["status"] == "prepared"

    def test_has_epub_path_absolute(self, workspace_metadata):
        assert "epub_path" in workspace_metadata
        assert os.path.isabs(workspace_metadata["epub_path"])

    def test_has_chapters_list(self, workspace_metadata):
        assert "chapters" in workspace_metadata
        assert isinstance(workspace_metadata["chapters"], list)
        assert len(workspace_metadata["chapters"]) > 0

    def test_chapter_has_required_keys(self, workspace_metadata):
        chapter = workspace_metadata["chapters"][0]
        assert "sequence" in chapter
        assert "original_filename" in chapter
        assert "output_filename" in chapter
        assert "detected_title" in chapter


# ---------------------------------------------------------------------------
# TestWorkspaceStructure
# ---------------------------------------------------------------------------


class TestWorkspaceStructure:
    """Test directory layout (source/, output/[lang]/, files)."""

    @pytest.fixture
    def workspace_dir(self, test_epub_path, tmp_path, workspace_args):
        """Run prepare_workspace and return the workspace directory path."""
        from prepare_workspace import prepare_workspace

        _result, _ws_name = prepare_workspace(
            epub_path=str(test_epub_path),
            base_dir=str(tmp_path),
            **workspace_args,
        )
        workspace_dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(workspace_dirs) == 1
        return workspace_dirs[0]

    def test_source_dir_exists_with_chapters(self, workspace_dir):
        source_dir = workspace_dir / "source"
        assert source_dir.is_dir()
        xhtml_files = list(source_dir.glob("chapter-*.xhtml"))
        assert len(xhtml_files) > 0

    def test_output_lang_dir_exists_empty(self, workspace_dir):
        output_dir = workspace_dir / "output" / "french"
        assert output_dir.is_dir()
        assert list(output_dir.iterdir()) == []

    def test_metadata_json_exists(self, workspace_dir):
        assert (workspace_dir / "metadata.json").is_file()

    def test_roundtrip_epub_exists(self, workspace_dir):
        assert (workspace_dir / "test-roundtrip.epub").is_file()

    def test_detection_report_exists(self, workspace_dir):
        assert (workspace_dir / "detection_report.txt").is_file()

    def test_workspace_name_has_timestamp_prefix(self, workspace_dir):
        """Workspace folder name should start with yyyymmdd_hhmm_ prefix."""
        name = workspace_dir.name
        # Must start with timestamp prefix pattern
        assert re.match(r'^\d{8}_\d{4}_', name), \
            f"Workspace name '{name}' does not start with yyyymmdd_hhmm_ prefix"
        # After the prefix, should not contain special characters
        suffix = re.sub(r'^\d{8}_\d{4}_', '', name)
        assert ":" not in suffix
        assert "(" not in suffix
        assert ")" not in suffix
        # Should use hyphens, not spaces
        assert " " not in name


# ---------------------------------------------------------------------------
# TestPrepareWorkspacePipeline
# ---------------------------------------------------------------------------


class TestPrepareWorkspacePipeline:
    """Integration test with real EPUB -- full pipeline creates valid workspace."""

    def test_full_pipeline_creates_valid_workspace(
        self, test_epub_path, tmp_path, workspace_args
    ):
        """End-to-end test: prepare_workspace creates a complete, valid workspace."""
        from prepare_workspace import prepare_workspace

        result, ws_name = prepare_workspace(
            epub_path=str(test_epub_path),
            base_dir=str(tmp_path),
            **workspace_args,
        )

        # Returns metadata dict
        assert isinstance(result, dict)
        assert result["status"] == "prepared"
        assert result["genre"] == "General"
        assert result["source_language"] == "English"
        assert result["target_language"] == "French"

        # Workspace name has timestamp prefix
        assert re.match(r'^\d{8}_\d{4}_', ws_name), \
            f"Workspace name '{ws_name}' missing timestamp prefix"

        # Workspace directory exists with correct name
        workspace_dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(workspace_dirs) == 1
        ws = workspace_dirs[0]
        assert ws.name == ws_name

        # Source chapters extracted
        source_files = sorted((ws / "source").glob("chapter-*.xhtml"))
        assert len(source_files) == len(result["chapters"])

        # Output language directory ready
        assert (ws / "output" / "french").is_dir()

        # Roundtrip EPUB valid (exists and non-empty)
        rt_epub = ws / "test-roundtrip.epub"
        assert rt_epub.is_file()
        assert rt_epub.stat().st_size > 0

        # metadata.json matches returned dict
        with open(ws / "metadata.json", "r", encoding="utf-8") as f:
            saved_meta = json.load(f)
        assert saved_meta == result

    def test_pipeline_with_litrpg_genre(self, test_epub_path, tmp_path, workspace_args):
        """Test pipeline with LitRPG genre (most common use case)."""
        from prepare_workspace import prepare_workspace

        workspace_args["genre"] = "LitRPG"
        workspace_args["target_language"] = "Japanese"

        result, ws_name = prepare_workspace(
            epub_path=str(test_epub_path),
            base_dir=str(tmp_path),
            **workspace_args,
        )

        assert result["genre"] == "LitRPG"
        assert result["target_language"] == "Japanese"

        # Check Japanese output directory
        workspace_dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        ws = workspace_dirs[0]
        assert (ws / "output" / "japanese").is_dir()
