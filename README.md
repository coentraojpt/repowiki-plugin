# repowiki

Convert any code repository into a rich, Obsidian-compatible wiki using multi-agent analysis.

## What it does

`/repowiki` analyses your repository using a pipeline of four specialized agents:

1. **Discovery** — scans every file and detects your tech stack
2. **Architect** — designs the wiki structure based on complexity
3. **Specialists** — one per section, running in parallel, deep-reading source code
4. **Finalizer** — resolves links, generates the vault index and knowledge graph

The result is an Obsidian vault with `[[WikiLinks]]`, Mermaid diagrams, YAML frontmatter, and source-attributed content.

## Install

```bash
/plugin install https://github.com/coentraojpt/repowiki-plugin
```

Or locally:

```bash
/plugin install /path/to/repowiki-plugin
```

## Usage

```bash
# Generate wiki for the current repo (output: .repowiki/)
/repowiki

# Custom output directory
/repowiki --output docs/wiki

# Portuguese content
/repowiki --lang pt

# Generate only one section
/repowiki --section "Database Schema"

# Regenerate only sections with changed files (git-aware)
/repowiki --update
```

## Open in Obsidian

After generation, open the output directory as an Obsidian vault:

`Settings (⚙) → Open vault → select .repowiki/`

The vault entry point is `index.md`.

## Output structure

```
.repowiki/
├── index.md                    # Vault entry point
├── Overview/
│   └── Project Overview.md
├── Architecture/
│   ├── Overview.md
│   └── Data Flow.md
├── Database/
│   ├── Schema Overview.md
│   └── Models Reference.md
├── API/
│   └── REST Endpoints.md
├── Security/
│   └── Authentication & Security.md
├── ... (sections depend on your repo)
└── _meta/
    └── repowiki-metadata.json  # Knowledge graph
```

## Extending with other AI providers

By default, repowiki uses Claude Code's session (no extra API cost). To use an external provider:

```bash
/repowiki --provider openai    # (v2 — not yet implemented)
/repowiki --provider ollama    # (v2 — not yet implemented)
```

See `providers/provider.py` to implement a new provider by subclassing `BaseProvider`.

## License

MIT
