"""Build a synthetic test EPUB that matches the original test expectations.

Mirrors the structure of a real EPUB with:
- 23 chapters in TOC (matching test_extract_excludes_non_chapter_content)
- Multi-file chapter spanning: Ch1 TOC anchor in text/part0001.html#_Toc64891124,
  actual content in text/part0002.html (matching test_extract_handles_multi_file_spanning)
- Front matter: titlepage.xhtml, text/part0000.html (excluded from TOC)
- Back matter: text/part0025.html (excluded from TOC)
- CSS stylesheet link in every chapter
- Chapter 1 title: "Chapter 1: May Cause Drowsiness"
- Chapter 1 content > 1000 chars

Run directly to regenerate: python tests/data/build_test_epub.py
"""
import os
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "test-book.epub")

# -- Chapter titles (23 chapters) -------------------------------------------

CHAPTER_TITLES = [
    "Chapter 1: May Cause Drowsiness",
    "Chapter 2: Old Habits",
    "Chapter 3: The Wandering Market",
    "Chapter 4: First Blood",
    "Chapter 5: Echoes in the Dark",
    "Chapter 6: A Brief Respite",
    "Chapter 7: The Stitching",
    "Chapter 8: Survival Instinct",
    "Chapter 9: Rank and File",
    "Chapter 10: The Broker",
    "Chapter 11: What Lies Beneath",
    "Chapter 12: Dungeon Crawl",
    "Chapter 13: Boss Fight",
    "Chapter 14: Loot Distribution",
    "Chapter 15: New Skills",
    "Chapter 16: The Arena",
    "Chapter 17: Allies and Enemies",
    "Chapter 18: System Update",
    "Chapter 19: The Expedition",
    "Chapter 20: Ambush",
    "Chapter 21: Revelations",
    "Chapter 22: The War Council",
    "Chapter 23: Endgame",
]

STYLESHEET_CSS = """\
body { font-family: serif; margin: 1em; }
h1 { text-align: center; }
p { text-indent: 1.5em; margin: 0.3em 0; }
.system-notification { background: #eee; border: 1px solid #ccc; padding: 0.5em; }
"""

# -- XHTML templates ---------------------------------------------------------


def _make_xhtml(title, paragraphs, css_path="../Styles/stylesheet.css"):
    """Build XHTML with CSS link and body content."""
    body = "\n".join(f"    <p>{p}</p>" for p in paragraphs)
    css_link = (
        f'  <link rel="stylesheet" type="text/css" href="{css_path}"/>\n'
        if css_path else ""
    )
    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>{title}</title>
{css_link}</head>
<body>
  <h1>{title}</h1>
{body}
</body>
</html>"""


TITLEPAGE_XHTML = _make_xhtml("Title Page", [
    "Apocalypse: Generic System",
    "The Stitched Worlds Book 1",
    "by Test Author",
], css_path=None)

FRONT_MATTER_XHTML = _make_xhtml("Front Matter", [
    "Copyright 2024 Test Author. All rights reserved.",
    "This is a work of fiction.",
], css_path=None)

# TOC page -- Chapter 1's TOC entry points here with a fragment anchor
TOC_PAGE_XHTML = """\
<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Table of Contents</title></head>
<body>
  <h1>Table of Contents</h1>
  <ul>
    <li><a id="_Toc64891124" href="part0002.html">Chapter 1: May Cause Drowsiness</a></li>
    <li><a href="part0003.html">Chapter 2: Old Habits</a></li>
    <li><a href="part0004.html">Chapter 3: The Wandering Market</a></li>
  </ul>
</body>
</html>"""

BACKMATTER_XHTML = _make_xhtml("About the Author", [
    "Test Author writes LitRPG novels for automated testing.",
    "Visit testauthor.example.com for more information.",
], css_path=None)


# -- Chapter content generators -----------------------------------------------

def _make_chapter_paragraphs(chapter_num, title, min_length=0):
    """Generate paragraph content for a chapter. Ch1 gets extra content for the >1000 char test."""
    base = [
        f"This is the beginning of {title}.",
        "Marcus looked around the unfamiliar surroundings, trying to get his bearings.",
        "A translucent blue panel hovered before his face, glowing with soft light.",
        '<div class="system-notification"><strong>[System]</strong> Quest updated.</div>',
        "He took a deep breath and pressed forward into the unknown.",
        f"The events of {title.lower()} would change everything he thought he knew.",
    ]
    if min_length > 0:
        # Pad with extra paragraphs until we exceed min_length
        extra = [
            "The air was thick with the scent of ozone and something else — something ancient and powerful that Marcus could not quite identify.",
            "Shadows danced across the walls as torchlight flickered in the narrow corridor.",
            '"Stay alert," whispered Elara, her hand resting on the hilt of her enchanted dagger. "This place has claimed better adventurers than us."',
            "Marcus nodded, gripping his own weapon tighter. The <em>Blade of the Initiate</em> hummed softly in his hand, resonating with the ambient mana.",
            '<div class="system-notification"><strong>[System]</strong> Warning: You have entered a Level 15 Dungeon. Your current level: 7. Proceed with caution.</div>',
            "The notification sent a chill down his spine, but there was no turning back now. The entrance had sealed behind them with a grinding of ancient stone.",
            "They pressed deeper into the dungeon, passing carved reliefs that depicted battles from a forgotten age — heroes wielding powers that modern adventurers could only dream of.",
            '"Look at this," Elara said, pointing to an inscription. "It mentions the Stitching. The event that merged the worlds."',
            '"I thought that was just a legend," Marcus replied.',
            '"Everything is a legend until you see it with your own eyes." She traced the carved letters with her fingertip. "This dungeon predates the Stitching. It was here before our worlds collided."',
            "A sound echoed from deeper in the corridor — something between a growl and the scraping of metal on stone.",
            "They exchanged a glance and moved forward, weapons ready. Whatever awaited them, they would face it together.",
            "The corridor opened into a vast chamber, its ceiling lost in darkness above. Bioluminescent fungi clung to the walls, casting an eerie blue-green glow across the space.",
            "In the center of the chamber stood a pedestal, and upon it rested a crystal that pulsed with inner light.",
            "Marcus felt drawn to it, each step forward feeling both inevitable and dangerous.",
        ]
        base.extend(extra)
    return base


# -- OPF / NCX / container ---------------------------------------------------

CONTAINER_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""


def _build_opf():
    """Build content.opf with manifest and spine.

    Spine order (28 items):
      titlepage.xhtml, text/part0000.html, text/part0001.html,
      text/part0002.html .. text/part0024.html, text/part0025.html
    """
    manifest = [
        '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        '    <item id="css" href="Styles/stylesheet.css" media-type="text/css"/>',
        '    <item id="titlepage" href="titlepage.xhtml" media-type="application/xhtml+xml"/>',
    ]
    spine = [
        '    <itemref idref="titlepage"/>',
    ]

    # part0000 (front matter) through part0025 (back matter)
    for i in range(26):
        item_id = f"part{i:04d}"
        manifest.append(
            f'    <item id="{item_id}" href="text/part{i:04d}.html"'
            f' media-type="application/xhtml+xml"/>'
        )
        spine.append(f'    <itemref idref="{item_id}"/>')

    # Extra spine item for 28 total: a second back matter page
    manifest.append(
        '    <item id="part0026" href="text/part0026.html"'
        ' media-type="application/xhtml+xml"/>'
    )
    spine.append('    <itemref idref="part0026"/>')

    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Apocalypse: Generic System</dc:title>
    <dc:language>en</dc:language>
    <dc:identifier id="uid">test-book-uuid-001</dc:identifier>
    <dc:creator>Test Author</dc:creator>
  </metadata>
  <manifest>
{chr(10).join(manifest)}
  </manifest>
  <spine toc="ncx">
{chr(10).join(spine)}
  </spine>
</package>"""


def _build_ncx():
    """Build toc.ncx with 23 navPoints.

    Chapter 1 points to text/part0001.html#_Toc64891124 (triggers multi-file spanning).
    Chapters 2-23 point directly to text/part0003.html through text/part0024.html.
    """
    nav_points = []

    # Chapter 1 -- anchor in part0001 (TOC page), content in part0002
    nav_points.append(f"""\
    <navPoint id="navPoint-1" playOrder="1">
      <navLabel><text>{CHAPTER_TITLES[0]}</text></navLabel>
      <content src="text/part0001.html#_Toc64891124"/>
    </navPoint>""")

    # Chapters 2-23 -- direct references to part0003..part0024
    for i in range(1, 23):
        part_num = i + 2  # Ch2->part0003, Ch3->part0004, ..., Ch23->part0024
        nav_points.append(f"""\
    <navPoint id="navPoint-{i + 1}" playOrder="{i + 1}">
      <navLabel><text>{CHAPTER_TITLES[i]}</text></navLabel>
      <content src="text/part{part_num:04d}.html"/>
    </navPoint>""")

    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="test-book-uuid-001"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>Apocalypse: Generic System</text></docTitle>
  <navMap>
{chr(10).join(nav_points)}
  </navMap>
</ncx>"""


# -- Build the EPUB ----------------------------------------------------------

def build_epub():
    """Assemble all components into a valid EPUB ZIP file."""
    with zipfile.ZipFile(OUTPUT_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype must be first and uncompressed
        zf.writestr(
            "mimetype", "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )

        # META-INF
        zf.writestr("META-INF/container.xml", CONTAINER_XML)

        # OPF and NCX
        zf.writestr("content.opf", _build_opf())
        zf.writestr("toc.ncx", _build_ncx())

        # Stylesheet
        zf.writestr("Styles/stylesheet.css", STYLESHEET_CSS)

        # Front matter
        zf.writestr("titlepage.xhtml", TITLEPAGE_XHTML)
        zf.writestr("text/part0000.html", FRONT_MATTER_XHTML)

        # TOC page (part0001) -- Ch1 TOC anchor lives here
        zf.writestr("text/part0001.html", TOC_PAGE_XHTML)

        # Chapter 1 content (part0002) -- multi-file spanning target
        # Must be > 1000 chars for test assertion
        ch1_content = _make_xhtml(
            CHAPTER_TITLES[0],
            _make_chapter_paragraphs(1, CHAPTER_TITLES[0], min_length=1500),
        )
        zf.writestr("text/part0002.html", ch1_content)

        # Chapters 2-23 (part0003 through part0024)
        for i in range(1, 23):
            part_num = i + 2
            content = _make_xhtml(
                CHAPTER_TITLES[i],
                _make_chapter_paragraphs(i + 1, CHAPTER_TITLES[i]),
            )
            zf.writestr(f"text/part{part_num:04d}.html", content)

        # Back matter
        zf.writestr("text/part0025.html", BACKMATTER_XHTML)
        # Second back matter page (to reach 28 spine items)
        zf.writestr("text/part0026.html", _make_xhtml("Also By", [
            "Other books by Test Author:",
            "The Stitched Worlds Book 2: System Reboot",
        ], css_path=None))

    print(f"Built test EPUB: {OUTPUT_PATH}")
    print(f"  Title: Apocalypse: Generic System")
    print(f"  Chapters in TOC: {len(CHAPTER_TITLES)}")
    print(f"  Spine items: 28")
    print(f"  Multi-file spanning: Ch1 (TOC anchor in part0001.html, content in part0002.html)")
    print(f"  Front matter: titlepage.xhtml, text/part0000.html")
    print(f"  Back matter: text/part0025.html, text/part0026.html")


if __name__ == "__main__":
    build_epub()
