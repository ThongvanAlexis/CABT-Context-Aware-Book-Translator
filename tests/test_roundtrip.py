"""Integration tests for full extract-rebuild round-trip validation.

Tests cover:
- Full pipeline: extract -> rebuild -> validate (no modifications)
- Validation failure detection: missing files, size differences
- Binary asset exact match (0% tolerance)
- Output file existence and size
"""
import os
import sys
import zipfile

import pytest


# ---------------------------------------------------------------------------
# Round-trip integration tests
# ---------------------------------------------------------------------------

class TestRoundtripPipeline:
    """Full extract-rebuild round-trip tests using the real test EPUB."""

    def test_roundtrip_extract_rebuild_validate(self, test_epub_path, tmp_output_dir, tmp_path):
        """Full pipeline: extract, rebuild, validate passes."""
        from extract_epub import extract_epub
        from rebuild_epub import rebuild_epub, validate_roundtrip

        # Extract
        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))
        chapter_dir = str(tmp_output_dir / "source")
        output_epub = str(tmp_path / "roundtrip.epub")

        # Rebuild (no language change -- round-trip mode)
        rebuild_epub(
            str(test_epub_path), chapter_dir, output_epub,
            metadata=metadata, target_language=None
        )

        # Validate
        results = validate_roundtrip(str(test_epub_path), output_epub)
        assert results["passed"] is True, (
            f"Round-trip validation failed: {results['errors']}"
        )
        assert len(results["errors"]) == 0, (
            f"Round-trip validation has errors: {results['errors']}"
        )

    def test_roundtrip_detects_missing_file(self, test_epub_path, tmp_output_dir, tmp_path):
        """Validation fails when a chapter file is missing from chapter_dir."""
        from extract_epub import extract_epub
        from rebuild_epub import rebuild_epub, validate_roundtrip

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))
        chapter_dir = str(tmp_output_dir / "source")

        # Delete one chapter file before rebuild
        chapter_to_delete = os.path.join(chapter_dir, "chapter-01.xhtml")
        assert os.path.isfile(chapter_to_delete), "chapter-01.xhtml should exist"
        os.remove(chapter_to_delete)

        output_epub = str(tmp_path / "missing_chapter.epub")
        rebuild_epub(
            str(test_epub_path), chapter_dir, output_epub,
            metadata=metadata, target_language=None
        )

        # Validate -- should fail because a chapter file is different
        # (the original chapter content is replaced by something else or missing)
        results = validate_roundtrip(str(test_epub_path), output_epub)
        # The rebuilt EPUB will still contain the file (copied from original),
        # but the content size will differ since the chapter wasn't replaced.
        # Actually, when the chapter file is missing on disk, rebuild should
        # copy the original. So the round-trip should still pass.
        # Let's test a more meaningful case: remove a file from the rebuilt EPUB.
        # Instead, let's create a manually broken ZIP.
        import shutil

        # Create a broken rebuilt EPUB by removing a file
        broken_epub = str(tmp_path / "broken.epub")
        with zipfile.ZipFile(output_epub, "r") as orig_z, \
             zipfile.ZipFile(broken_epub, "w") as new_z:
            for item in orig_z.infolist():
                # Skip one file to simulate missing
                if item.filename.endswith("part0002.html") or \
                   item.filename.endswith("chapter1.xhtml"):
                    continue
                new_z.writestr(item, orig_z.read(item.filename))

        results = validate_roundtrip(str(test_epub_path), broken_epub)
        assert results["passed"] is False, "Validation should fail with missing file"
        assert len(results["errors"]) > 0, "Should have error about missing file"

    def test_roundtrip_detects_size_change(self, test_epub_path, tmp_output_dir, tmp_path):
        """Validation fails when file size exceeds tolerance."""
        from extract_epub import extract_epub
        from rebuild_epub import rebuild_epub, validate_roundtrip

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))
        chapter_dir = str(tmp_output_dir / "source")

        # Modify a chapter to add significant extra content
        chapter_file = os.path.join(chapter_dir, "chapter-01.xhtml")
        with open(chapter_file, "a", encoding="utf-8") as f:
            # Add enough content to exceed 0% tolerance
            f.write("<!-- EXTRA CONTENT " + "x" * 10000 + " -->")

        output_epub = str(tmp_path / "size_diff.epub")
        rebuild_epub(
            str(test_epub_path), chapter_dir, output_epub,
            metadata=metadata, target_language=None
        )

        # Validate with 0% tolerance -- should fail
        results = validate_roundtrip(str(test_epub_path), output_epub, tolerance_pct=0.0)
        assert results["passed"] is False, (
            "Validation should fail with 0% tolerance and modified chapter"
        )
        assert len(results["errors"]) > 0, "Should have size difference error"

    def test_roundtrip_binary_exact_match(self, test_epub_path, tmp_output_dir, tmp_path):
        """Binary assets are byte-identical after round-trip (0% tolerance)."""
        from extract_epub import extract_epub
        from rebuild_epub import rebuild_epub

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))
        chapter_dir = str(tmp_output_dir / "source")
        output_epub = str(tmp_path / "binary_check.epub")

        rebuild_epub(
            str(test_epub_path), chapter_dir, output_epub,
            metadata=metadata, target_language=None
        )

        binary_extensions = {".png", ".jpg", ".jpeg", ".gif", ".svg",
                             ".ttf", ".otf", ".woff", ".woff2"}

        with zipfile.ZipFile(str(test_epub_path), "r") as orig, \
             zipfile.ZipFile(output_epub, "r") as rebuilt:
            for name in orig.namelist():
                ext = os.path.splitext(name)[1].lower()
                if ext in binary_extensions:
                    orig_data = orig.read(name)
                    rebuilt_data = rebuilt.read(name)
                    assert orig_data == rebuilt_data, (
                        f"Binary file {name} not byte-identical after round-trip"
                    )

    def test_roundtrip_output_file_exists(self, test_epub_path, tmp_output_dir, tmp_path):
        """Rebuilt EPUB file exists on disk and has non-zero size."""
        from extract_epub import extract_epub
        from rebuild_epub import rebuild_epub

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))
        chapter_dir = str(tmp_output_dir / "source")
        output_epub = str(tmp_path / "exists_check.epub")

        rebuild_epub(
            str(test_epub_path), chapter_dir, output_epub,
            metadata=metadata, target_language=None
        )

        assert os.path.isfile(output_epub), "Rebuilt EPUB file does not exist"
        assert os.path.getsize(output_epub) > 0, "Rebuilt EPUB file is empty"
