---
name: translate-book
version: 1.1.3
description: Translate all chapters in parallel with glossary consistency, producing a translated EPUB
argument-hint: <workspace-path>
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, Agent]
---

# CABT Translate

Translate all chapters in parallel with glossary consistency, producing a translated EPUB. Uses XHTML tokenization to preserve formatting, dispatches translation agents in batches of 8, validates token integrity, merges new terms, and rebuilds the final EPUB.

<!-- ANTI-PATTERNS — READ BEFORE PROCEEDING:
  - DO NOT translate chapters yourself — always delegate to Agent tool
  - DO NOT write to glossary.md — it is read-only during translation
  - DO NOT use AskUserQuestion (bug #29547) — collect answers in conversation
  - DO NOT pass previous chapter context to agents
  - DO NOT send raw XHTML to agents — always tokenize first (tokens look like XML tags: <em:1>, </em:1>, <br:1/>)
  - DO NOT nest Agent calls — translation agents must NOT spawn sub-agents
-->

## Workflow

### Step 0: Version Check

Print the version on every run:

```
cabt:translate-book v1.1.3
```

Then check if `$ARGUMENTS` contains `--version`. If it does, stop here -- do not proceed to Step 1 or any further steps.

### Step 1: Load Workspace

If a workspace path was provided as `$ARGUMENTS`, change to that directory first:

```bash
cd "<workspace_path>"
```

Read `metadata.json` from the current directory.

```bash
cat ./metadata.json
```

Verify the contents:
- If the file does not exist, tell the user: "No workspace found. Run /prepare-book first." and stop.
- If `status` is not `"glossary-built"` and not `"translating"`, tell the user: "Unexpected workspace status: '{status}'. Expected 'glossary-built' (run /build-book-glossary first) or 'translating' (for resume)." and stop.

Verify that `glossary.md` exists in the current directory:

```bash
test -f ./glossary.md && echo "Glossary found" || echo "Glossary not found"
```

If glossary.md does not exist, tell the user: "glossary.md not found. Run /build-book-glossary first." and stop.

Extract these fields for use throughout the workflow:
- `title`
- `genre`
- `source_language`
- `target_language`
- `chapters` (array with `sequence`, `output_filename`, `token_count`)
- `original_epub_path`

Also extract reuse information:
- `glossary_reuse` field (if present): contains `source_workspace`, `source_book_title`, `imported_files`, `imported_at`
- Check if `glossary_reuse` is present AND `glossary_reuse.imported_files` contains `"translation-style-brief.md"` AND `./translation-style-brief.md` exists on disk -- if all true, this is a **reuse path** for the style brief
- If `glossary_reuse` is absent or `"translation-style-brief.md"` is not in `imported_files` or file is missing on disk, this is a **fresh path** (v1.0 behavior unchanged)

Note: Do NOT check for `translation_progress` here -- that is the resume path handled by Step 2. The three paths are: resume (translation_progress present with brief_generated or brief_reused true), reuse (`"translation-style-brief.md"` in glossary_reuse.imported_files + file on disk), and fresh (no brief). Resume takes precedence over reuse.

### Step 2: Check Resume State

Check if `metadata.json` has a `translation_progress` field:

- **If `translation_progress` exists and `translation_progress.status` is `"complete"`:**
  Tell the user: "Translation already complete. Your EPUB is at: ./{title}-{target_language}.epub" and stop.

- **If `translation_progress` exists and `translation_progress.status` is `"in_progress"`:**
  This is a resume. Determine:
  - `chapters_translated`: list of chapter sequences already translated
  - `chapters_failed`: list of chapter sequences that previously failed (will be retried)
  - `chapters_remaining`: all other chapters
  - Whether the style brief was already generated or confirmed from reuse (`brief_generated` or `brief_reused` field)

  Tell the user: "Resuming translation: {N} chapters already translated, {M} remaining (including {F} previously failed chapters to retry)."

  If `brief_generated` is true or `brief_reused` is true, skip Step 2.5 and Step 4 (style brief already handled).
  Skip chapters in `chapters_translated` during Step 7.
  Retry chapters in `chapters_failed` along with `chapters_remaining`.

- **If no `translation_progress` field:** Fresh start. Continue to Step 2.5.

### Step 2.5: Brief Detection and Analysis

*Skip this step on resume if `translation_progress.brief_generated` is true or `translation_progress.brief_reused` is true.*

Check which path applies (in priority order):

1. **Resume path:** If this is a resume (from Step 2) and brief was already handled -- skip Step 2.5 entirely. (Already handled by Step 2 logic above.)
2. **Reuse path:** If `"translation-style-brief.md"` is in `glossary_reuse.imported_files` AND `./translation-style-brief.md` exists on disk -- run the analysis flow below.
3. **Fresh path:** If no reused brief exists -- skip Step 2.5, continue to Step 3. Step 4 will generate the brief from scratch.

---

**Reuse path (analysis flow):**

Print:
```
Found translation style brief from [source_book_title]. Analyzing compatibility...
```
Where `[source_book_title]` comes from `glossary_reuse.source_book_title` in metadata.json.

Read the existing brief:
```bash
cat ./translation-style-brief.md
```

Read `book_research` from metadata.json (populated by /build-book-glossary Step 4). Compare the new book's research against the existing brief's settings. Specifically look for:

1. **Tone/register shifts:** Does the new book's style or tone differ from what the brief assumes? For example, if the brief says 'comedic tone with wordplay adaptation' but research suggests this book has a more serious, dramatic tone.
2. **Character voice changes:** Do new POV characters or narrator changes affect the translation style? For example, if the brief assumes a single first-person narrator but the new book has multiple POV characters with distinct voices.
3. **Genre emphasis shifts:** Does the new book emphasize different genre elements? For example, if the brief prioritizes action pacing but the new book is more dialogue-heavy or introspective.

IMPORTANT: Do NOT flag these as differences:
- Setting changes that don't affect translation style (new locations, new magic systems)
- New characters that follow existing voice patterns
- Plot-level differences that don't impact HOW text is translated

**If differences ARE found:** Present the brief summary with key settings, then flag each difference explicitly. For each diff, show what the current brief says and what the research suggests, then ask for the user's decision. Example:

```
Your brief says 'comedic tone with wordplay adaptation.' The new book has a more serious, dramatic tone. Want to adjust the humor handling?
```

After the user responds to each flagged item, update `./translation-style-brief.md` in place with the changes (edit specific sections, no full rewrite).

Then ask: 'Anything else you'd like to adjust?'

**If NO meaningful differences found:** Show:
```
Using translation style brief from [source_book_title]. Style: [key settings summary extracted from the brief -- sentence structure, humor handling, reading level, cultural references]. Anything to adjust?
```
Wait for user response. If user has adjustments, update `./translation-style-brief.md` in place. If user confirms, proceed.

**'Start fresh' escape hatch:** If at any point the user says they want to start fresh / generate a new brief / discard the existing brief:
- Print: 'Understood -- will generate a fresh brief in Step 4.'
- Do NOT set `brief_reused` flag
- Do NOT copy the brief to output directory
- Continue to Step 3, then Step 4 will run the full Q&A as usual

**After confirmation (reuse path only):**
- Print: 'Brief confirmed. Preparing chapters for translation...'
- Create output directories (same as Step 3):
```bash
mkdir -p './output/{lang}/'
mkdir -p './output/{lang}/translator-notes/'
mkdir -p './output/{lang}/new-terms/'
mkdir -p './output/{lang}/.tokenized/'
mkdir -p './output/{lang}/.translated/'
```
- Copy the confirmed brief to where translation agents expect it:
```bash
cp './translation-style-brief.md' './output/{lang}/translation-style-brief.md'
```
- Update metadata.json: set `status` to `'translating'` and add `translation_progress` with:
  - `status`: `'in_progress'`
  - `brief_reused`: true
  - `brief_generated`: false
  - `chapters_translated`: []
  - `chapters_failed`: []
  - `total_chapters`: (count from chapters array)
- Skip Step 3 (already created output dirs) and skip Step 4 (brief already confirmed). Continue to Step 5.

### Step 3: Create Output Directories

*Skip this step if output directories were already created in Step 2.5 (reuse path).*

Determine the language directory name. Use the same naming convention as prepare_workspace.py: lowercase, spaces replaced with hyphens (e.g., "Brazilian Portuguese" becomes "brazilian-portuguese").

```bash
mkdir -p "./output/{lang}/"
mkdir -p "./output/{lang}/translator-notes/"
mkdir -p "./output/{lang}/new-terms/"
mkdir -p "./output/{lang}/.tokenized/"
mkdir -p "./output/{lang}/.translated/"
```

Where `{lang}` is the target language directory name (lowercase, hyphenated).

Update metadata.json: set `status` to `"translating"` and add `translation_progress` with:
- `status`: `"in_progress"`
- `brief_generated`: false
- `chapters_translated`: []
- `chapters_failed`: []
- `total_chapters`: (count from chapters array)

### Step 4: Generate Translation Style Brief

*Skip this step on resume if `translation_progress.brief_generated` is true.* Also skip this step if `translation_progress.brief_reused` is true (brief was confirmed from reuse in Step 2.5).

Read `glossary-rules.md` to understand existing translation philosophy decisions:

```bash
cat ./glossary-rules.md
```

Present 3-4 translation-specific questions to the user that are NOT covered by glossary-rules.md. Use multiple-choice format (A/B/C). These questions address translation approach, not terminology (which glossary-rules.md already covers).

Example questions (use your judgment for exact wording based on genre and language pair):

1. **Sentence structure fidelity:** How closely should translation follow the source sentence structure?
   - (A) Very faithful to source structure -- keep sentence order and structure close to original
   - (B) Natural target language flow -- restructure sentences freely for natural reading
   - (C) Creative adaptation -- significant restructuring for stylistic effect

2. **Humor and wordplay handling:** When the source contains humor or wordplay:
   - (A) Translate literally and add a translator note explaining the joke
   - (B) Find equivalent humor in {target_language} even if the specific joke changes
   - (C) Prioritize comedic intent -- adapt freely to land the joke

3. **Expected reading level:** What reading level should the translation target?
   - (A) Young adult -- accessible vocabulary, shorter sentences
   - (B) Adult literary -- full vocabulary range, varied sentence structure
   - (C) Match source exactly -- mirror the complexity of the original

4. **Cultural references:** When the source contains culture-specific references:
   - (A) Keep original reference as-is
   - (B) Adapt to equivalent reference in target culture
   - (C) Keep original with a brief translator note

Wait for the user's responses in the conversation. Do NOT use AskUserQuestion.

After collecting all answers, build the Q&A JSON and call translation_helpers.py:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/translation_helpers.py generate-brief \
  --metadata-path ./metadata.json \
  --qa-json '{"sentence_structure": "answer", "humor_handling": "answer", "reading_level": "answer", "cultural_references": "answer"}' \
  --output ./output/{lang}/translation-style-brief.md
```

Read the generated brief and show a summary to the user:

```bash
cat ./output/{lang}/translation-style-brief.md
```

Update metadata.json: set `translation_progress.brief_generated` to true.

### Step 5: Prepare Glossary

Read glossary.md and strip (?) markers using translation_helpers.py. This creates a clean copy for translation agents -- the original glossary.md is NOT modified.

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/translation_helpers.py strip-glossary \
  --input ./glossary.md \
  --output ./output/{lang}/.cleaned-glossary.md
```

The `.cleaned-glossary.md` is a hidden working file, not part of the final output.

### Step 6: Tokenize All Source Chapters

For each chapter in the chapters array, tokenize the XHTML to replace tags with semantic XML-style tokens:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/xhtml_tokenizer.py tokenize \
  --input ./source/{output_filename} \
  --output ./output/{lang}/.tokenized/{output_filename}.txt \
  --registry ./output/{lang}/.tokenized/{output_filename}.json
```

Run this for every chapter. Log any tokenization failures but continue with the remaining chapters. A chapter that fails tokenization cannot be translated -- mark it as failed in metadata.json.

### Step 7: Translate Chapters in Parallel Batches

**Rebuild-only shortcut:** Before building the translation list, check if ALL chapters already have `.translated/` files on disk:

```bash
# For each chapter, check if ./output/{lang}/.translated/{output_filename}.txt exists
```

If every chapter has a `.translated/` file already, skip the entire translation step. Log: "All chapters already translated — skipping to detokenization and EPUB rebuild." Jump directly to Step 8.

This enables fast EPUB regeneration (e.g., after a tokenizer fix) without re-running expensive translation agents.

**Otherwise**, build the list of chapters to translate:
- Fresh start: all chapters
- Resume: all chapters minus those in `chapters_translated` (retry those in `chapters_failed`)

Process chapters in **batches of 8**. For each batch, dispatch **8 Agent tool calls simultaneously** in a single response.

**CRITICAL: Dispatch all agents in the batch at the same time. Do NOT wait for one agent to finish before starting the next within the same batch. Between batches, wait for all agents to return before starting the next batch.**

Each agent receives this prompt (adapted per chapter):

> You are a literary translation agent for "{title}".
>
> ## Context
> - Genre: {genre}
> - Translating from {source_language} to {target_language}
> - Chapter {sequence} of {total_chapters}
>
> ## Files to Read
> Read these files using the Read tool:
> 1. `./glossary-rules.md` -- your translation philosophy rules
> 2. `./output/{lang}/translation-style-brief.md` -- style guidelines for this translation
> 3. `./output/{lang}/.cleaned-glossary.md` -- glossary terms (USE THESE EXACTLY, no synonyms, no variation)
> 4. `./output/{lang}/.tokenized/{output_filename}.txt` -- the tokenized source chapter to translate
>
> ## CRITICAL RULES
> 1. GLOSSARY TERMS ARE NON-NEGOTIABLE. Use the exact translation from the glossary. No synonyms, no creative alternatives.
> 2. TRANSLATE EVERY SENTENCE. No omissions. No summaries. Every sentence in the source must have a corresponding translation.
> 3. PRESERVE ALL XML TOKENS. The source text contains formatting tokens that look like XML tags (e.g., `<em:1>`, `</strong:2>`, `<br:3/>`). These are NOT real HTML — they are placeholders for original formatting. Keep every token exactly as-is in your output, positioned correctly relative to the translated text. Do not modify, remove, translate, or invent tokens.
> 4. Follow the style brief for tone, register, humor adaptation, and cultural references.
> 5. Be faithful to the original but natural in the target language. Idioms should match existing idioms in the target language. Adapt humor, swear words, and cultural references naturally.
>
> ## Output
> Write THREE files:
>
> ### 1. Translated chapter
> Write the translated tokenized text to: `./output/{lang}/.translated/{output_filename}.txt`
> This should be the full translated text with all tokens preserved in place.
>
> ### 2. Translator notes
> Write to: `./output/{lang}/translator-notes/chapter-{seq:02d}-notes.md`
> Format:
> ```markdown
> # Translator Notes: Chapter {seq}
>
> ## Summary
> [1-2 sentence summary of what happens in this chapter]
>
> ## Translation Decisions
> [Notable choices: adapted idioms, wordplay handling, cultural adaptations]
>
> ## Ambiguous Passages
> [Any passages where meaning was unclear, with your interpretation]
>
> ## Warnings
> [Any issues: very long sentences, untranslatable wordplay, potential glossary conflicts]
> ```
>
> ### 3. New terms (only if new terms found)
> Write to: `./output/{lang}/new-terms/chapter-{seq:02d}-terms.md`
> Only create this file if you encounter important terms NOT in the glossary. Format:
> ```markdown
> # New Terms: Chapter {seq}
>
> | Source | Translation | Context |
> |---|---|---|
> | {source_term} | {your_translation} | {brief context for why this term matters} |
> ```

Agent allowed-tools: `[Read, Write, Edit, Bash, Glob, Grep]`
(No Agent nesting, no WebSearch -- translation agents just translate.)

**After each batch completes**, for each agent result:

1. **Validate tokens** on the translated output:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/xhtml_tokenizer.py validate \
     --original ./output/{lang}/.tokenized/{output_filename}.txt \
     --translated ./output/{lang}/.translated/{output_filename}.txt
   ```

2. **If validation fails:** Retry the chapter with a fresh Agent call (up to 2 retries total per chapter). Add this note to the retry agent prompt: "IMPORTANT: The previous translation attempt had token validation errors. Pay extra careful attention to preserving ALL tokens exactly as they appear in the source." If still failing after 2 retries, mark the chapter as failed.

3. **If validation passes:** Run detokenization to restore XHTML:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/xhtml_tokenizer.py detokenize \
     --input ./output/{lang}/.translated/{output_filename}.txt \
     --registry ./output/{lang}/.tokenized/{output_filename}.json \
     --output ./output/{lang}/{output_filename}
   ```

4. **Update metadata.json:** Move the chapter sequence to `chapters_translated` (if passed) or `chapters_failed` (if failed after retries).

5. **Log progress:** "Chapter {seq}/{total} translated -- {N} new terms" (or "Chapter {seq}/{total} FAILED after retries" if failed).

### Step 8: Merge New Terms

After ALL batches complete, merge per-chapter new-terms into a single file:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/translation_helpers.py merge-terms \
  --terms-dir ./output/{lang}/new-terms/ \
  --output ./output/{lang}/new-terms.md
```

If no new-terms files exist (no agents found new terms), this will produce an empty or minimal output file. This is normal.

### Step 9: Rebuild EPUB

Only proceed if at least one chapter was successfully translated.

Call rebuild_epub.py to produce the final translated EPUB:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/rebuild_epub.py \
  "{original_epub_path}" \
  "./output/{lang}/" \
  "./{title_slug}-{lang}.epub" \
  --target-language {target_language} \
  --metadata-json ./metadata.json
```

Where `{title_slug}` is the sanitized book title (lowercase, hyphens for spaces, no special characters) -- the same slug used for the workspace directory name.

If the rebuild fails, log the error but do NOT crash the workflow. The translated chapter files are still available even without the EPUB.

### Step 10: Final Summary

Update metadata.json:
- Set `status` to `"translated"`
- Set `translation_progress.status` to `"complete"`
- Set `translation_progress.epub_path` to the EPUB output path (if rebuild succeeded)

Display a comprehensive summary:

```
## Translation Complete

**Book:** {title}
**Translation:** {source_language} -> {target_language}

### Results
- Chapters translated: {N}/{total}
- Chapters failed: {M} {list of failed chapter sequences if any}
- New terms discovered: {count} (see output/{lang}/new-terms.md)

### Output Files
- Translated EPUB: ./{title_slug}-{lang}.epub
- Translator notes: ./output/{lang}/translator-notes/
- New terms for review: ./output/{lang}/new-terms.md

### Next Steps
1. Review the translated EPUB in your e-reader
2. Check translator notes for flagged passages
3. Review new-terms.md and add validated terms to glossary.md

---
Translation pipeline complete!
```

If some chapters failed, add a note:
```
### Failed Chapters
Chapters {list} could not be translated due to token validation errors.
You can retry them by removing those chapter numbers from `chapters_translated`
in metadata.json and running /translate-book {workspace_path} again.
```

## Error Handling

- **Chapter tokenization failure:** Log the error, mark the chapter as failed, continue with remaining chapters.
- **Agent failure (crash, timeout):** Mark the chapter as failed, continue with remaining chapters. Do NOT retry on agent crash (only retry on token validation failure).
- **Token validation failure:** Retry up to 2 times with a fresh Agent. If still failing after retries, mark as failed and continue.
- **Script failure (helpers, tokenizer):** Log stderr, continue if possible. Never crash the entire workflow for a single script error.
- **EPUB rebuild failure:** Log the error, still show the translation summary. The translated chapters are available as individual XHTML files even without the EPUB.
- **No chapters translated:** Skip EPUB rebuild. Show summary with 0 chapters translated and the failure details.

## Notes

- Python 3 with `ebooklib`, `lxml`, and `tiktoken` packages required
- The workspace path can be passed as an argument, or the current directory is used
- Each translation agent runs in parallel within its batch (8 agents at a time) -- unlike build-glossary which runs sequentially
- Glossary.md is read-only during translation. New terms go to separate per-chapter files.
- Translation progress is saved to metadata.json after each batch for checkpoint/resume support
- The Agent tool spawns foreground subagents. Multiple Agent calls in the same response run in parallel.
- AskUserQuestion is excluded from allowed-tools due to bug #29547
- The `.tokenized/`, `.translated/`, and `.cleaned-glossary.md` are working files, not part of the final output
