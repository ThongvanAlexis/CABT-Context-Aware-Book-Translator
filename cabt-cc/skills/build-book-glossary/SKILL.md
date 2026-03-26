---
name: build-book-glossary
version: 1.1.2
description: Build a genre-aware terminology glossary by processing chapters sequentially
argument-hint: <workspace-path>
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, Agent, WebSearch, WebFetch]
---

# CABT Build Glossary

Build a comprehensive, genre-aware terminology glossary by processing chapters sequentially. Each chapter is analyzed by a dedicated agent that receives the full accumulated glossary and returns only new terms. The glossary accumulates context chapter-by-chapter, ensuring consistent and comprehensive term extraction.

## Workflow

### Step 0: Version Check

Print the version on every run:

```
cabt:build-book-glossary v1.1.2
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
- If `status` is `"glossary-built"`, tell the user: "Glossary already built. Review glossary.md or delete it to rebuild." and stop.
- If `status` is not `"prepared"` and not `"glossary-in-progress"`, tell the user: "Unexpected workspace status: '{status}'. Expected 'prepared' or 'glossary-in-progress'." and stop.

Extract these fields for use throughout the workflow:
- `title`
- `genre`
- `source_language`
- `target_language`
- `chapters` (array with `sequence`, `output_filename`, `token_count`)

Also extract reuse information:
- `glossary_reuse` field (if present): contains `source_workspace`, `source_book_title`, `imported_files`, `imported_at`
- Check if `glossary_reuse` is present AND `glossary-rules.md` exists on disk -- if both true, this is a **reuse path** for rules
- Check if `glossary_reuse` is present AND `glossary.md` exists on disk -- if both true, this is a **reuse path** for glossary seeding
- If `glossary_reuse` is absent or both files are missing on disk, this is a **fresh path** (v1.0 behavior unchanged)

Note: Do NOT check for `glossary_progress` here -- that is the resume path handled by Step 2. The three paths are: fresh (no reuse, no resume), reuse (glossary_reuse present + files on disk), and resume (glossary_progress present). Resume takes precedence over reuse (if someone resumes a reuse build, Step 2 handles it).

### Step 2: Check Resume State

Run the resume check:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/glossary_helpers.py resume --metadata-path ./metadata.json
```

Parse the JSON output and handle each case:

- **If `is_complete` is true:** Tell the user "Glossary is already complete. Review glossary.md before running /translate-book." and stop.
- **If `is_resume` is true:** Tell the user: "{resume_from - 1} of {total} chapters already processed. Resume from chapter {resume_from} or restart from scratch?" Wait for the user's response. If the user chooses restart: delete glossary.md and glossary-rules.md, then reset `glossary_progress` in metadata.json by removing the field entirely.
- **If `is_resume` is false:** Fresh start. Continue to the next step.

### Step 3: Token Capacity Pre-flight

Check the output token environment variable:

```bash
echo ${CLAUDE_CODE_MAX_OUTPUT_TOKENS:-"NOT SET"}
```

Run the pre-flight check:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/glossary_helpers.py preflight --metadata-path ./metadata.json
```

Parse the JSON output. If `warnings` is non-empty:
- Show each warning to the user.
- List the large chapters by sequence number and token count.
- Suggest: "Set the environment variable `CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000` in your user profile (e.g., `.bashrc`, `.zshrc`, or PowerShell profile), then restart this shell for it to be taken into account."
- Ask the user: "Continue anyway or set the env var and restart first?"

If warnings is empty, proceed silently.

### Step 4: Book Research (Auto Pre-step)

Check if metadata.json already has a `book_research` field with `researched: true`. If so, skip this step and move to Step 5.

Use the **Agent** tool to spawn a book research agent with this prompt:

> You are a book research agent. Search the web for information about the book '{title}' to help with translation from {source_language} to {target_language}.
>
> Research the following:
> 1. Book summary and plot overview
> 2. Writing style and tone
> 3. Major themes
> 4. Series position (standalone, part of series, which book number)
> 5. Notable terminology conventions
> 6. Existing fan translations in {target_language} if any
> 7. Genre-specific conventions for {genre} books
>
> Try these search queries:
> - '{title}' book review
> - '{title}' {target_language} translation
> - '{title}' wiki fandom
> - '{title}' fan translation terminology
>
> Return a structured summary with these sections:
> - **Summary:** Brief plot overview
> - **Style:** Writing style and tone notes
> - **Themes:** Major themes
> - **Series Position:** Standalone or series info
> - **Terminology Notes:** Any notable terminology conventions found
> - **Fan Translations:** Existing fan translations found (or "None found")
>
> If the book is not found online, note this and return what you can infer from the title and genre.

The agent has access to WebSearch and WebFetch tools.

After the agent returns:
- Parse the response and save to metadata.json as a new `book_research` field with these keys:
  - `summary` (string)
  - `style` (string)
  - `themes` (string)
  - `series_position` (string)
  - `terminology_notes` (string)
  - `fan_translations` (string)
  - `researched` (boolean -- true if the agent found information, false if not)
- If the agent fails or returns nothing useful, set `researched` to `false` and note the failure. This is NOT a blocker -- proceed to the next step.

### Step 5: Translation Rules Q&A

Check which path applies (in priority order):

1. **Resume path:** If `glossary-rules.md` exists AND this is a **resume** (from Step 2, i.e., `glossary_progress` is present) -- skip Step 5 entirely. (Unchanged from v1.0.)
2. **Reuse path:** If `glossary-rules.md` exists AND this is a **reuse** path (`glossary_reuse` present in metadata.json, not a resume) -- run the adapted flow below.
3. **Fresh path:** If `glossary-rules.md` does NOT exist -- run the full Q&A flow below.

---

**Reuse path (adapted flow):**

Print:
```
Using translation rules from [source_book_title]. Checking for differences...
```
Where `[source_book_title]` comes from `glossary_reuse.source_book_title` in metadata.json.

Compare the book research (from Step 4's `book_research` field in metadata.json) against the existing `glossary-rules.md`. Specifically look for ONLY these two categories of differences:

1. **Tone/register shifts:** Does the new book's style or tone differ from what the rules assume? For example, if rules say "use tu/vous with allies=tu" but research suggests this book is more formal overall.
2. **Fan translation updates:** Does the research reveal established fan translations in the target language that contradict current rules? For example, if rules say "keep Skill in English" but research found the community now uses a translated term.

IMPORTANT: Do NOT flag these as differences:
- New characters, locations, or entities (naming conventions carry forward -- if rules say "keep names in English", that applies to new names too)
- New genre terms that follow existing rule patterns
- Any item that is simply "new but consistent with existing rules"

**If differences ARE found:** Present only the specific diffs as targeted questions. For each diff, show what the current rule says and what the research suggests, then ask for the user's decision. After the user responds, update `glossary-rules.md` in place with the changes (no changelog section, no full rewrite -- just edit the specific rules that changed).

**If NO meaningful differences found:** Show:
```
These rules carry forward from [source_book_title]. Anything to adjust?
```
Wait for user response. If user has adjustments, update `glossary-rules.md` in place. If user says no / confirms, proceed.

**Both reuse sub-paths end with:** Ask: "Do you want to discuss more points or have specific concerns about the translation?"

Then print: "Rules confirmed. Starting glossary build..."

---

**Fresh path (full Q&A -- v1.0 behavior unchanged):**

Generate 6-10 genre-specific questions dynamically based on `source_language`, `target_language`, and `genre`. All questions are in English regardless of target language.

Questions should cover:
- **Proper nouns:** Translate names with narrative meaning, or keep all names in the original language?
- **Key genre terms:** Specific to the genre:
  - LitRPG: Skill, Quest, Dungeon, Level, Party, Boss, Loot, Buff/Debuff, Tank/Healer/DPS, system notifications
  - Fantasy: spells, incantations (keep original language if Latin/Elvish?), noble titles (Lord/Seigneur?), magical system terms
  - Sci-Fi: tech terms (FTL, warp), military ranks (Captain/Capitaine?), ship/station names, scientific jargon
  - General: domain-specific terminology, formal/informal register
- **Onomatopoeia and SFX:** Adapt sound effects or keep original? (e.g., *ding!*, *whoosh*, *crack*)
- **Character speech register:** How to handle different speech levels (formal/informal/slang) in {target_language}?
- **Cultural adaptations:** Adapt cultural references or keep original with footnotes?
- **Honorifics:** If applicable to the language pair, how to handle honorifics?

If `book_research` is available and has `researched: true`, reference specific findings in the questions. For example: "Fans commonly translate X as Y -- do you agree with this convention?"

Present all questions to the user at once. Wait for the user's responses.

After receiving answers, ask: "Do you want to discuss more points or have specific concerns about the translation?"

Write all decisions to `glossary-rules.md` in English. Format as a clear, numbered list of translation rules. Example format:

```markdown
# Translation Rules -- {title}

## Proper Nouns
1. Keep character names in English unless they have clear narrative meaning
2. Translate place names that are descriptive (e.g., "Shadowlands")

## Genre Terms
3. Keep "Skill", "Quest", "Dungeon" in English (common in French LitRPG community)
4. Translate "Level" as "Niveau"
...

## Speech Register
5. Use tu/vous distinction: allies use tu, strangers use vous
...
```

### Step 6: Initialize Glossary

If `glossary.md` does not exist (fresh start or restart, no reuse):

Run the template generator:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/glossary_helpers.py template --title "{title}" --genre "{genre}" --source-language "{source_language}" --target-language "{target_language}"
```

Write the stdout output to `glossary.md`.

Update metadata.json:
- Set `status` to `"glossary-in-progress"`
- Add `glossary_progress` field with:
  - `last_chapter_processed`: 0
  - `total_chapters`: (number of chapters from chapters array)
  - `status`: `"in_progress"`

If `glossary.md` already exists from reuse (`glossary_reuse` present in metadata.json and `glossary.md` on disk): skip template generation entirely -- the reused glossary is already in place. Instead:

1. Count the existing terms in `glossary.md`: count all non-header, non-separator table rows (lines starting with `|` that are not header rows or `|---|` separator rows) across all sections. Store this count as `carried_forward_count` for use in Step 8.
2. Print: `Starting with N terms from [source_book_title]. Processing chapters for new terms...` where N is the `carried_forward_count` and `source_book_title` comes from `glossary_reuse.source_book_title`.
3. Update metadata.json: set `status` to `"glossary-in-progress"`, add `glossary_progress` field with `last_chapter_processed: 0`, `total_chapters: (count)`, `status: "in_progress"`, and `carried_forward_count: N`.

If `glossary.md` already exists from resume (`glossary_progress` present, not from reuse): this is handled by Step 2. Step 6 does nothing (existing v1.0 behavior).

### Step 7: Process Chapters Sequentially

Display before starting the loop:

```
Now processing all {total_chapters} chapters sequentially. This will take a while.
(The glossary from previous chapters is important when processing a chapter, which is why we process them sequentially — each chapter analysis gets the glossary from the previous chapters in its context.)
```

Note: When `glossary.md` was seeded from a previous book (reuse path), chapter agents work exactly as in the fresh path -- they read the accumulated glossary and add only new terms. No changes to the agent prompt or processing loop.

**CRITICAL — THREE RULES FOR CHAPTER PROCESSING:**
1. **ONE agent PER chapter.** Never batch multiple chapters into a single agent. Each chapter gets its own dedicated Agent call.
2. **SEQUENTIAL, never parallel.** Wait for one agent to return before spawning the next. The orchestrator updates glossary.md between agents so the next agent sees accumulated terms.
3. **NEVER process chapter content in this orchestrator context.** Do NOT read chapter XHTML files, glossary.md, or glossary-rules.md yourself. The agent reads those files itself.

**The loop must look like this:** for each chapter → spawn ONE agent → agent returns new terms → orchestrator appends terms to glossary.md → orchestrator updates metadata.json → log progress → move to NEXT chapter → spawn next agent. Do NOT spawn an agent that handles "remaining chapters" or "chapters N through M".

For each chapter in the `chapters` array from metadata.json (in sequence order), starting from the resume point:

1. **Skip** if the chapter's `sequence` is less than or equal to `glossary_progress.last_chapter_processed`.

2. **Prepare book research summary** (from metadata.json already in memory): If `book_research.researched` is true, format a brief paragraph from the `book_research` fields (summary, style, themes, terminology_notes). Otherwise use "No book research available."

3. **Spawn a glossary extraction agent using the Agent tool.** Pass it file paths — the agent reads the files itself. Use this prompt:

   > You are a glossary extraction agent for literary translation.
   >
   > ## Context
   > - Book: {title}
   > - Genre: {genre}
   > - Source Language: {source_language}
   > - Target Language: {target_language}
   > - Chapter: {sequence} of {total_chapters}
   > - Book Research: {book_research_summary}
   >
   > ## Files to Read
   > Read these files yourself using the Read tool:
   > - `./glossary-rules.md` — translation rules
   > - `./glossary.md` — current accumulated glossary
   > - `./source/{output_filename}` — chapter XHTML to process
   >
   > ## Your Task
   > 1. Read all three files above first.
   > 2. Read the chapter content carefully. XHTML tags provide formatting context (e.g., `<em>` for emphasis, `<strong>` for system notifications in LitRPG). Focus on text content.
   > 3. Check ALL sections of the current glossary before adding any term. Identify ONLY terms that should be in the glossary but are NOT already there.
   > 4. For each new term, provide:
   >    - {source_language} term (exact as it appears in the text)
   >    - {target_language} translation (following the translation rules in glossary-rules.md)
   >    - Context note (ch.{sequence} + brief context)
   >    - For characters: also note their speech register (formal, informal, slang, etc.)
   > 5. If you are uncertain about a translation, mark it with (?) after the translation. Example: Croc-Ombre (?)
   > 6. If an existing glossary term appears in new significant context in this chapter, note the context update needed. Format: UPDATE: [term] -- add context: [new context note]
   > 7. Do NOT repeat terms already in the glossary unless you are noting a context update.
   > 8. Do NOT add idiomatic expressions, common sayings, proverbs, pop culture references, or brand names to the glossary (e.g., "Work smarter, not harder", "M&Ms", "break a leg"). These are the translator's job to handle in context during translation — they are NOT glossary terms. The glossary is for recurring proper nouns, genre-specific terminology, character names, world-building terms, and technical vocabulary that need consistent translation across chapters.
   >
   > ## Output Format
   > Return ONLY new entries as markdown tables matching the glossary section structure. Use the exact section headers from the glossary. If no new terms found in a category, omit that section.
   >
   > Example output:
   > ## Characters and Creatures
   > | {source_language} | {target_language} | Register | Context |
   > |---|---|---|---|
   > | Shadowfang | Croc-Ombre (?) | formal, archaic speech | ch.03 -- antagonist introduced |
   >
   > ## Skills / Spells / Abilities
   > | {source_language} | {target_language} | Context |
   > |---|---|---|
   > | Mana Burst | Explosion de Mana | ch.03 -- MC first skill |
   >
   > If no new terms at all, respond with: No new terms.
   >
   > IMPORTANT: Return ONLY the markdown tables (or 'No new terms.'). No explanations, no preamble.

7. **Parse the agent's response:**
   - If the response contains "No new terms" -- log and continue to the next chapter.
   - If markdown tables are returned -- for each section header in the response, find the matching section in `glossary.md` and append the new rows after the existing table rows (before the next section header). Match section headers exactly. If the agent returned a section header that does not exist in `glossary.md`, add it as a new section at the end of the file (before any trailing content).
   - If UPDATE lines are present (lines starting with "UPDATE:") -- find the existing term's row in `glossary.md` and append the new context note to its Context column, separated by a semicolon.

8. **Write** the updated `glossary.md`.

9. **Update metadata.json:** Set `glossary_progress.last_chapter_processed` to this chapter's sequence number.

10. **Log progress:** "Chapter {sequence}/{total_chapters} -- {N} new terms" (where N is the count of new table rows from the agent response, excluding header and separator rows).

### Step 8: Finalize

After all chapters are processed:

1. Update metadata.json:
   - Set `status` to `"glossary-built"`
   - Set `glossary_progress.status` to `"complete"`

2. Count glossary statistics by reading `glossary.md`:
   - Total terms: count all non-header, non-separator table rows (lines starting with `|` that are not header rows or `|---|` separator rows) across all sections
   - Terms per category: count rows per section header
   - Uncertain terms: count entries containing `(?)` in glossary.md

3. Display the final summary:

   **If this was a reuse build** (`glossary_reuse` present in metadata.json):
   - Read `carried_forward_count` from `glossary_progress` in metadata.json (saved in Step 6)
   - Calculate `new_terms = total_terms - carried_forward_count`
   - Display:

   ```
   Glossary Complete!

     Total terms:        {total}  ({carried_forward_count} carried forward + {new_terms} new)
     Terms by category:
       {category 1}:     {n}
       {category 2}:     {n}
       ...
     Uncertain terms:    {n} (marked with (?))

   Review glossary.md and fix any (?) entries before translating.

   ---
   Next step: /translate-book {workspace_path}
   ```

   **If this was NOT a reuse build** (fresh path -- v1.0 behavior unchanged):

   ```
   Glossary Complete!

     Total terms:        {count}
     Terms by category:
       {category 1}:     {n}
       {category 2}:     {n}
       ...
     Uncertain terms:    {n} (marked with (?))

   Review glossary.md and fix any (?) entries before translating.

   ---
   Next step: /translate-book {workspace_path}
   ```

   Where `{workspace_path}` is the current working directory (the workspace the user `cd`'d into or passed as argument).

   **IMPORTANT:** Print the command exactly as `/translate-book`, NOT `/cabt:translate-book`. Do NOT add a namespace prefix. The short form is required for autocomplete to work.

## Error Handling

- **No metadata.json:** "No workspace found. Run /prepare-book first."
- **Status is "glossary-built":** "Glossary already built. Review glossary.md or delete it to rebuild."
- **Agent returns unparseable response:** Log a warning with the chapter number, skip that chapter's terms, and continue. The chapter can be re-processed later by manually resetting `glossary_progress.last_chapter_processed` in metadata.json to the chapter before the failed one.
- **Book research agent fails:** Set `book_research.researched` to `false` in metadata.json and proceed without research context. This is not a blocker.

## Notes

- Python 3 with `ebooklib`, `lxml`, and `tiktoken` packages required
- The workspace path can be passed as an argument, or the current directory is used
- Each chapter agent runs sequentially (not parallel) to ensure glossary accumulation -- each agent sees terms from all previous chapters
- glossary.md is saved after every chapter for checkpoint/resume support
- The Agent tool spawns foreground subagents that block until complete
- glossary-rules.md is written before any chapter processing begins
- Book research results are saved to metadata.json so they persist across resume sessions
