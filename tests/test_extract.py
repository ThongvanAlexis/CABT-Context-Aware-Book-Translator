"""Comprehensive tests for EPUB chapter extraction.

Tests cover:
- DRM detection (real DRM vs font obfuscation vs clean EPUB)
- Chapter extraction from real test EPUB
- XHTML format preservation
- Metadata structure and content
- Front/back matter exclusion
- Multi-file chapter spanning detection
- Detection report generation
- Error handling
"""
import os
import re
import zipfile

import pytest


# ---------------------------------------------------------------------------
# Helper: create synthetic EPUB archives for DRM tests
# ---------------------------------------------------------------------------

MINIMAL_OPF = b"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
    <dc:language>en</dc:language>
    <dc:identifier id="uid">test-id-123</dc:identifier>
  </metadata>
  <manifest>
    <item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="ch1"/>
  </spine>
</package>"""

MINIMAL_CONTAINER_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

MINIMAL_XHTML = b"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Test</title></head>
<body><p>Test content.</p></body>
</html>"""


def _create_minimal_epub(path, extra_files=None):
    """Create a minimal valid EPUB ZIP for testing.

    Args:
        path: Where to write the ZIP file.
        extra_files: Dict of {filename: bytes} to add to the archive.
    """
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", MINIMAL_CONTAINER_XML)
        zf.writestr("content.opf", MINIMAL_OPF)
        zf.writestr("chapter1.xhtml", MINIMAL_XHTML)
        if extra_files:
            for name, content in extra_files.items():
                zf.writestr(name, content)


# ---------------------------------------------------------------------------
# DRM detection tests
# ---------------------------------------------------------------------------

class TestDrmDetection:
    """Tests for the check_drm function."""

    def test_drm_clean_epub(self, test_epub_path):
        """Non-DRM EPUB returns (False, None)."""
        from extract_epub import check_drm

        is_drm, message = check_drm(str(test_epub_path))
        assert is_drm is False
        assert message is None

    def test_drm_encryption_xml(self, tmp_path):
        """EPUB with encryption.xml containing DRM EncryptedData returns (True, message)."""
        from extract_epub import check_drm

        encryption_xml = b"""<?xml version="1.0" encoding="utf-8"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"
            xmlns:enc="http://www.w3.org/2001/04/xmlenc#">
  <enc:EncryptedData>
    <enc:EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes256-cbc"/>
    <enc:CipherData>
      <enc:CipherReference URI="chapter1.xhtml"/>
    </enc:CipherData>
  </enc:EncryptedData>
</encryption>"""

        epub_path = tmp_path / "drm_enc.epub"
        _create_minimal_epub(
            epub_path,
            extra_files={"META-INF/encryption.xml": encryption_xml},
        )

        is_drm, message = check_drm(str(epub_path))
        assert is_drm is True
        assert message is not None
        assert "DRM" in message or "drm" in message.lower() or "encrypt" in message.lower()

    def test_drm_rights_xml(self, tmp_path):
        """EPUB with rights.xml returns (True, message)."""
        from extract_epub import check_drm

        epub_path = tmp_path / "drm_rights.epub"
        _create_minimal_epub(
            epub_path,
            extra_files={"META-INF/rights.xml": b"<rights/>"},
        )

        is_drm, message = check_drm(str(epub_path))
        assert is_drm is True
        assert message is not None
        assert "rights" in message.lower() or "DRM" in message

    def test_drm_font_obfuscation_not_flagged(self, tmp_path):
        """Font-only encryption.xml returns (False, None) -- no false positive."""
        from extract_epub import check_drm

        encryption_xml = b"""<?xml version="1.0" encoding="utf-8"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"
            xmlns:enc="http://www.w3.org/2001/04/xmlenc#">
  <enc:EncryptedData>
    <enc:EncryptionMethod Algorithm="http://www.idpf.org/2008/embedding"/>
    <enc:CipherData>
      <enc:CipherReference URI="fonts/myfont.otf"/>
    </enc:CipherData>
  </enc:EncryptedData>
</encryption>"""

        epub_path = tmp_path / "font_obf.epub"
        _create_minimal_epub(
            epub_path,
            extra_files={"META-INF/encryption.xml": encryption_xml},
        )

        is_drm, message = check_drm(str(epub_path))
        assert is_drm is False
        assert message is None

    def test_drm_invalid_file(self, tmp_path):
        """Non-ZIP file returns (False, error_message)."""
        from extract_epub import check_drm

        bad_path = tmp_path / "not_an_epub.txt"
        bad_path.write_text("This is not a ZIP file")

        is_drm, message = check_drm(str(bad_path))
        assert is_drm is False
        assert message is not None  # Should have error message


# ---------------------------------------------------------------------------
# Chapter extraction tests (using real test EPUB)
# ---------------------------------------------------------------------------

class TestChapterExtraction:
    """Tests for extract_epub function using the real test EPUB."""

    def test_extract_creates_chapter_files(self, test_epub_path, tmp_output_dir):
        """extract_epub creates chapter-NN.xhtml files in source/ subdirectory."""
        from extract_epub import extract_epub

        extract_epub(str(test_epub_path), str(tmp_output_dir))

        source_dir = tmp_output_dir / "source"
        assert source_dir.is_dir()

        chapter_files = sorted(source_dir.glob("chapter-*.xhtml"))
        assert len(chapter_files) >= 5, (
            f"Expected at least 5 chapter files, got {len(chapter_files)}"
        )

    def test_extract_xhtml_preserves_formatting(self, test_epub_path, tmp_output_dir):
        """Extracted chapter files contain valid XHTML with head/link tags."""
        from extract_epub import extract_epub

        extract_epub(str(test_epub_path), str(tmp_output_dir))

        source_dir = tmp_output_dir / "source"
        chapter_file = source_dir / "chapter-01.xhtml"
        assert chapter_file.is_file()

        content = chapter_file.read_text(encoding="utf-8")

        # Verify XHTML structure is preserved
        assert content.startswith("<?xml") or content.startswith("<html") or content.startswith("<!DOCTYPE"), (
            f"Chapter file should start with XML declaration, html tag, or DOCTYPE. Got: {content[:100]}"
        )
        assert "<body" in content, "Chapter should contain <body> tag"
        assert "<p" in content, "Chapter should contain <p> tag"

        # Verify CSS links are preserved (not stripped by ebooklib)
        assert "<link" in content or "stylesheet" in content, (
            "Chapter should preserve CSS link references"
        )

    def test_extract_metadata_structure(self, test_epub_path, tmp_output_dir):
        """Returned metadata dict has required keys."""
        from extract_epub import extract_epub

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))

        assert "title" in metadata
        assert "source_language" in metadata
        assert "epub_path" in metadata
        assert "chapters" in metadata

        assert isinstance(metadata["title"], str)
        assert len(metadata["title"]) > 0
        assert isinstance(metadata["source_language"], str)
        assert isinstance(metadata["chapters"], list)
        assert len(metadata["chapters"]) > 0

    def test_extract_chapter_metadata_fields(self, test_epub_path, tmp_output_dir):
        """Each chapter in metadata has required fields."""
        from extract_epub import extract_epub

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))

        for ch in metadata["chapters"]:
            assert "sequence" in ch, "Chapter missing 'sequence'"
            assert "original_filename" in ch, "Chapter missing 'original_filename'"
            assert "output_filename" in ch, "Chapter missing 'output_filename'"
            assert "detected_title" in ch, "Chapter missing 'detected_title'"

            assert isinstance(ch["sequence"], int)
            assert isinstance(ch["original_filename"], str)
            assert re.match(r"chapter-\d{2}\.xhtml", ch["output_filename"]), (
                f"Output filename should match chapter-NN.xhtml, got {ch['output_filename']}"
            )
            assert isinstance(ch["detected_title"], str)

    def test_extract_sequential_numbering(self, test_epub_path, tmp_output_dir):
        """Output filenames are sequential: chapter-01, chapter-02, etc. with no gaps."""
        from extract_epub import extract_epub

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))

        for i, ch in enumerate(metadata["chapters"], 1):
            expected = f"chapter-{i:02d}.xhtml"
            assert ch["output_filename"] == expected, (
                f"Expected {expected}, got {ch['output_filename']}"
            )
            assert ch["sequence"] == i

    def test_extract_excludes_non_chapter_content(self, test_epub_path, tmp_output_dir):
        """Non-TOC spine items (front/back matter) are not extracted as chapters."""
        from extract_epub import extract_epub

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))

        # The test EPUB has 23 TOC entries and 28 spine items (including titlepage)
        # Front matter: titlepage.xhtml, part0000.html, part0001.html (TOC page)
        # Back matter: part0025.html
        # So chapter count should match TOC entry count (23), not spine count
        chapter_count = len(metadata["chapters"])
        assert chapter_count == 23, (
            f"Expected 23 chapters (matching TOC), got {chapter_count}"
        )

        # Verify no front matter files are included
        original_files = [ch["original_filename"] for ch in metadata["chapters"]]
        assert "titlepage.xhtml" not in original_files, "titlepage.xhtml should be excluded"
        assert "text/part0000.html" not in original_files, "part0000 (front matter) should be excluded"
        # part0001 is the TOC page -- it should not be extracted as a chapter
        # (though it's referenced by Chapter 1's TOC entry, the content goes to part0002)
        assert "text/part0025.html" not in original_files, "part0025 (back matter) should be excluded"

    def test_extract_detection_report(self, test_epub_path, tmp_output_dir):
        """detection_report.txt is written to output_dir after extraction."""
        from extract_epub import extract_epub

        extract_epub(str(test_epub_path), str(tmp_output_dir))

        report_path = tmp_output_dir / "detection_report.txt"
        assert report_path.is_file(), "detection_report.txt should be created"

        content = report_path.read_text(encoding="utf-8")
        assert "Chapter Detection Report" in content
        assert "chapter-01.xhtml" in content

    def test_extract_raises_on_drm(self, tmp_path):
        """extract_epub raises ValueError for DRM-protected EPUB."""
        from extract_epub import extract_epub

        encryption_xml = b"""<?xml version="1.0" encoding="utf-8"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"
            xmlns:enc="http://www.w3.org/2001/04/xmlenc#">
  <enc:EncryptedData>
    <enc:EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes256-cbc"/>
    <enc:CipherData>
      <enc:CipherReference URI="chapter1.xhtml"/>
    </enc:CipherData>
  </enc:EncryptedData>
</encryption>"""

        epub_path = tmp_path / "drm_test.epub"
        _create_minimal_epub(
            epub_path,
            extra_files={"META-INF/encryption.xml": encryption_xml},
        )

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with pytest.raises(ValueError):
            extract_epub(str(epub_path), str(output_dir))


# ---------------------------------------------------------------------------
# Non-standard structure tests
# ---------------------------------------------------------------------------

class TestNonstandardStructures:
    """Tests for handling non-standard EPUB chapter structures."""

    def test_extract_handles_multi_file_spanning(self, test_epub_path, tmp_output_dir):
        """Multi-file chapter spanning is detected and content files are extracted.

        The test EPUB has Chapter 1 with TOC pointing to part0001.html#_Toc64891124
        (the TOC page) while the actual chapter content is in part0002.html.
        """
        from extract_epub import extract_epub

        metadata = extract_epub(str(test_epub_path), str(tmp_output_dir))

        # Find chapter 1
        ch1 = metadata["chapters"][0]
        assert ch1["detected_title"] == "Chapter 1: May Cause Drowsiness"

        # Chapter 1 should be extracted from part0002.html (the content file)
        assert ch1["original_filename"] == "text/part0002.html", (
            f"Chapter 1 should come from part0002.html, got {ch1['original_filename']}"
        )

        # Detection notes should mention the multi-file spanning
        assert ch1["detection_notes"], "Chapter 1 should have detection notes about multi-file spanning"
        assert "part0001" in ch1["detection_notes"], (
            "Detection notes should reference part0001 (the TOC anchor file)"
        )

        # Verify the content file was actually written
        ch1_file = tmp_output_dir / "source" / "chapter-01.xhtml"
        assert ch1_file.is_file()
        content = ch1_file.read_text(encoding="utf-8")
        # The content should be substantial (part0002 is ~67K chars)
        assert len(content) > 1000, (
            f"Chapter 1 content seems too short ({len(content)} chars). "
            f"May have extracted the TOC page instead of content."
        )
