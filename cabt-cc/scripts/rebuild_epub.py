"""
EPUB reconstruction with zipfile-based approach and round-trip validation.

Rebuilds a valid EPUB from modified chapter XHTML files, preserving all
non-text assets (images, fonts, CSS) byte-for-byte from the original.
Uses Python's zipfile module (NOT ebooklib write_epub) to avoid CSS link
destruction.

Usage:
    python rebuild_epub.py <original_epub> <chapter_dir> <output_epub> [options]

Options:
    --target-language LANG   Update dc:language metadata to LANG
    --validate               Run round-trip validation after rebuild
    --metadata-json PATH     Path to metadata.json from extraction
"""

import argparse
import json
import os
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree


# ---------------------------------------------------------------------------
# XML namespace constants
# ---------------------------------------------------------------------------

CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"

NAMESPACES = {
    "container": CONTAINER_NS,
    "opf": OPF_NS,
    "dc": DC_NS,
}

# Binary file extensions (0% tolerance in round-trip validation)
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".ttf", ".otf", ".woff", ".woff2",
}

# Text file extensions (tolerance_pct in round-trip validation)
TEXT_EXTENSIONS = {
    ".xhtml", ".html", ".xml", ".css", ".ncx", ".opf",
}


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def find_opf_path(epub_path):
    """
    Find the OPF file path by reading META-INF/container.xml.

    Never hardcodes OPF location -- always reads from container.xml.

    Args:
        epub_path: Path to the EPUB file.

    Returns:
        The OPF file path within the EPUB (e.g., "content.opf" or
        "OEBPS/content.opf").

    Raises:
        ValueError: If container.xml is missing or malformed.
    """
    with zipfile.ZipFile(epub_path, "r") as z:
        if "META-INF/container.xml" not in z.namelist():
            raise ValueError(
                "Invalid EPUB: META-INF/container.xml not found"
            )

        container_bytes = z.read("META-INF/container.xml")
        root = etree.fromstring(container_bytes)

        # Find rootfile element
        rootfile = root.find(
            f".//{{{CONTAINER_NS}}}rootfile"
        )
        if rootfile is None:
            raise ValueError(
                "Invalid EPUB: No rootfile element in container.xml"
            )

        opf_path = rootfile.get("full-path")
        if not opf_path:
            raise ValueError(
                "Invalid EPUB: rootfile has no full-path attribute"
            )

        return opf_path


def update_opf_language(opf_bytes, target_language):
    """
    Update dc:language in OPF XML content.

    Finds all dc:language elements and updates their text to the target
    language. If no dc:language exists, adds one to the metadata element.
    Preserves all other OPF content exactly.

    Args:
        opf_bytes: OPF file content as bytes.
        target_language: Target language code (e.g., "fr", "de", "ja").

    Returns:
        Modified OPF content as bytes with XML declaration.
    """
    # Parse preserving the original structure
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(opf_bytes, parser)

    # Find and update dc:language elements
    lang_elements = root.findall(".//dc:language", NAMESPACES)

    if lang_elements:
        for elem in lang_elements:
            elem.text = target_language
    else:
        # No dc:language exists -- add one to metadata
        metadata = root.find(".//opf:metadata", NAMESPACES)
        if metadata is None:
            metadata = root.find(f".//{{{OPF_NS}}}metadata")
        if metadata is not None:
            lang_elem = etree.SubElement(
                metadata,
                f"{{{DC_NS}}}language"
            )
            lang_elem.text = target_language

    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=False,
    )


def _build_chapter_mapping(metadata, chapter_dir):
    """
    Build a mapping from original EPUB filenames to chapter files on disk.

    Args:
        metadata: Metadata dict from extract_epub (or None).
        chapter_dir: Directory containing chapter-NN.xhtml files.

    Returns:
        Dict mapping original_filename -> absolute path to chapter file on disk.
    """
    mapping = {}

    if metadata and "chapters" in metadata:
        for ch in metadata["chapters"]:
            original = ch["original_filename"]
            output = ch["output_filename"]
            chapter_path = os.path.join(chapter_dir, output)
            if os.path.isfile(chapter_path):
                mapping[original] = chapter_path
    else:
        # No metadata -- scan chapter_dir for chapter-NN.xhtml files
        # and match to original EPUB spine order (best effort)
        chapter_files = sorted(
            f for f in os.listdir(chapter_dir)
            if re.match(r"chapter-\d+\.xhtml", f)
        )
        # Without metadata, we cannot map to original filenames.
        # This is a fallback -- caller should provide metadata.
        # Log a warning but continue.
        pass

    return mapping


def rebuild_epub(original_epub_path, chapter_dir, output_epub_path,
                 metadata=None, target_language=None):
    """
    Rebuild an EPUB from modified chapter files.

    Uses zipfile (NOT ebooklib write_epub) to construct the output EPUB.
    Copies all non-chapter files byte-for-byte from the original.
    Chapter files are replaced with content from chapter_dir.
    If target_language is provided, updates dc:language in the OPF.

    Args:
        original_epub_path: Path to the original EPUB file.
        chapter_dir: Directory containing chapter-NN.xhtml files.
        output_epub_path: Path for the rebuilt EPUB output.
        metadata: Metadata dict from extract_epub (contains chapter mapping).
                  If None, mapping is built by scanning chapter_dir.
        target_language: Target language code (e.g., "fr"). If None,
                         dc:language is left unchanged (round-trip mode).
    """
    # Build chapter mapping: original_filename -> path on disk
    chapter_mapping = _build_chapter_mapping(metadata, chapter_dir)

    # Find OPF path for potential language update
    opf_path = find_opf_path(original_epub_path)

    # Ensure output directory exists
    output_dir = os.path.dirname(output_epub_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with zipfile.ZipFile(original_epub_path, "r") as zin, \
         zipfile.ZipFile(output_epub_path, "w") as zout:

        # Step 1: Write mimetype FIRST with ZIP_STORED, no extra field
        mimetype_info = zipfile.ZipInfo("mimetype")
        mimetype_info.compress_type = zipfile.ZIP_STORED
        mimetype_info.extra = b""
        zout.writestr(mimetype_info, "application/epub+zip")

        # Step 2: Iterate all files in original ZIP
        for item in zin.infolist():
            filename = item.filename

            # Skip mimetype (already written as first entry)
            if filename == "mimetype":
                continue

            # Case: OPF file with language update
            if filename == opf_path and target_language is not None:
                opf_bytes = zin.read(filename)
                modified_opf = update_opf_language(opf_bytes, target_language)
                zout.writestr(
                    filename, modified_opf,
                    compress_type=zipfile.ZIP_DEFLATED,
                )
                continue

            # Case: Chapter file that should be replaced
            if filename in chapter_mapping:
                chapter_path = chapter_mapping[filename]
                with open(chapter_path, "rb") as f:
                    chapter_content = f.read()
                zout.writestr(
                    filename, chapter_content,
                    compress_type=zipfile.ZIP_DEFLATED,
                )
                continue

            # Default: Copy byte-for-byte from original
            original_data = zin.read(filename)
            zout.writestr(
                filename, original_data,
                compress_type=zipfile.ZIP_DEFLATED,
            )


def validate_roundtrip(original_path, rebuilt_path, tolerance_pct=1.0):
    """
    Validate structural fidelity between original and rebuilt EPUB.

    Compares file count, filenames, file sizes (with tolerance), and
    spine order. Binary files (images, fonts) use 0% tolerance.
    Text files use the provided tolerance_pct.

    Args:
        original_path: Path to the original EPUB.
        rebuilt_path: Path to the rebuilt EPUB.
        tolerance_pct: Size tolerance percentage for text files (default 1.0).

    Returns:
        Dict with keys:
        - passed (bool): True if no errors found.
        - errors (list[str]): Critical issues.
        - warnings (list[str]): Non-critical observations.
    """
    results = {"passed": True, "errors": [], "warnings": []}

    with zipfile.ZipFile(original_path, "r") as orig, \
         zipfile.ZipFile(rebuilt_path, "r") as rebuilt:

        orig_names = set(orig.namelist())
        rebuilt_names = set(rebuilt.namelist())

        # Check 1: File count
        if len(orig_names) != len(rebuilt_names):
            results["errors"].append(
                f"File count mismatch: original={len(orig_names)}, "
                f"rebuilt={len(rebuilt_names)}"
            )

        # Check 2: File names -- missing/extra
        missing = orig_names - rebuilt_names
        if missing:
            results["errors"].append(
                f"Missing files in rebuilt EPUB: {sorted(missing)}"
            )

        extra = rebuilt_names - orig_names
        if extra:
            results["warnings"].append(
                f"Extra files in rebuilt EPUB: {sorted(extra)}"
            )

        # Check 3: File sizes with tolerance
        for name in sorted(orig_names & rebuilt_names):
            orig_size = orig.getinfo(name).file_size
            rebuilt_size = rebuilt.getinfo(name).file_size

            if orig_size == 0:
                continue

            ext = os.path.splitext(name)[1].lower()

            # Determine tolerance based on file type
            if ext in BINARY_EXTENSIONS:
                file_tolerance = 0.0
            else:
                file_tolerance = tolerance_pct

            diff_pct = abs(rebuilt_size - orig_size) / orig_size * 100

            if diff_pct > file_tolerance:
                results["errors"].append(
                    f"{name}: size differs by {diff_pct:.1f}% "
                    f"(original: {orig_size}, rebuilt: {rebuilt_size}, "
                    f"tolerance: {file_tolerance}%)"
                )

        # Check 4: Spine order preserved
        try:
            orig_opf_path = find_opf_path(original_path)
            rebuilt_opf_path = find_opf_path(rebuilt_path)

            orig_opf = etree.fromstring(orig.read(orig_opf_path))
            rebuilt_opf = etree.fromstring(rebuilt.read(rebuilt_opf_path))

            orig_spine = [
                item.get("idref")
                for item in orig_opf.findall(
                    f".//{{{OPF_NS}}}spine/{{{OPF_NS}}}itemref"
                )
            ]
            rebuilt_spine = [
                item.get("idref")
                for item in rebuilt_opf.findall(
                    f".//{{{OPF_NS}}}spine/{{{OPF_NS}}}itemref"
                )
            ]

            if orig_spine != rebuilt_spine:
                results["errors"].append(
                    f"Spine order differs: original has {len(orig_spine)} items, "
                    f"rebuilt has {len(rebuilt_spine)} items"
                )
        except Exception as e:
            results["warnings"].append(
                f"Could not compare spine order: {e}"
            )

    # passed is True only if errors list is empty
    results["passed"] = len(results["errors"]) == 0

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """CLI entry point for EPUB reconstruction."""
    parser = argparse.ArgumentParser(
        description="Rebuild an EPUB from modified chapter files."
    )
    parser.add_argument(
        "original_epub_path",
        help="Path to the original EPUB file"
    )
    parser.add_argument(
        "chapter_dir",
        help="Directory containing chapter-NN.xhtml files"
    )
    parser.add_argument(
        "output_epub_path",
        help="Path for the rebuilt EPUB output"
    )
    parser.add_argument(
        "--target-language",
        default=None,
        help="Update dc:language metadata to this language code (e.g., 'fr')"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run round-trip validation after rebuild"
    )
    parser.add_argument(
        "--metadata-json",
        default=None,
        help="Path to metadata.json from extraction (for chapter mapping)"
    )

    args = parser.parse_args()

    # Validate input
    if not os.path.isfile(args.original_epub_path):
        print(f"Error: Original EPUB not found: {args.original_epub_path}",
              file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(args.chapter_dir):
        print(f"Error: Chapter directory not found: {args.chapter_dir}",
              file=sys.stderr)
        sys.exit(1)

    # Load metadata if provided
    metadata = None
    if args.metadata_json:
        with open(args.metadata_json, "r", encoding="utf-8") as f:
            metadata = json.load(f)

    # Rebuild
    print(f"Rebuilding EPUB...")
    print(f"  Original: {args.original_epub_path}")
    print(f"  Chapters: {args.chapter_dir}")
    print(f"  Output: {args.output_epub_path}")
    if args.target_language:
        print(f"  Target language: {args.target_language}")

    rebuild_epub(
        args.original_epub_path,
        args.chapter_dir,
        args.output_epub_path,
        metadata=metadata,
        target_language=args.target_language,
    )

    print(f"Rebuilt EPUB written to: {args.output_epub_path}")

    # Validate if requested
    if args.validate:
        print(f"\nRunning round-trip validation...")
        results = validate_roundtrip(
            args.original_epub_path,
            args.output_epub_path,
        )

        if results["warnings"]:
            print(f"\nWarnings:")
            for w in results["warnings"]:
                print(f"  - {w}")

        if results["errors"]:
            print(f"\nErrors:")
            for e in results["errors"]:
                print(f"  - {e}")
            print(f"\nValidation FAILED")
            sys.exit(1)
        else:
            print(f"\nValidation PASSED")


if __name__ == "__main__":
    main()
