---
name: prepare-book
version: 1.2.2
description: Interactively set up a translation workspace from an EPUB file
argument-hint: <path-to-epub>
allowed-tools: [Read, Write, Bash, Glob, Grep]
---

# CABT Prepare Book

Interactively collect book configuration from the user, extract chapters from an EPUB file, validate round-trip fidelity, and create a complete translation workspace.

## Workflow

### Step 0: Version Check

Print the version on every run:

```
cabt:prepare-book v1.2.2
```

Then check if `$ARGUMENTS` contains `--version`. If it does, stop here -- do not proceed to Step 1 or any further steps.

### Step 1: Collect Configuration

Collect all configuration from the user before starting extraction.

1. **EPUB path** -- If an EPUB path was provided as `$ARGUMENTS`, use it. Otherwise ask the user: "What is the path to your EPUB file?"

   After obtaining the path, verify the file exists:
   ```bash
   test -f "<epub_path>" && echo "File found" || echo "File not found"
   ```
   If the file does not exist, tell the user the path was not found and ask them to check it.

2. **Reuse question** -- After the EPUB path is confirmed, ask the user:

   > "Would you like to reuse glossary and translation style from a previous book's workspace? (yes/no)"

3. **If user says YES (reuse path):**

   a. Ask: "What is the path to the previous book's workspace folder?"

   b. Validate the previous workspace:
   ```bash
   test -f "<previous_workspace_path>/metadata.json" && echo "Valid workspace" || echo "Not a valid workspace"
   ```

   c. If not valid: tell the user "That path does not contain a valid CABT workspace (no metadata.json found). Please check the path." Then ask for the path again.

   d. If valid: read the previous workspace's metadata.json:
   ```bash
   cat "<previous_workspace_path>/metadata.json"
   ```

   e. Extract `source_language`, `target_language`, `genre`, and `title` from the previous metadata.

   f. Display to user:
   ```
   Loaded configuration from previous workspace:
     Previous book:     <title>
     Genre:             <genre>
     Source language:    <source_language>
     Target language:    <target_language>
   ```

   g. Use these values for workspace creation. Do NOT ask the genre, source language, or target language questions -- they are inherited from the previous workspace.

   h. Set `reuse_from` to the previous workspace path (used in Step 2.5).

4. **If user says NO (fresh path):**

   a. **Genre** -- Present the following options and ask the user to choose one:

      - **LitRPG** -- Books with stats, skills, system notifications, level-ups, and game mechanics
      - **Fantasy** -- Books with magic systems, fantasy races, nobility, and medieval/epic settings
      - **Sci-Fi** -- Books with technology, spaceships, military hierarchies, and futuristic settings
      - **General** -- Books that don't fit the above categories; uses simplified terminology categories

   b. **Source language** -- Ask the user: "What is the source language of this book?" (e.g., English, Japanese, Korean)

   c. **Target language** -- Ask the user: "What language should the book be translated to?" (e.g., French, Spanish, German)

   d. Set `reuse_from` to null (Step 2.5 will be skipped).

### Step 2: Create Workspace

Run the workspace preparation script with all collected information (genre, source language, and target language come from either reuse or fresh input):

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/prepare_workspace.py "<epub_path>" --genre "<genre>" --source-language "<source_lang>" --target-language "<target_lang>"
```

If the script exits with an error, show the error message to the user and stop. Do not attempt to retry or work around the error.

Parse the JSON output from stdout on success. The output contains `workspace_path`, `title`, and `chapter_count`.

### Step 2.5: Import Reuse Files

**Only run this step if `reuse_from` is set** (user chose to reuse from a previous workspace in Step 1). If `reuse_from` is null, skip to Step 3.

Run the reuse workspace script:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/reuse_workspace.py --source-workspace "<reuse_from>" --target-workspace "<workspace_path>"
```

Where `<workspace_path>` is the `workspace_path` from Step 2's JSON output.

If the script exits with an error, show the error message to the user and stop. Do not attempt to retry or work around the error.

Parse the JSON output from stdout on success. Report to the user:

```
Imported from previous workspace:
  Glossary:                <"Imported (chapter references cleaned)" if had_glossary else "Not found in previous workspace">
  Translation rules:       <"Imported" if had_rules else "Not found in previous workspace">
  Translation style brief: <"Imported" if had_brief else "Not found in previous workspace">
```

### Step 2.7: Classify Chapters

After workspace creation (and optional reuse import), classify which extracted entries are translatable content and which should be skipped. This step always runs regardless of whether reuse was used.

**Sub-step 1: Extract snippets**

Run the snippet extractor to get chapter data for classification:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/extract_snippets.py "<workspace_path>"
```

Parse the JSON output. Each entry has: `sequence`, `output_filename`, `detected_title`, `snippet` (first 500 chars of text content), `snippet_end` (last 200 chars of text content), and `detection_notes`.

**Sub-step 2: Display detection path**

Read `translation_mode` from `metadata.json` in the workspace. Display the detection path to the user:

- If `chapters_from_toc`:
  ```
  Detected N chapters from Table of Contents.
  Running table of contents classification via LLM...
  ```
- If `files_from_spine`:
  ```
  Bad table of contents (absent or only 1 entry) -- switching to LLM chapter detection.
  Extracted N files from EPUB spine. Classifying via LLM...
  ```

Where N is the number of entries from the snippets output.

**Sub-step 3: Classify entries**

You (the LLM executing this skill) are the classifier. Look at ALL entries together as a batch -- cross-entry context matters. For each entry, consider the `detected_title`, `snippet` (beginning of file), and `snippet_end` (end of file), then decide:

- **translate** -- actual content to translate (chapters, prologues, epilogues, interludes, appendices, author's notes, afterwords, game manuals, story content)
- **skip** -- non-content that should not be translated (copyright, dedication, about the author, newsletter signup, promotional pages, table of contents page, title page, also-by lists)
- **uncertain** -- cannot confidently classify from title and snippets alone

**IMPORTANT — mixed content files:** A single HTML file may contain non-content (e.g., promotional blurb, legal notice) mixed with actual story/chapter text. If either `snippet` or `snippet_end` contains what looks like narrative or chapter content, classify as **translate** — the story content takes priority over any surrounding non-content.

**Sub-step 4: Build classification result**

Build a JSON array of objects, one per entry in the same order as the snippets array. Each object has:
- `title` -- the `detected_title` from the snippet
- `action` -- one of "translate", "skip", or "uncertain"
- `reason` -- short explanation (e.g., "story content", "copyright page", "unclear from title alone")

**Sub-step 5: Present classification to user**

Display the classification in two sections:

```
CHAPTERS TO TRANSLATE (N):
  1. chapter-01.xhtml -- "Chapter 1: The Beginning" -- translate: story content
  2. chapter-02.xhtml -- "Interlude" -- uncertain: unclear from title alone (?)
  ...

SKIPPED ENTRIES (N):
  - chapter-15.xhtml -- "Copyright" -- skip: copyright page
  - chapter-16.xhtml -- "Also By" -- skip: promotional content
  ...
```

Rules:
- CHAPTERS TO TRANSLATE includes entries with action "translate" or "uncertain"
- Uncertain entries get `(?)` appended at the end
- SKIPPED ENTRIES includes entries with action "skip"
- Each line format: `output_filename -- "detected_title" -- action: reason`

**Sub-step 6: Ask for confirmation**

Ask the user:

> "Does this classification look correct? (yes / adjust)"

**Sub-step 7: Handle adjustment (if user says "adjust")**

If the user wants to adjust:

1. Display a full numbered list of ALL entries (both kept and skipped) with their current action in brackets. For example:
   ```
   1. chapter-01.xhtml -- "Chapter 1" [translate]
   2. chapter-02.xhtml -- "Copyright" [skip]
   3. chapter-03.xhtml -- "Interlude" [uncertain]
   ```

2. Ask: "Enter the numbers of entries to flip (comma-separated):"

3. Flip logic:
   - translate -> skip
   - skip -> translate
   - uncertain -> translate

4. Redisplay the two-section view (Sub-step 5 format) with updated classifications.

5. Ask for confirmation again (Sub-step 6). Repeat until the user approves.

**Sub-step 8: Update metadata.json**

After the user approves the classification, update the workspace by running this Python script via Bash. Replace `<workspace_path>` with the actual workspace path and `<classification_json>` with the JSON-encoded classification array (the result from Sub-step 4, with any adjustments from Sub-step 7 applied).

```bash
python -c "
import json, os, shutil

workspace = '<workspace_path>'
classification = json.loads('<classification_json>')

# Load metadata
meta_path = os.path.join(workspace, 'metadata.json')
with open(meta_path, 'r', encoding='utf-8') as f:
    metadata = json.load(f)

# Build classification lookup by title
class_by_title = {}
for entry in classification:
    class_by_title[entry['title']] = entry['action']

# Separate kept and skipped chapters
kept = []
for ch in metadata['chapters']:
    action = class_by_title.get(ch['detected_title'], 'translate')
    if action != 'skip':
        kept.append(ch)

source_dir = os.path.join(workspace, 'source')

# Two-pass rename to avoid collisions
# Pass 1: rename kept files to temporary names
for i, ch in enumerate(kept, 1):
    old_path = os.path.join(source_dir, ch['output_filename'])
    tmp_name = f'_tmp_{i:02d}.xhtml'
    tmp_path = os.path.join(source_dir, tmp_name)
    if os.path.isfile(old_path):
        shutil.move(old_path, tmp_path)
    ch['_tmp_name'] = tmp_name

# Pass 2: rename temp files to final sequential names
for i, ch in enumerate(kept, 1):
    tmp_path = os.path.join(source_dir, ch['_tmp_name'])
    new_name = f'chapter-{i:02d}.xhtml'
    new_path = os.path.join(source_dir, new_name)
    if os.path.isfile(tmp_path):
        shutil.move(tmp_path, new_path)
    ch['sequence'] = i
    ch['output_filename'] = new_name
    del ch['_tmp_name']

# Recalculate total tokens
total_tokens = sum(ch.get('token_count', 0) for ch in kept)

# Update metadata
metadata['chapters'] = kept
metadata['total_tokens'] = total_tokens

with open(meta_path, 'w', encoding='utf-8') as f:
    json.dump(metadata, f, indent=2, ensure_ascii=False)

print(f'Updated metadata.json: {len(kept)} chapters kept, renumbered 1..{len(kept)}')
print(f'Total tokens: {total_tokens}')
"
```

**IMPORTANT:** When constructing the `<classification_json>` string for the Python script, escape any single quotes in titles by replacing `'` with `'"'"'` so the shell command does not break. Alternatively, write the classification JSON to a temporary file and read it from Python.

**Sub-step 9: Regenerate detection report**

Regenerate `detection_report.txt` with the final two-section classification format by calling `_write_detection_report` from `extract_epub.py`.

**IMPORTANT:** Since Sub-step 8 already removed skipped entries from `metadata.json`, the report needs the ORIGINAL chapter list (before filtering) so it can show both kept and skipped sections. Save the original chapters list before Sub-step 8 runs, and use it here.

Replace `<workspace_path>`, `<original_chapters_json>` (ALL chapters from before Sub-step 8), and `<classification_json>` (the final classification array with any user adjustments):

```bash
python -c "
import json, sys
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
from extract_epub import _write_detection_report

workspace = '<workspace_path>'

# original_chapters contains ALL chapters (before skip removal in Sub-step 8)
original_chapters = json.loads('<original_chapters_json>')
classification = json.loads('<classification_json>')

# Read metadata just for the title
meta_path = workspace + '/metadata.json'
with open(meta_path, 'r', encoding='utf-8') as f:
    metadata = json.load(f)

_write_detection_report(workspace, metadata['title'], original_chapters, classification=classification)
print('detection_report.txt regenerated with classification')
"
```

**Sub-step 10:** Proceed to Step 3.

### Step 3: Report Results

Show a summary of the prepared workspace:

```
Workspace Ready!

  Book title:         <title from JSON output>
  Genre:              <selected genre>
  Source language:     <source language>
  Target language:     <target language>
  Chapters detected:  <total entries from extract_snippets> (from <TOC|spine>)
  Chapters to translate: <count of kept chapters after classification>
  Entries skipped:     <count of skipped entries after classification>
  Workspace path:     <workspace_path from JSON output>
  Round-trip test:     Passed
```

Where `(from TOC)` or `(from spine)` reflects the `translation_mode` from metadata.json.

If reuse was used (i.e., `reuse_from` is set), add one more line after the summary block:

```
  Reused from:        <previous_workspace_path>
```

Then print:

```
Review the detection_report.txt to see which chapters will be translated and which were skipped.

---
Next step: /build-book-glossary {workspace_path}
```

Where `{workspace_path}` is the actual `workspace_path` value from the JSON output in Step 2.

**IMPORTANT:** Print the command exactly as `/build-book-glossary`, NOT `/cabt:build-book-glossary`. Do NOT add a namespace prefix. The short form is required for autocomplete to work.

## Error Handling

- **Workspace already exists**: The script will exit with an error message explaining that the workspace folder already exists. Show this message to the user. They need to delete the existing workspace or use a different working directory.
- **DRM detected**: The script will exit with an error about DRM protection. Show the error to the user -- the EPUB must be DRM-free before processing.
- **EPUB file not found**: If the file path check in Step 1 fails, ask the user to verify the path and try again.
- **Round-trip validation fails**: The script will exit with validation errors. Show these to the user and suggest checking the EPUB file for unusual structure.

## Requirements

- Python 3 with `ebooklib` and `lxml` packages installed
- Install dependencies: `pip install ebooklib lxml`

## Notes

- The workspace folder is named with a timestamp prefix followed by the sanitized book title (e.g., `20260324_1902_Apocalypse-Generic-System`) and created in the current working directory. This makes each workspace unique and chronologically sortable.
- The workspace contains: `source/` (extracted chapter XHTML files), `output/<target_language>/` (empty, ready for translated chapters), `metadata.json` (book and configuration details), `test-roundtrip.epub` (kept for visual inspection in Calibre), and `detection_report.txt` (chapter detection details).
- The `metadata.json` file tracks processing state. After prepare-book, the status is "prepared". Downstream commands (`/build-book-glossary`, `/translate-book`) advance the state.
- The round-trip test EPUB is kept until `/translate-book` starts, so you can open it in any e-reader to verify extraction quality.
