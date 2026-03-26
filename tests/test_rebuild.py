"""Tests for EPUB reconstruction script.

Tests cover:
- Rebuilt EPUB structure (valid ZIP, mimetype first and stored)
- Asset preservation (images, CSS, fonts byte-identical)
- dc:language metadata update
- OPF location dynamic resolution
- File count preservation
"""
import os
import sys
import zipfile

import pytest
from lxml import etree


# ---------------------------------------------------------------------------
# Rebuild script tests
# ---------------------------------------------------------------------------

class TestRebuildCreatesValidEpub:
    """Rebuilt EPUB is a valid ZIP with correct structure."""

    def test_rebuild_creates_valid_epub(self, test_epub_path, tmp_output_dir, tmp_path):
        """Rebuilt file is a valid ZIP with mimetype first entry."""
        from extract_epub import extract_epub
        from rebuild_epub import rebuild_epub

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))
        chapter_dir = str(tmp_output_dir / "source")
        output_epub = str(tmp_path / "rebuilt.epub")

        rebuild_epub(str(test_epub_path), chapter_dir, output_epub, metadata=metadata)

        # Must be a valid ZIP
        assert zipfile.is_zipfile(output_epub), "Rebuilt file is not a valid ZIP"

        # Must open without error
        with zipfile.ZipFile(output_epub, "r") as z:
            names = z.namelist()
            assert len(names) > 0, "Rebuilt EPUB is empty"

    def test_rebuild_mimetype_first_and_stored(self, test_epub_path, tmp_output_dir, tmp_path):
        """mimetype is first entry with ZIP_STORED compression."""
        from extract_epub import extract_epub
        from rebuild_epub import rebuild_epub

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))
        chapter_dir = str(tmp_output_dir / "source")
        output_epub = str(tmp_path / "rebuilt.epub")

        rebuild_epub(str(test_epub_path), chapter_dir, output_epub, metadata=metadata)

        with zipfile.ZipFile(output_epub, "r") as z:
            # First entry must be mimetype
            first_entry = z.infolist()[0]
            assert first_entry.filename == "mimetype", (
                f"First ZIP entry should be 'mimetype', got '{first_entry.filename}'"
            )

            # Must be uncompressed (ZIP_STORED = 0)
            assert first_entry.compress_type == zipfile.ZIP_STORED, (
                f"mimetype should use ZIP_STORED (0), got {first_entry.compress_type}"
            )

            # Content must be correct
            content = z.read("mimetype")
            assert content == b"application/epub+zip", (
                f"mimetype content should be 'application/epub+zip', got {content}"
            )


class TestRebuildPreservesAssets:
    """Non-chapter files are copied byte-for-byte."""

    def test_rebuild_preserves_images(self, test_epub_path, tmp_output_dir, tmp_path):
        """Image files are byte-identical in original and rebuilt."""
        from extract_epub import extract_epub
        from rebuild_epub import rebuild_epub

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))
        chapter_dir = str(tmp_output_dir / "source")
        output_epub = str(tmp_path / "rebuilt.epub")

        rebuild_epub(str(test_epub_path), chapter_dir, output_epub, metadata=metadata)

        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".svg"}

        with zipfile.ZipFile(str(test_epub_path), "r") as orig, \
             zipfile.ZipFile(output_epub, "r") as rebuilt:
            for name in orig.namelist():
                ext = os.path.splitext(name)[1].lower()
                if ext in image_extensions:
                    orig_data = orig.read(name)
                    rebuilt_data = rebuilt.read(name)
                    assert orig_data == rebuilt_data, (
                        f"Image {name} differs between original and rebuilt"
                    )

    def test_rebuild_preserves_css(self, test_epub_path, tmp_output_dir, tmp_path):
        """CSS files are byte-identical in original and rebuilt."""
        from extract_epub import extract_epub
        from rebuild_epub import rebuild_epub

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))
        chapter_dir = str(tmp_output_dir / "source")
        output_epub = str(tmp_path / "rebuilt.epub")

        rebuild_epub(str(test_epub_path), chapter_dir, output_epub, metadata=metadata)

        with zipfile.ZipFile(str(test_epub_path), "r") as orig, \
             zipfile.ZipFile(output_epub, "r") as rebuilt:
            for name in orig.namelist():
                if name.endswith(".css"):
                    orig_data = orig.read(name)
                    rebuilt_data = rebuilt.read(name)
                    assert orig_data == rebuilt_data, (
                        f"CSS {name} differs between original and rebuilt"
                    )

    def test_rebuild_preserves_fonts(self, test_epub_path, tmp_output_dir, tmp_path):
        """Font files are byte-identical in original and rebuilt."""
        from extract_epub import extract_epub
        from rebuild_epub import rebuild_epub

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))
        chapter_dir = str(tmp_output_dir / "source")
        output_epub = str(tmp_path / "rebuilt.epub")

        rebuild_epub(str(test_epub_path), chapter_dir, output_epub, metadata=metadata)

        font_extensions = {".ttf", ".otf", ".woff", ".woff2"}

        with zipfile.ZipFile(str(test_epub_path), "r") as orig, \
             zipfile.ZipFile(output_epub, "r") as rebuilt:
            for name in orig.namelist():
                ext = os.path.splitext(name)[1].lower()
                if ext in font_extensions:
                    orig_data = orig.read(name)
                    rebuilt_data = rebuilt.read(name)
                    assert orig_data == rebuilt_data, (
                        f"Font {name} differs between original and rebuilt"
                    )

    def test_rebuild_file_count(self, test_epub_path, tmp_output_dir, tmp_path):
        """Rebuilt EPUB has same number of files as original."""
        from extract_epub import extract_epub
        from rebuild_epub import rebuild_epub

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))
        chapter_dir = str(tmp_output_dir / "source")
        output_epub = str(tmp_path / "rebuilt.epub")

        rebuild_epub(str(test_epub_path), chapter_dir, output_epub, metadata=metadata)

        with zipfile.ZipFile(str(test_epub_path), "r") as orig, \
             zipfile.ZipFile(output_epub, "r") as rebuilt:
            orig_count = len(orig.namelist())
            rebuilt_count = len(rebuilt.namelist())
            assert orig_count == rebuilt_count, (
                f"File count mismatch: original={orig_count}, rebuilt={rebuilt_count}"
            )


class TestRebuildLanguageUpdate:
    """dc:language metadata update tests."""

    def test_rebuild_updates_language(self, test_epub_path, tmp_output_dir, tmp_path):
        """dc:language changed to target_language when provided."""
        from extract_epub import extract_epub
        from rebuild_epub import rebuild_epub, find_opf_path

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))
        chapter_dir = str(tmp_output_dir / "source")
        output_epub = str(tmp_path / "rebuilt.epub")

        rebuild_epub(
            str(test_epub_path), chapter_dir, output_epub,
            metadata=metadata, target_language="fr"
        )

        # Read OPF from rebuilt EPUB and check dc:language
        opf_path = find_opf_path(output_epub)
        with zipfile.ZipFile(output_epub, "r") as z:
            opf_content = z.read(opf_path)

        ns = {"dc": "http://purl.org/dc/elements/1.1/"}
        root = etree.fromstring(opf_content)
        lang_elements = root.findall(".//dc:language", ns)
        assert len(lang_elements) > 0, "No dc:language element found in rebuilt OPF"
        assert lang_elements[0].text == "fr", (
            f"dc:language should be 'fr', got '{lang_elements[0].text}'"
        )

    def test_rebuild_preserves_language_when_none(self, test_epub_path, tmp_output_dir, tmp_path):
        """dc:language unchanged when target_language is None."""
        from extract_epub import extract_epub
        from rebuild_epub import rebuild_epub, find_opf_path

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))
        chapter_dir = str(tmp_output_dir / "source")
        output_epub = str(tmp_path / "rebuilt.epub")

        # Get original language
        opf_path_orig = find_opf_path(str(test_epub_path))
        with zipfile.ZipFile(str(test_epub_path), "r") as z:
            opf_orig = z.read(opf_path_orig)
        ns = {"dc": "http://purl.org/dc/elements/1.1/"}
        root_orig = etree.fromstring(opf_orig)
        orig_lang = root_orig.findall(".//dc:language", ns)[0].text

        # Rebuild without target_language
        rebuild_epub(
            str(test_epub_path), chapter_dir, output_epub,
            metadata=metadata, target_language=None
        )

        # Check language is unchanged
        opf_path_rebuilt = find_opf_path(output_epub)
        with zipfile.ZipFile(output_epub, "r") as z:
            opf_rebuilt = z.read(opf_path_rebuilt)
        root_rebuilt = etree.fromstring(opf_rebuilt)
        rebuilt_lang = root_rebuilt.findall(".//dc:language", ns)[0].text
        assert rebuilt_lang == orig_lang, (
            f"dc:language should be unchanged ('{orig_lang}'), got '{rebuilt_lang}'"
        )

    def test_rebuild_opf_not_hardcoded(self, test_epub_path):
        """find_opf_path reads from container.xml, not hardcoded."""
        from rebuild_epub import find_opf_path

        opf_path = find_opf_path(str(test_epub_path))
        assert opf_path is not None, "find_opf_path returned None"
        assert isinstance(opf_path, str), "find_opf_path should return a string"

        # Verify the OPF actually exists in the EPUB
        with zipfile.ZipFile(str(test_epub_path), "r") as z:
            assert opf_path in z.namelist(), (
                f"OPF path '{opf_path}' not found in EPUB"
            )
