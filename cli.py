#!/usr/bin/env python3
"""
repowiki CLI — convert any code repository into an Obsidian wiki.

Runs locally with Ollama — no API keys, no accounts, no cost.
Auto-detects the best available model on your machine.

Usage:
  python cli.py                       # auto-detect model → .repowiki/
  python cli.py --model gemma4:9b     # pick a specific model
  python cli.py --output docs/wiki    # custom output dir
  python cli.py --lang pt             # Portuguese output
  python cli.py --section "Database"  # one section only
  python cli.py --dry-run             # preview plan, no generation

Requirements:
  - Python 3.10+  (no pip installs needed)
  - Ollama running: https://ollama.com
  - At least one model: ollama pull gemma4:9b
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── Constants ───────────────────────────────────────────────────────────────

IGNORE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", "migrations",
    "staticfiles", "dist", "build", "coverage", ".repowiki", ".tmp",
    ".claude", ".vscode", ".idea", "htmlcov", ".eggs", "eggs",
    "vendor", "bower_components", ".next", ".nuxt", "__mocks__",
}
SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".rb", ".java",
    ".cs", ".php", ".swift", ".kt", ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".sh", ".md",
}
IGNORE_EXTENSIONS = {".pyc", ".pyo", ".min.js", ".min.css", ".map"}

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# ── Phase 1: Discovery ──────────────────────────────────────────────────────

def scan_repo(repo_root: Path) -> dict:
    """Scan repo structure without AI. Pure filesystem analysis."""
    repo_root = repo_root.resolve()
    files_by_type: dict[str, list[str]] = {
        "models": [], "views": [], "urls": [], "serializers": [],
        "forms": [], "tasks": [], "consumers": [], "settings": [],
        "tests": [], "docker": [], "templates": [], "components": [],
        "config": [],
    }
    all_files: list[str] = []

    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames
                       if d not in IGNORE_DIRS and not d.startswith(".")]
        for filename in filenames:
            fp = Path(dirpath) / filename
            rel = fp.relative_to(repo_root)
            suffix = fp.suffix.lower()
            if suffix in IGNORE_EXTENSIONS:
                continue
            if suffix not in SOURCE_EXTENSIONS and filename not in ("Dockerfile", "Makefile"):
                continue
            s = str(rel).replace("\\", "/")
            all_files.append(s)
            name = filename.lower()
            path = s.lower()

            if filename in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml"):
                files_by_type["docker"].append(s)
            elif name == "models.py" or "/models/" in path:
                files_by_type["models"].append(s)
            elif name in ("views.py",) or "/views/" in path:
                files_by_type["views"].append(s)
            elif name == "urls.py" or "/routes/" in path:
                files_by_type["urls"].append(s)
            elif name == "serializers.py":
                files_by_type["serializers"].append(s)
            elif name == "forms.py":
                files_by_type["forms"].append(s)
            elif name == "tasks.py" or "celery" in path:
                files_by_type["tasks"].append(s)
            elif "consumers.py" in name:
                files_by_type["consumers"].append(s)
            elif "settings" in name and suffix == ".py":
                files_by_type["settings"].append(s)
            elif name.startswith("test_") or "/tests/" in path or "/test/" in path:
                files_by_type["tests"].append(s)
            elif suffix in (".html", ".jinja2"):
                files_by_type["templates"].append(s)
            elif suffix in (".jsx", ".tsx") or "/components/" in path:
                files_by_type["components"].append(s)
            elif name in ("settings.py", "config.py", "pyproject.toml",
                          "package.json", "go.mod", "requirements.txt"):
                files_by_type["config"].append(s)

    # Language detection
    counts = {
        "python": sum(1 for f in all_files if f.endswith(".py")),
        "typescript": sum(1 for f in all_files if f.endswith((".ts", ".tsx"))),
        "javascript": sum(1 for f in all_files if f.endswith((".js", ".jsx"))),
        "go": sum(1 for f in all_files if f.endswith(".go")),
        "rust": sum(1 for f in all_files if f.endswith(".rs")),
        "ruby": sum(1 for f in all_files if f.endswith(".rb")),
    }
    lang = max(counts, key=counts.get) if any(counts.values()) else "unknown"

    # Stack & pattern detection
    paths_str = " ".join(all_files).lower()
    stack = []
    if files_by_type["settings"] or "django" in paths_str:
        stack.append("django")
    if files_by_type["tasks"]:
        stack.append("celery")
    if files_by_type["consumers"]:
        stack.append("django-channels")
    if "fastapi" in paths_str:
        stack.append("fastapi")
    if "express" in paths_str:
        stack.append("express")
    if files_by_type["components"] or "react" in paths_str:
        stack.append("react")
    if files_by_type["docker"]:
        stack.append("docker")
    if "postgres" in paths_str or "postgresql" in paths_str:
        stack.append("postgresql")
    if "redis" in paths_str:
        stack.append("redis")

    patterns = []
    if files_by_type["tasks"]:
        patterns.append("background-jobs")
    if files_by_type["consumers"]:
        patterns.append("websockets")
    if files_by_type["serializers"]:
        patterns.append("rest-api")
    if files_by_type["tests"]:
        patterns.append("testing")
    if files_by_type["docker"]:
        patterns.append("containerized")
    # Multi-tenancy check (read first model file)
    for mf in files_by_type["models"][:2]:
        try:
            content = (repo_root / mf).read_text(encoding="utf-8", errors="ignore")[:4000].lower()
            if any(k in content for k in ("empresa", "tenant", "organization_id", "company_id")):
                patterns.append("multi-tenant")
                break
        except Exception:
            pass

    total = len(all_files)
    complexity = "low" if total < 30 else "high" if total > 150 else "medium"

    key_files = [
        f for f in ("README.md", "requirements.txt", "package.json",
                    "go.mod", "Cargo.toml", "pyproject.toml", "manage.py")
        if (repo_root / f).exists()
    ]
    key_files += files_by_type["settings"][:2]
    key_files += files_by_type["config"][:2]
    key_files = list(dict.fromkeys(key_files))[:10]

    return {
        "repo_name": repo_root.name,
        "repo_root": str(repo_root),
        "language_primary": lang,
        "framework": stack[0] if stack else "unknown",
        "stack": stack,
        "detected_patterns": patterns,
        "complexity": complexity,
        "total_files": total,
        "files_by_type": files_by_type,
        "key_files": key_files,
    }


# ── Phase 2: Architecture (rule-based, no AI needed) ───────────────────────

SECTION_RULES = [
    dict(id="overview",    title="Project Overview",          out="Overview",
         pages=["Project Overview"],
         sources=["key_files"],
         context="Repository purpose, tech stack, and quick start guide",
         always=True),
    dict(id="architecture", title="Architecture & Design",    out="Architecture",
         pages=["Overview", "Data Flow"],
         sources=["settings", "config"],
         context="System architecture, layers, and component relationships",
         always=True),
    dict(id="database",    title="Database Schema",           out="Database",
         pages=["Schema Overview", "Models Reference"],
         sources=["models"],
         context="ORM models, database relationships, and data structures",
         always=False),
    dict(id="api",         title="API Reference",             out="API",
         pages=["REST Endpoints"],
         sources=["views", "urls", "serializers"],
         context="API endpoints, request/response formats",
         always=False),
    dict(id="security",    title="Authentication & Security", out="Security",
         pages=["Authentication Flow"],
         sources=["views"],
         context="Authentication, authorization, and security mechanisms",
         always=False),
    dict(id="frontend",    title="Frontend Architecture",     out="Frontend",
         pages=["UI Overview"],
         sources=["templates", "components"],
         context="Frontend templates, components, and UI architecture",
         always=False),
    dict(id="jobs",        title="Background Jobs",           out="Jobs",
         pages=["Task Overview"],
         sources=["tasks"],
         context="Background job definitions, queues, and scheduled tasks",
         always=False),
    dict(id="realtime",    title="Real-time & WebSocket",     out="Realtime",
         pages=["WebSocket Channels"],
         sources=["consumers"],
         context="WebSocket consumers and real-time events",
         always=False),
    dict(id="testing",     title="Testing Strategy",          out="Testing",
         pages=["Test Overview"],
         sources=["tests"],
         context="Test structure, patterns, and testing strategy",
         always=False),
    dict(id="operations",  title="Deployment & Operations",   out="Operations",
         pages=["Deployment Guide"],
         sources=["docker", "config"],
         context="Deployment configuration and infrastructure",
         always=False),
    dict(id="faq",         title="Troubleshooting & FAQ",     out="FAQ",
         pages=["Common Issues & FAQ"],
         sources=["key_files"],
         context="Common issues, debugging tips, and FAQ",
         always=True),
]

AUTH_PATHS = {"auth", "account", "login", "password", "session", "token", "jwt"}


def plan_architecture(manifest: dict, section_filter: str | None = None) -> dict:
    ft = manifest["files_by_type"]
    sections = []

    for rule in SECTION_RULES:
        # Decide if section applies
        if not rule["always"]:
            sources = [f for key in rule["sources"] for f in ft.get(key, [])]
            if not sources:
                # Special case: security — check for auth paths in views
                if rule["id"] == "security":
                    sources = [f for f in ft.get("views", [])
                               if any(p in f.lower() for p in AUTH_PATHS)]
                if not sources:
                    continue

        if section_filter and rule["title"].lower() != section_filter.lower():
            continue

        # Build key_files list
        key_files: list[str] = []
        for key in rule["sources"]:
            if key == "key_files":
                key_files += manifest["key_files"]
            else:
                key_files += ft.get(key, [])[:8]
        # Deduplicate, cap at 10
        seen: set[str] = set()
        deduped = [f for f in key_files if not (f in seen or seen.add(f))][:10]  # type: ignore

        sections.append({
            "id": rule["id"],
            "title": rule["title"],
            "output_dir": rule["out"],
            "pages": list(rule["pages"]),
            "key_files": deduped,
            "context": rule["context"],
        })

    return {"repo_name": manifest["repo_name"], "sections": sections}


# ── Phase 3: Content generation ─────────────────────────────────────────────

def build_prompt(section: dict, source_text: str, lang: str, depth: str = "medium") -> str:
    lang_note = "Escreve todo o conteúdo em Português (PT-PT)." if lang == "pt" \
                else "Write all content in English."

    depth_note = {
        "shallow": "Note: Source shown as structural summary (class/field/method names only).",
        "medium": "Note: Source shown as structural summary with method body previews.",
        "deep": "",
    }.get(depth, "")

    pages_list = "\n".join(f"- {p}" for p in section["pages"])
    sep = "---PAGE_BREAK---"

    return f"""You are a senior technical writer generating wiki documentation for a software repository.

TASK: Generate Obsidian-compatible Markdown wiki pages for the "{section['title']}" section.
CONTEXT: {section['context']}
LANGUAGE: {lang_note}

PAGES TO WRITE:
{pages_list}

SOURCE CODE (document ONLY what you see here — never invent):
{source_text}
{depth_note}

OUTPUT FORMAT:
Write each page as a separate Markdown document.
Separate pages with exactly this line: {sep}
Each page must follow this template:

---
tags: [<2-4 lowercase tags>]
category: {section['output_dir']}
wiki_version: 1.0
generated: {TODAY}
sources: {', '.join(section.get('key_files', []))}
---

# <Page Title>

## Table of Contents
- [[{section['output_dir']}/<sibling page if any>]]
- [[index|Back to Index]]

## <Heading 1>

<Clear technical prose based on the source code above>

```mermaid
<erDiagram for models | graph TB for architecture | sequenceDiagram for flows>
```

> **Sources:** `<filename>:L<start>-L<end>`

---
*[[index|← Back to Index]] · Generated by repowiki*

RULES:
1. Every class name, method, field, and endpoint must come from the source code above.
2. Include at least one Mermaid diagram per page.
3. Use [[WikiLinks]] for internal navigation: [[Category/Page Name]].
4. Write wiki prose (encyclopedic), NOT code commentary ("this function does X").
5. Separate pages with exactly: {sep}

Begin writing now:
"""


def parse_pages(response: str, section: dict) -> dict[str, str]:
    sep = "---PAGE_BREAK---"
    parts = [p.strip() for p in response.split(sep) if p.strip()]

    if len(parts) >= len(section["pages"]):
        return {section["pages"][i]: parts[i] for i in range(len(section["pages"]))}

    # Fallback: assign everything to first page
    return {section["pages"][0]: response.strip()}


def write_page(output_dir: Path, section_dir: str, page_name: str, content: str) -> Path:
    target = output_dir / section_dir
    target.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[<>:"/\\|?*]', "-", page_name)
    path = target / f"{safe}.md"
    path.write_text(content, encoding="utf-8")
    return path


# ── Phase 4: Finalization ───────────────────────────────────────────────────

def write_index(output_dir: Path, architecture: dict, manifest: dict):
    repo = manifest["repo_name"]
    stack = ", ".join(manifest["stack"]) or "unknown"
    total_pages = sum(len(s["pages"]) for s in architecture["sections"])

    rows = []
    start_here = []
    for s in architecture["sections"]:
        links = " · ".join(f"[[{s['output_dir']}/{p}]]" for p in s["pages"])
        rows.append(f"| [[{s['output_dir']}/{s['pages'][0]}\\|{s['title']}]] | {links} |")
        if s["id"] in ("overview", "architecture", "database"):
            start_here.append(f"- [[{s['output_dir']}/{s['pages'][0]}]] — {s['context']}")

    content = f"""---
tags: [index, wiki, overview]
category: index
wiki_version: 1.0
generated: {TODAY}
---

# {repo} Wiki

> **Stack:** {stack} · **Sections:** {len(architecture["sections"])} · **Pages:** {total_pages}

## Navigation

| Section | Pages |
|---|---|
{chr(10).join(rows)}

## Start Here

{chr(10).join(start_here) or "- [[Overview/Project Overview]]"}

---
*Generated by [repowiki](https://github.com/coentraojpt/repowiki-plugin)*
"""
    (output_dir / "index.md").write_text(content, encoding="utf-8")


def write_metadata(output_dir: Path, architecture: dict, manifest: dict):
    (output_dir / "_meta").mkdir(exist_ok=True)
    sections_data = []
    relations = []
    rel_id = 1

    for s in architecture["sections"]:
        sec_id = str(uuid.uuid4())
        pages_data = []
        for p in s["pages"]:
            pid = str(uuid.uuid4())
            safe = re.sub(r'[<>:"/\\|?*]', "-", p)
            pages_data.append({"id": pid, "title": p, "path": f"{s['output_dir']}/{safe}.md"})
            relations.append({"id": rel_id, "source_id": sec_id, "target_id": pid,
                               "source_type": "SECTION", "target_type": "PAGE",
                               "relationship_type": "PARENT_CHILD"})
            rel_id += 1
        sections_data.append({"id": sec_id, "title": s["title"],
                               "output_dir": s["output_dir"], "pages": pages_data})

    meta = {
        "wiki_version": "1.0.0",
        "generated": datetime.now(timezone.utc).isoformat(),
        "repo_name": manifest["repo_name"],
        "provider": manifest.get("provider", "unknown"),
        "model": manifest.get("model", "unknown"),
        "total_sections": len(architecture["sections"]),
        "total_pages": sum(len(s["pages"]) for s in architecture["sections"]),
        "sections": sections_data,
        "knowledge_relations": relations,
    }
    (output_dir / "_meta" / "repowiki-metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── Ollama auto-detection ─────────────────────────────────────────────────────

# Ranked preference — better models first
_PREFERRED_MODELS = [
    "gemma4:27b", "gemma4:9b", "qwen2.5:14b", "qwen2.5:7b",
    "llama3.1:70b", "llama3.1:8b", "phi4", "mistral",
    "gemma4", "llama3.2", "llama2",
]

OLLAMA_INSTALL = """
  Ollama not found. Install it (free, runs locally):

    https://ollama.com/download

  Then pull a model:

    ollama pull gemma4:9b

  And run repowiki again.
"""

OLLAMA_NO_MODELS = """
  Ollama is running but no models are installed.

  Pull one (pick any):

    ollama pull gemma4:9b      ← recommended
    ollama pull qwen2.5:7b     ← alternative
    ollama pull llama3.1:8b    ← alternative

  Then run repowiki again.
"""


def detect_ollama_model(host: str, preferred: str | None = None) -> str:
    """
    Auto-detect the best available Ollama model.
    Returns the model name to use, or raises RuntimeError with a helpful message.
    """
    try:
        req = urllib.request.Request(f"{host}/api/tags")
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError:
        raise RuntimeError(OLLAMA_INSTALL)
    except Exception as e:
        raise RuntimeError(f"  Could not reach Ollama at {host}: {e}")

    available = [m["name"] for m in data.get("models", [])]
    if not available:
        raise RuntimeError(OLLAMA_NO_MODELS)

    # If user specified a model, verify it's installed
    if preferred:
        for m in available:
            if m == preferred or m.startswith(preferred.split(":")[0]):
                return m
        raise RuntimeError(
            f"  Model '{preferred}' not installed.\n"
            f"  Available: {', '.join(available)}\n"
            f"  Install it: ollama pull {preferred}"
        )

    # Auto-select: prefer known good models in ranked order
    for candidate in _PREFERRED_MODELS:
        for m in available:
            if m == candidate or m.startswith(candidate.split(":")[0] + ":"):
                return m

    # Fallback: just use whatever is installed
    return available[0]


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="repowiki — convert any repo into an Obsidian wiki (runs locally, no API key)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py                          auto-detect model, output .repowiki/
  python cli.py --model gemma4:9b        use a specific model
  python cli.py --output docs/wiki       custom output directory
  python cli.py --lang pt                Portuguese output
  python cli.py --section "Database"     one section only
  python cli.py --dry-run                preview plan, no generation

First time? Install Ollama then pull a model:
  https://ollama.com/download
  ollama pull gemma4:9b
        """,
    )
    parser.add_argument("--repo", default=".", type=Path,
                        help="Repository path (default: current directory)")
    parser.add_argument("--output", default=".repowiki", type=Path,
                        help="Output directory (default: .repowiki)")
    parser.add_argument("--model", default=None,
                        help="Ollama model to use (default: auto-detect best available)")
    parser.add_argument("--host", default="http://localhost:11434",
                        help="Ollama URL (default: http://localhost:11434)")
    parser.add_argument("--lang", default="en", choices=["en", "pt"],
                        help="Output language (default: en)")
    parser.add_argument("--section", type=str, default=None,
                        help="Generate only one section by title")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show plan without generating content")
    parser.add_argument("--depth", default="medium",
                        choices=["shallow", "medium", "deep"],
                        help="Extraction depth: shallow (fastest, ~90%% token reduction), "
                             "medium (default, ~73%%), deep (full code)")
    # Advanced / hidden
    parser.add_argument("--provider", default="ollama",
                        choices=["ollama", "claude", "openai"],
                        help=argparse.SUPPRESS)
    args = parser.parse_args()

    repo_root = args.repo.resolve()
    output_dir = (
        repo_root / args.output
        if not args.output.is_absolute()
        else args.output
    )

    # ── Resolve model (unless using a non-ollama provider)
    sys.path.insert(0, str(Path(__file__).parent))
    from providers.provider import get_provider

    if args.provider == "ollama":
        try:
            model = detect_ollama_model(args.host, args.model)
        except RuntimeError as e:
            print(e)
            sys.exit(1)
    else:
        model = args.model or "default"

    print(f"\nrepowiki")
    print(f"  repo:    {repo_root}")
    print(f"  output:  {output_dir}")
    print(f"  model:   {model}")
    print(f"  lang:    {args.lang}")
    print(f"  depth:   {args.depth}\n")

    # ── Phase 1: Discovery
    print("[1/5] Scanning repository...")
    manifest = scan_repo(repo_root)
    manifest["provider"] = args.provider
    manifest["model"] = model
    print(f"      {manifest['total_files']} files · {manifest['language_primary']} "
          f"· {manifest['framework']} · complexity={manifest['complexity']}")
    if manifest["detected_patterns"]:
        print(f"      patterns: {', '.join(manifest['detected_patterns'])}")

    # ── Phase 2: Architecture
    print("\n[2/5] Planning wiki architecture...")
    architecture = plan_architecture(manifest, args.section)
    for s in architecture["sections"]:
        print(f"      → {s['title']:<35} {len(s['pages'])} page(s), "
              f"{len(s['key_files'])} key file(s)")

    if args.dry_run:
        print("\nDry run — no files written. Remove --dry-run to generate.")
        return

    if not architecture["sections"]:
        print("\nNo sections matched. Try without --section filter.")
        sys.exit(1)

    # ── Initialise provider
    try:
        provider = get_provider(args.provider, model=model, host=args.host)
    except RuntimeError as e:
        print(f"\n{e}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Phase 3: Extract code structure
    print("\n[3/5] Extracting code structure...")
    from extractor import extract_repo
    extracted = extract_repo(repo_root, architecture, args.depth, output_dir)
    print(f"      cached: {extracted['cache_hits']} files · extracted: {extracted['cache_misses']} files")

    # ── Phase 4: Generate
    print(f"\n[4/5] Generating wiki ({len(architecture['sections'])} sections)...")
    total_pages = 0

    for section in architecture["sections"]:
        print(f"      {section['title']}...", end=" ", flush=True)

        source_text = extracted["sections"].get(section["id"], "")
        if not source_text.strip():
            print("(no readable files — skipped)")
            continue

        prompt = build_prompt(section, source_text, args.lang, args.depth)
        try:
            response = provider.generate(prompt)
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        pages = parse_pages(response, section)
        written = 0
        for page_name, content in pages.items():
            if content.strip():
                write_page(output_dir, section["output_dir"], page_name, content)
                written += 1
                total_pages += 1
        print(f"{written} page(s) written")

    # ── Phase 5: Finalize
    print("\n[5/5] Finalizing...")
    write_index(output_dir, architecture, manifest)
    write_metadata(output_dir, architecture, manifest)

    print(f"\n✓ Done")
    print(f"  Sections: {len(architecture['sections'])}")
    print(f"  Pages:    {total_pages}")
    print(f"  Output:   {output_dir}/")
    print(f"\n  Open in Obsidian: Settings → Open vault → select \"{output_dir.name}/\"")
    print(f"  Start reading:    {output_dir}/index.md\n")


if __name__ == "__main__":
    main()
