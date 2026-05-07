---
description: Translate an existing repowiki Obsidian wiki to a different language
allowed-tools: Glob, Read, Write
---

Translate all Markdown pages in an existing repowiki vault to the target language. Preserve frontmatter, [[WikiLinks]], Mermaid diagrams, and code blocks — translate only prose content.

## Usage Examples

```
/repowiki translate --to pt    # translate existing wiki to Portuguese (PT-PT)
/repowiki translate --to en    # translate existing wiki to English
/repowiki translate --to es    # translate existing wiki to Spanish
```

## Step 0: Parse Arguments

- `--to <lang>` — target language code (required). Common codes: `en`, `pt`, `es`, `fr`, `de`, `it`
- `--wiki <dir>` — wiki directory to translate (default: `.repowiki`)

Store:
- `TARGET_LANG` = parsed `--to` value
- `WIKI_DIR` = parsed `--wiki` value or `.repowiki`

If `--to` is not provided, report an error: "Usage: /repowiki translate --to <lang>" and stop.

## Step 1: Discover pages

Use Glob to find all `.md` files in `<WIKI_DIR>/` excluding `_meta/` and `index.md`.

Report: `Found N pages to translate to <TARGET_LANG>`

## Step 2: Translate each page

For EACH `.md` file found:

1. Read the file content
2. Translate it — follow these rules exactly:
   - **Preserve verbatim** (do NOT translate):
     - YAML frontmatter (lines between `---` markers at the top)
     - `[[WikiLinks]]` — keep the exact text inside double brackets
     - Mermaid code blocks (` ```mermaid ... ``` `)
     - All other fenced code blocks (` ```lang ... ``` `)
     - `> **Sources:**` attribution lines
     - The footer line starting with `*[[index|`
   - **Translate** all other prose text to `<TARGET_LANG>`
   - For Portuguese (pt): use PT-PT (European Portuguese), not PT-BR
3. Write the translated content back to the same file path

## Step 3: Translate index.md

Read `<WIKI_DIR>/index.md`. Translate only the prose content (table cells that are section descriptions, "Start Here" bullet descriptions). Preserve all `[[WikiLinks]]`, YAML frontmatter, and the table structure. Write it back.

## Step 4: Report

```
✓ Translation complete

Wiki:      <WIKI_DIR>/
Language:  <TARGET_LANG>
Pages:     <N> translated

Open in Obsidian to verify.
```
