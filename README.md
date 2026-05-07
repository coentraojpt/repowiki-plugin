# repowiki — Claude Code Plugin

Convert any code repository into a rich, navigable Obsidian wiki directly from Claude Code — no Ollama, no API keys, no configuration.

## Install

```
/plugin install https://github.com/coentraojpt/repowiki-plugin
```

## Usage

```
/repowiki                            # generate wiki for current repo → .repowiki/
/repowiki --section "Database"       # regenerate one section only
/repowiki --output docs/wiki         # custom output directory
/repowiki --lang pt                  # Portuguese output (PT-PT)
/repowiki --update                   # only regenerate sections with changed files
```

```
/repowiki translate --to pt          # translate existing wiki to Portuguese
/repowiki translate --to en          # translate existing wiki to English
```

## How it works

Four specialized agents run in sequence:

```
/repowiki
    ├── [1] Discovery Agent     ← scans repo, builds manifest
    ├── [2] Architect Agent     ← designs wiki structure
    ├── [3..N] Specialist Agents ← one per section, run in parallel
    └── [N+1] Finalizer Agent   ← resolves links, builds index
```

Output is Obsidian-compatible: `[[WikiLinks]]`, Mermaid diagrams, YAML frontmatter, source-attributed content.

## Output structure

```
.repowiki/
├── index.md                  ← vault entry point
├── Overview/
│   └── Project Overview.md
├── Architecture/
│   ├── System Architecture.md
│   └── Data Flow.md
├── Database/
│   └── Models Reference.md
├── ... (sections adapt to your repo)
└── _meta/
    └── repowiki-metadata.json
```

Open in Obsidian: `Settings (⚙) → Open vault → select .repowiki/`

## Standalone CLI version

Looking for the standalone CLI (Ollama/OpenAI/Claude API, no Claude Code needed)?

→ [repowiki-cli](https://github.com/coentraojpt/repowiki-cli)

## License

MIT
