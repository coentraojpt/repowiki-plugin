# repowiki

Convert any code repository into a rich, navigable Obsidian wiki — **runs locally, no API keys, no accounts**.

## How it works

```
your repo  →  repowiki  →  Obsidian vault
```

Four agents work in sequence:
1. **Discovery** — maps every file and detects your tech stack
2. **Architect** — designs the wiki structure based on complexity
3. **Specialists** — one per section, deep-reads source code in parallel
4. **Finalizer** — resolves links, builds the index and knowledge graph

Output is Obsidian-compatible: `[[WikiLinks]]`, Mermaid diagrams, YAML frontmatter, source-attributed content.

---

## Quickstart (2 steps)

**Step 1 — Install Ollama** (free, runs on your machine):

```
https://ollama.com/download
```

**Step 2 — Pull a model and run:**

```bash
ollama pull gemma4:9b

cd /your/project
python /path/to/repowiki/cli.py
```

That's it. repowiki auto-detects the best model you have installed.

---

## Open in Obsidian

After generation, open the output as a vault:

`Obsidian → Settings (⚙) → Open vault → select .repowiki/`

Start at `index.md`.

---

## Options

```bash
python cli.py                        # auto-detect model, output → .repowiki/
python cli.py --model gemma4:9b      # pick a specific model
python cli.py --output docs/wiki     # custom output directory
python cli.py --lang pt              # Portuguese output
python cli.py --section "Database"   # regenerate one section only
python cli.py --dry-run              # preview plan without generating
```

---

## Recommended models

| Model | Size | Notes | Install |
|---|---|---|---|
| `gemma4:9b` | ~6 GB | Best balance — recommended | `ollama pull gemma4:9b` |
| `qwen2.5:7b` | ~5 GB | Strong code understanding | `ollama pull qwen2.5:7b` |
| `llama3.1:8b` | ~5 GB | Good general purpose | `ollama pull llama3.1:8b` |
| `gemma4` | ~2 GB | Fast, limited context | `ollama pull gemma4` |
| `gemma4:27b` | ~17 GB | Best quality, needs 16GB VRAM | `ollama pull gemma4:27b` |

repowiki auto-selects the best model from this list that you have installed.

---

## Claude Code plugin

If you use Claude Code, install as a plugin — uses your existing session, nothing to configure:

```
/plugin install repowiki
/repowiki
```

---

## Output structure

```
.repowiki/
├── index.md                  ← vault entry point
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
├── ... (sections adapt to your repo)
└── _meta/
    └── repowiki-metadata.json
```

---

## License

MIT
