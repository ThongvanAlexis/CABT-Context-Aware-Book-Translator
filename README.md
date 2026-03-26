# CABT -- Context Aware Book Translator

> **Disclaimer:** This tool is intended for personal use — translating books you own for your own reading. It is not designed for distributing, selling, or publicly sharing translated works. Please respect copyright law and the rights of authors and publishers.

A Claude Code plugin that translates EPUB books with genre-aware glossary consistency. CABT extracts chapters from an EPUB, builds a terminology glossary chapter-by-chapter, then translates all chapters in parallel with guaranteed term consistency. Every term is translated the same way throughout the entire book, respecting genre conventions and the author's voice.

During Translation one subagent is spawned per chapter and the glossary and translation rules are put back at the top of its context, ensuring that you don't have inconsistent terminology accross chapters.

## Why?

I read so many English books that I now have more English vocabulary than I do in my native tongue. I wanted to read back in French, but nobody is publishing translations of the books I read T_T.
So I wrote these 3 skills. It takes around 40 minutes to build the glossary and about 1h20 to translate a book — it's really good.
After translating a book I had already read, I re-read the translated version and at no point did I find issues with the translation. The glossary really does provide consistency for specific terms used across a series.

## Features

- **Genre-aware glossary system** -- specialized terminology handling for LitRPG, Fantasy, Sci-Fi, and General fiction
- **Sequential glossary building** -- chapter-by-chapter term accumulation ensures comprehensive coverage
- **Parallel translation** -- chapters translated simultaneously in batches of 8 for speed
- **Glossary enforcement** -- every translated chapter uses the exact same term translations
- **XHTML formatting preservation** -- italics, bold, system notifications, tables, and all original formatting survive translation
- **EPUB-in, EPUB-out** -- no manual file handling; give it an EPUB, get a translated EPUB back
- **Checkpoint and resume** -- both glossary building and translation can be interrupted and resumed
- **Interactive translation philosophy** -- Q&A sessions establish translation rules and style before any translation begins
- **Series translation support** -- reuse glossary, translation rules, and style brief from a previous book's workspace; Q&A adapts to only surface differences
- **Timestamped workspaces** -- folders prefixed with `yyyymmdd_hhmm_` for chronological sorting and uniqueness

## Requirements

if you don't have them claude code will install them from you himself, in your global interpreter once he notices they are missing.

- **Claude model:** tested with `claude-opus-4-6[1M]`. Those skills relies on Opus's ability to preserve XML tokens faithfully during translation. Future model updates may affect translation quality or skill compatibility — run a few test chapters before committing to a full book translation.
- **Python 3** with the following packages:
  - `ebooklib` (>= 0.18)
  - `lxml` (>= 4.0)
  - `tiktoken` (>= 0.5)
- **Claude Code** -- download from [https://claude.com/download](https://claude.com/download)

Install Python dependencies:

```
pip install ebooklib lxml tiktoken
```

## Installation

1. **Clone the repository:**
   
   ```
   git clone https://github.com/ThongvanAlexis/CABT-Context-Aware-Book-Translator.githttps://github.com/ThongvanAlexis/CABT-Context-Aware-Book-Translator.git
   ```

2. **Install Python dependencies:**
   
   ```
   pip install ebooklib lxml tiktoken
   ```

3. **Register the plugin in Claude Code:**
   
   Run these two commands inside Claude Code, replacing the path with wherever you cloned the repo:
   
   ```
   /plugin marketplace add /path/to/CABT-Context-Aware-Book-Translator
   /plugin install cabt@cabt
   ```

4. **Restart Claude Code** to pick up the new plugin.

## Workflow -- The Three Commands

CABT uses a three-command pipeline. Each command builds on the output of the previous one.

### 1. `/prepare-book`

Extracts chapters from an EPUB and creates a translation workspace.

```
/prepare-book path/to/book.epub
```

**What it asks:**

- Genre (LitRPG, Fantasy, Sci-Fi, or General)
- Source language (e.g., English)
- Target language (e.g., French)
- Whether to reuse glossary and translation style from a previous book's workspace (for series)

**What it produces:**

- A timestamped workspace directory (e.g., `20260324_1902_Book-Title`) containing:
  - `source/` -- extracted chapter XHTML files
  - `metadata.json` -- book configuration and processing state
  - `test-roundtrip.epub` -- validation copy to verify extraction quality
  - `detection_report.txt` -- chapter detection details
  - If reusing: `glossary.md`, `glossary-rules.md`, and `translation-style-brief.md` copied from the previous workspace (glossary stripped of context references)

### 2. `/build-book-glossary`

Researches the book online, then processes chapters sequentially to build a terminology glossary.

```
/build-book-glossary workspace-path
```

**What it does:**

- Searches the web for book context, fan translations, and terminology conventions
- Asks 6-10 genre-specific translation philosophy questions (proper nouns, genre terms, speech register, onomatopoeia, cultural adaptations)
- Processes each chapter with a dedicated agent that sees all previously accumulated terms
- Each agent extracts new terms and proposes translations
- **Series mode:** when a seeded glossary/rules exist from a previous workspace, the Q&A adapts to only surface tone/register differences rather than asking everything from scratch

**What it produces:**

- `glossary.md` -- categorized terminology with source terms, translations, and context
- `glossary-rules.md` -- translation philosophy decisions from the Q&A session

**After completion:** Review `glossary.md` and fix any entries marked with `(?)` before translating. These are terms where the agent was uncertain about the best translation.

### 3. `/translate-book`

Translates all chapters in parallel with glossary enforcement, then rebuilds the EPUB.

```
/translate-book workspace-path
```

**What it asks:**

- 3-4 translation style questions (sentence structure fidelity, humor handling, reading level, cultural references)
- **Series mode:** when a style brief exists from a previous workspace, it reuses or discusses changes rather than starting fresh

**What it does:**

- Tokenizes XHTML formatting into XML-style tokens to protect it during translation
- Translates all chapters in parallel (batches of 8 agents) with strict glossary enforcement
- Validates XHTML token integrity after each translation
- Detokenizes translated text back to proper XHTML
- Rebuilds the final translated EPUB with all original assets (images, fonts, CSS)

**What it produces:**

- `{book-title}-{language}.epub` -- the translated EPUB
- `output/{language}/translator-notes/` -- per-chapter translation decisions and flagged passages
- `output/{language}/new-terms.md` -- terms discovered during translation that were not in the glossary

## Example

### First book

```
/prepare-book my-novel.epub
```

When prompted, select a genre (e.g., LitRPG), source language (English), and target language (French). Say "no" to reuse. This creates a timestamped workspace like `20260324_1902_My-Novel`.

```
/build-book-glossary 20260324_1902_My-Novel
```

Answer the translation philosophy questions, then review `glossary.md` -- fix any entries marked with `(?)`.

```
/translate-book 20260324_1902_My-Novel
```

Answer the style brief questions, wait for parallel translation, and find the translated EPUB at `My-Novel-french.epub`. Check `output/french/translator-notes/` for per-chapter decisions and `output/french/new-terms.md` for terms discovered during translation.

### Series -- translating book 2

```
/prepare-book my-novel-book-2.epub
```

Say "yes" to reuse and provide the path to the first book's workspace (`20260324_1902_My-Novel`). Genre and language are inherited automatically. Glossary, rules, and style brief are copied into the new workspace.

```
/build-book-glossary 20260325_0930_My-Novel-Book-2
```

The Q&A adapts -- only tone/register differences from the previous book are surfaced. Existing terms carry forward and new terms are added on top.

```
/translate-book 20260325_0930_My-Novel-Book-2
```

The existing style brief is reused. Only changes in the new book's style are discussed.

## Supported Genres

| Genre       | Specialization                                                                                     |
| ----------- | -------------------------------------------------------------------------------------------------- |
| **LitRPG**  | Stats, skills, system notifications, level-ups, game mechanics, party roles (Tank/Healer/DPS)      |
| **Fantasy** | Magic systems, fantasy races, nobility titles, medieval and epic settings, spells and incantations |
| **Sci-Fi**  | Technology terms, spaceships, military hierarchies, futuristic settings, scientific jargon         |
| **General** | Simplified terminology categories for books outside the above genres                               |

## How It Works

- **Python scripts for all deterministic tasks** -- every non-creative operation (EPUB extraction, tokenization, detokenization, EPUB reconstruction, validation, checkpoint management) is handled by Python scripts rather than LLM prompts, minimizing token usage and eliminating hallucination risks on tasks that don't require intelligence
- **EPUB extraction** preserves exact XHTML structure using raw ZIP access (not ebooklib's writer, which can destroy CSS links)
- **Glossary building** is sequential so each chapter agent sees all prior terms, ensuring consistent terminology accumulation
- **Translation** uses XML-style tokens (e.g., `<em:1>`, `</strong:2>`) to protect XHTML formatting during LLM translation -- the LLM translates text while preserving tokens in place
- **EPUB reconstruction** maintains all original assets (images, fonts, CSS, metadata) and replaces only the translated chapter content
- **Round-trip validation** ensures extraction fidelity before any translation begins

## Tips

- **Glossary building is sequential** (takes longer per chapter) but **translation is parallel** (fast). For a 30-chapter book, expect glossary building to take significantly longer than translation.
- For large books, set `CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000` in your shell profile (`.bashrc`, `.zshrc`, or PowerShell profile) to avoid output truncation on long chapters.
- The round-trip test EPUB (`test-roundtrip.epub`) is kept in the workspace until translation starts. Open it in an e-reader to verify extraction quality before committing to the full pipeline.
- If translation is interrupted, re-run `/translate-book` on the same workspace to resume from where it stopped. Already-translated chapters are skipped.
- After translation, new terms discovered during translation are automatically merged back into `glossary.md` for consistency in future books of the same series.
- **For series:** always reuse from the most recently translated book's workspace to get the most complete glossary. Workspaces are timestamped so they sort chronologically.
