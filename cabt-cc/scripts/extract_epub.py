"""
EPUB chapter extraction with DRM detection and TOC-based chapter detection.

Extracts individual chapter XHTML files from an EPUB, preserving all formatting.
Supports both EPUB2 (NCX TOC) and EPUB3 (nav.xhtml TOC) via ebooklib's unified
TOC interface. Handles multi-file chapter spanning and excludes front/back matter.

Usage:
    python extract_epub.py <epub_path> <output_dir>
"""

import argparse
import json
import os
import posixpath
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

from ebooklib import epub
import ebooklib

from rebuild_epub import find_opf_path


# Font obfuscation algorithm URIs -- these are NOT DRM
FONT_OBFUSCATION_ALGORITHMS = {
    "http://www.idpf.org/2008/embedding",
    "http://ns.adobe.com/pdf/enc#RC",
}

# XML namespaces used in encryption.xml
ENC_NS = "http://www.w3.org/2001/04/xmlenc#"


def check_drm(epub_path):
    """
    Check if an EPUB file is DRM-protected.

    Inspects the ZIP archive for META-INF/encryption.xml and META-INF/rights.xml.
    Distinguishes real DRM encryption from font obfuscation (which is benign).

    Args:
        epub_path: Path to the EPUB file.

    Returns:
        Tuple of (is_drm: bool, message: str or None).
        - (False, None) for non-DRM EPUB.
        - (True, message) for DRM-protected EPUB.
        - (False, error_message) for invalid ZIP files.
    """
    try:
        with zipfile.ZipFile(epub_path, "r") as z:
            names = z.namelist()

            # Check for rights.xml -- always DRM
            if "META-INF/rights.xml" in names:
                return (
                    True,
                    "This EPUB contains DRM rights management "
                    "(META-INF/rights.xml found). "
                    "Please remove DRM protection before processing.",
                )

            # Check for encryption.xml -- may be DRM or just font obfuscation
            if "META-INF/encryption.xml" in names:
                enc_content = z.read("META-INF/encryption.xml")
                try:
                    root = etree.fromstring(enc_content)
                except etree.XMLSyntaxError:
                    # Malformed encryption.xml -- treat as suspicious
                    return (
                        True,
                        "This EPUB has a malformed META-INF/encryption.xml. "
                        "It may be DRM-protected. Please verify before processing.",
                    )

                # Find all EncryptedData elements
                encrypted_data_elements = root.findall(
                    f"{{{ENC_NS}}}EncryptedData"
                )

                for enc_data in encrypted_data_elements:
                    # Get the encryption method algorithm
                    enc_method = enc_data.find(f"{{{ENC_NS}}}EncryptionMethod")
                    if enc_method is not None:
                        algorithm = enc_method.get("Algorithm", "")
                        if algorithm not in FONT_OBFUSCATION_ALGORITHMS:
                            # This is real DRM, not just font obfuscation
                            return (
                                True,
                                "This EPUB appears to be DRM-protected "
                                "(META-INF/encryption.xml contains encrypted "
                                "content data). Please remove DRM protection "
                                "before processing. Tools like Calibre with "
                                "DeDRM plugin can help.",
                            )
                    else:
                        # EncryptedData without a known algorithm -- flag it
                        return (
                            True,
                            "This EPUB appears to be DRM-protected "
                            "(META-INF/encryption.xml contains encrypted data "
                            "with unknown method). Please remove DRM "
                            "protection before processing.",
                        )

            return (False, None)

    except zipfile.BadZipFile:
        return (False, "File is not a valid ZIP/EPUB archive.")
    except FileNotFoundError:
        return (False, f"File not found: {epub_path}")
    except Exception as e:
        return (False, f"Error reading file: {e}")


def _clean_toc_title(title):
    """
    Strip dot-leader artifacts from TOC titles.

    Some EPUBs embed trailing dots (e.g. "Chapter 1: Old Habits..........")
    as print-style dot leaders. This strips 3+ trailing dots.
    """
    if not title:
        return title
    return re.sub(r'\.{3,}\s*$', '', title).rstrip()


def _flatten_toc(toc_entries):
    """
    Flatten ebooklib's TOC structure into a list of (title, href) tuples.

    Handles both epub.Link entries and tuple (Section, [children]) entries
    that ebooklib uses for nested TOC structures.

    Args:
        toc_entries: book.toc from ebooklib.

    Returns:
        List of dicts with 'title' and 'href' keys.
    """
    result = []
    for entry in toc_entries:
        if isinstance(entry, epub.Link):
            title = _clean_toc_title(entry.title)
            result.append({"title": title, "href": entry.href})
        elif isinstance(entry, tuple):
            # (Section, [Link, Link, ...])
            section, children = entry
            # Include the section itself if it has an href
            if hasattr(section, "href") and section.href:
                title = _clean_toc_title(section.title)
                result.append({"title": title, "href": section.href})
            # Recursively flatten children
            result.extend(_flatten_toc(children))
    return result


def detect_chapters(book):
    """
    Detect chapter files from the EPUB's TOC and spine.

    Uses TOC as primary chapter source. Cross-references with spine to:
    - Identify front/back matter (in spine but not TOC) and exclude it
    - Handle multi-file chapters: when TOC entry points to file A#fragment
      and next spine file B has no TOC entry, file B is the chapter content

    Falls back to spine order when TOC is empty.

    Args:
        book: An ebooklib EpubBook object.

    Returns:
        List of chapter dicts with keys:
        - title: Chapter title from TOC
        - href: File path within EPUB (no fragment)
        - original_filename: Same as href
        - detection_notes: Any notes about detection (e.g., multi-file spanning)
    """
    toc_entries = _flatten_toc(book.toc)

    # Build spine ordered list of document files
    spine_files = []
    for item_id, _linear in book.spine:
        item = book.get_item_with_id(item_id)
        if item is not None:
            spine_files.append(item.get_name())

    # If TOC is degenerate (0 or 1 entries), fall back to spine
    if len(toc_entries) <= 1:
        # Pre-filter spine to XHTML/HTML content files only
        CONTENT_EXTENSIONS = {'.xhtml', '.html', '.htm', '.xml'}
        spine_files_filtered = [
            href for href in spine_files
            if Path(href).suffix.lower() in CONTENT_EXTENSIONS
        ]
        chapters = []
        for href in spine_files_filtered:
            chapters.append(
                {
                    "title": Path(href).stem,
                    "href": href,
                    "original_filename": href,
                    "detection_notes": "spine_fallback",
                }
            )
        return chapters

    # Build set of files referenced by TOC (strip fragments)
    toc_file_set = set()
    toc_entries_by_file = {}
    for entry in toc_entries:
        href_no_frag = entry["href"].split("#")[0]
        toc_file_set.add(href_no_frag)
        # Store the first TOC entry for each file
        if href_no_frag not in toc_entries_by_file:
            toc_entries_by_file[href_no_frag] = entry

    # Build set of non-TOC spine files (potential content continuations)
    non_toc_spine_files = set()
    for href in spine_files:
        if href not in toc_file_set:
            non_toc_spine_files.add(href)

    # Process TOC entries to build chapter list, handling multi-file spanning
    chapters = []
    for entry in toc_entries:
        href_full = entry["href"]
        href_no_frag = href_full.split("#")[0]
        has_fragment = "#" in href_full
        title = entry["title"]
        detection_notes = ""

        # Find position of this TOC file in spine
        if href_no_frag in spine_files:
            spine_idx = spine_files.index(href_no_frag)
        else:
            # TOC references a file not in spine -- use it directly
            chapters.append(
                {
                    "title": title,
                    "href": href_no_frag,
                    "original_filename": href_no_frag,
                    "detection_notes": "TOC file not found in spine",
                }
            )
            continue

        # Multi-file chapter detection:
        # When a TOC entry points to file A with a fragment, and the next
        # spine file B has no TOC entry, B is the actual chapter content.
        if has_fragment and (spine_idx + 1) < len(spine_files):
            next_spine_file = spine_files[spine_idx + 1]
            if next_spine_file in non_toc_spine_files:
                # The next file is the actual chapter content
                detection_notes = (
                    f"Content file (TOC anchor in {href_no_frag})"
                )
                chapters.append(
                    {
                        "title": title,
                        "href": next_spine_file,
                        "original_filename": next_spine_file,
                        "detection_notes": detection_notes,
                    }
                )
                # Remove from non-TOC set so it's not treated as back matter
                non_toc_spine_files.discard(next_spine_file)
                continue

        # Standard case: TOC file is the chapter content
        chapters.append(
            {
                "title": title,
                "href": href_no_frag,
                "original_filename": href_no_frag,
                "detection_notes": detection_notes,
            }
        )

    return chapters


def extract_epub(epub_path, output_dir):
    """
    Extract chapters from an EPUB into individual XHTML files.

    Reads the EPUB, detects chapters via TOC, and writes each chapter as
    chapter-NN.xhtml in output_dir/source/. Preserves original XHTML
    formatting by reading raw content from the ZIP file.

    Args:
        epub_path: Path to the EPUB file.
        output_dir: Directory to write extracted chapters to.

    Returns:
        Metadata dict with keys: title, source_language, epub_path, chapters.

    Raises:
        ValueError: If the EPUB is DRM-protected.
        FileNotFoundError: If the EPUB file doesn't exist.
    """
    epub_path = str(epub_path)

    # Step 1: DRM check
    is_drm, drm_msg = check_drm(epub_path)
    if is_drm:
        raise ValueError(drm_msg)

    # Step 2: Read EPUB with ebooklib
    book = epub.read_epub(epub_path)

    # Step 3: Extract metadata
    title_meta = book.get_metadata("DC", "title")
    title = title_meta[0][0] if title_meta else "Unknown"

    lang_meta = book.get_metadata("DC", "language")
    source_language = lang_meta[0][0] if lang_meta else "unknown"

    # Step 4: Detect chapters from TOC
    chapters = detect_chapters(book)

    # Step 5: Create output directory
    source_dir = os.path.join(output_dir, "source")
    os.makedirs(source_dir, exist_ok=True)

    # Resolve OPF base directory. ebooklib normalizes TOC/spine hrefs as
    # paths relative to the OPF; ZIP entries are absolute from the archive
    # root. When the OPF lives in a subdirectory (e.g. "OEBPS/content.opf"),
    # raw ZIP lookups must prepend that directory.
    opf_path = find_opf_path(epub_path)
    opf_dir = posixpath.dirname(opf_path)

    # Step 6: Extract chapter content from raw ZIP
    chapters_meta = []
    with zipfile.ZipFile(epub_path, "r") as z:
        zip_names = z.namelist()

        for i, ch in enumerate(chapters, 1):
            href = ch["href"]
            zip_path = posixpath.normpath(
                posixpath.join(opf_dir, href)
            ) if opf_dir else href

            # Read raw content from ZIP (preserves exact XHTML)
            if zip_path in zip_names:
                resolved_name = zip_path
                content = z.read(zip_path)
            else:
                # Try case-insensitive match
                matched = None
                for name in zip_names:
                    if name.lower() == zip_path.lower():
                        matched = name
                        break
                if matched:
                    resolved_name = matched
                    content = z.read(matched)
                    ch["detection_notes"] = (
                        (ch["detection_notes"] + "; " if ch["detection_notes"] else "")
                        + f"Case-insensitive match: {matched}"
                    )
                else:
                    ch["detection_notes"] = (
                        (ch["detection_notes"] + "; " if ch["detection_notes"] else "")
                        + f"WARNING: File not found in ZIP: {zip_path}"
                    )
                    continue

            # Write chapter file
            out_name = f"chapter-{i:02d}.xhtml"
            out_path = os.path.join(source_dir, out_name)
            with open(out_path, "wb") as f:
                f.write(content)

            # Store the resolved ZIP path as original_filename so
            # rebuild_epub can match it against ZIP entries.
            chapters_meta.append(
                {
                    "sequence": i,
                    "original_filename": resolved_name,
                    "output_filename": out_name,
                    "detected_title": ch["title"],
                    "detection_notes": ch["detection_notes"],
                }
            )

    # Step 7: Write detection report
    _write_detection_report(output_dir, title, chapters_meta)

    # Step 8: Build and return metadata
    metadata = {
        "title": title,
        "source_language": source_language,
        "epub_path": os.path.abspath(epub_path),
        "chapters": chapters_meta,
    }

    return metadata


def _write_detection_report(output_dir, title, chapters_meta, classification=None):
    """
    Write a detection_report.txt with chapter mapping details.

    When classification is None, writes the original single-table format
    (backward compatible). When classification is provided, writes a
    two-section format with kept/skipped entries and reasons.

    Args:
        output_dir: Directory to write the report to.
        title: Book title.
        chapters_meta: List of chapter metadata dicts.
        classification: Optional list of dicts with 'title', 'action',
            and 'reason' keys. Actions: 'translate', 'skip', 'uncertain'.
    """
    report_path = os.path.join(output_dir, "detection_report.txt")

    if classification is None:
        # Original single-table format (backward compatible)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"EPUB Chapter Detection Report\n")
            f.write(f"{'=' * 60}\n\n")
            f.write(f"Book Title: {title}\n")
            f.write(f"Chapters Detected: {len(chapters_meta)}\n\n")
            f.write(f"{'─' * 60}\n")
            f.write(f"{'Seq':<5} {'Output File':<22} {'Original File':<30} {'Title'}\n")
            f.write(f"{'─' * 60}\n")

            for ch in chapters_meta:
                f.write(
                    f"{ch['sequence']:<5} "
                    f"{ch['output_filename']:<22} "
                    f"{ch['original_filename']:<30} "
                    f"{ch['detected_title']}\n"
                )
                if ch["detection_notes"]:
                    f.write(f"      Notes: {ch['detection_notes']}\n")

            f.write(f"\n{'─' * 60}\n")
            f.write(f"End of report\n")
        return

    # Two-section format with classification results
    # Build a lookup from title to classification entry
    class_by_title = {}
    for entry in classification:
        class_by_title[entry["title"]] = entry

    # Determine translation mode from detection_notes
    has_spine = any(
        "spine_fallback" in (ch.get("detection_notes", "") or "")
        for ch in chapters_meta
    )
    translation_mode = "files_from_spine" if has_spine else "chapters_from_toc"

    # Separate into kept (translate/uncertain) and skipped
    kept = []
    skipped = []
    for ch in chapters_meta:
        cls = class_by_title.get(ch["detected_title"], {})
        action = cls.get("action", "translate")
        reason = cls.get("reason", "")
        entry = {**ch, "_action": action, "_reason": reason}
        if action == "skip":
            skipped.append(entry)
        else:
            kept.append(entry)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"EPUB Chapter Detection Report\n")
        f.write(f"{'=' * 60}\n\n")
        f.write(f"Book Title: {title}\n")
        f.write(f"Translation Mode: {translation_mode}\n")
        f.write(f"Chapters to Translate: {len(kept)}\n")
        f.write(f"Skipped Entries: {len(skipped)}\n\n")

        f.write(f"{'─' * 60}\n")
        f.write(f"CHAPTERS TO TRANSLATE\n")
        f.write(f"{'─' * 60}\n")
        for i, entry in enumerate(kept, 1):
            uncertain = " (?)" if entry["_action"] == "uncertain" else ""
            reason_str = f" -- {entry['_action']}: {entry['_reason']}" if entry["_reason"] else ""
            f.write(
                f"{i}. {entry['output_filename']}"
                f' -- "{entry["detected_title"]}"'
                f"{reason_str}{uncertain}\n"
            )

        f.write(f"\n{'─' * 60}\n")
        f.write(f"SKIPPED ENTRIES\n")
        f.write(f"{'─' * 60}\n")
        if skipped:
            for entry in skipped:
                reason_str = f" -- skip: {entry['_reason']}" if entry["_reason"] else " -- skip"
                f.write(
                    f"- {entry['output_filename']}"
                    f' -- "{entry["detected_title"]}"'
                    f"{reason_str}\n"
                )
        else:
            f.write("(none)\n")

        f.write(f"\n{'─' * 60}\n")
        f.write(f"End of report\n")


def main():
    """CLI entry point for EPUB extraction."""
    parser = argparse.ArgumentParser(
        description="Extract chapters from an EPUB file into individual XHTML files."
    )
    parser.add_argument("epub_path", help="Path to the EPUB file")
    parser.add_argument("output_dir", help="Directory to write extracted chapters to")
    args = parser.parse_args()

    # Validate input
    if not os.path.isfile(args.epub_path):
        print(f"Error: File not found: {args.epub_path}", file=sys.stderr)
        sys.exit(1)

    # Extract
    try:
        metadata = extract_epub(args.epub_path, args.output_dir)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Write metadata.json
    meta_path = os.path.join(args.output_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"Extracted: {metadata['title']}")
    print(f"Language: {metadata['source_language']}")
    print(f"Chapters: {len(metadata['chapters'])}")
    print(f"Output: {os.path.abspath(args.output_dir)}/source/")
    print(f"Metadata: {meta_path}")
    print(f"Report: {os.path.join(args.output_dir, 'detection_report.txt')}")


if __name__ == "__main__":
    main()
