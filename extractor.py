from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

_CACHE_VERSION = 1


def _md5(path: Path) -> str:
    try:
        return hashlib.md5(path.read_bytes()[:1_048_576]).hexdigest()[:8]  # cap at 1 MB for performance
    except Exception:
        return "00000000"


def _load_cache(cache_path: Path) -> dict:
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if data.get("version") == _CACHE_VERSION and data.get("patterns_hash") == _PATTERNS_HASH:
            return data
    except Exception:
        pass
    return {"version": _CACHE_VERSION, "patterns_hash": _PATTERNS_HASH, "entries": {}}


def _save_cache(cache_path: Path, cache: dict) -> None:
    cache_path.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8"
    )


_REGEX_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "js": [
        (r"^export\s+(?:default\s+)?class\s+(\w+)", "class"),
        (r"^class\s+(\w+)", "class"),
        (r"^export\s+(?:default\s+)?function\s+(\w+)", "function"),
        (r"^(?:async\s+)?function\s+(\w+)", "function"),
        (r"^(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(", "arrow-fn"),
        (r"^import\s+.+\s+from\s+['\"](.+)['\"]", "import"),
    ],
    "ts": [
        (r"^export\s+(?:default\s+)?(?:abstract\s+)?class\s+(\w+)", "class"),
        (r"^export\s+interface\s+(\w+)", "interface"),
        (r"^export\s+type\s+(\w+)", "type"),
        (r"^export\s+enum\s+(\w+)", "enum"),
        (r"^export\s+(?:async\s+)?function\s+(\w+)", "function"),
        (r"^(?:async\s+)?function\s+(\w+)", "function"),
        (r"^import\s+.+\s+from\s+['\"](.+)['\"]", "import"),
    ],
    "go": [
        (r"^type\s+(\w+)\s+struct\s*\{", "struct"),
        (r"^type\s+(\w+)\s+interface\s*\{", "interface"),
        (r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(", "func"),
    ],
    "rb": [
        (r"^(?:class|module)\s+(\w+)", "class"),
        (r"^\s*def\s+(\w+)", "method"),
    ],
    "java": [
        (r"^(?:public\s+|private\s+|protected\s+)?(?:abstract\s+)?(?:class|interface|enum)\s+(\w+)", "class"),
        (r"^\s*(?:public|private|protected)\s+\S+\s+(\w+)\s*\(", "method"),
    ],
    "kt": [
        (r"^(?:data\s+|sealed\s+)?class\s+(\w+)", "class"),
        (r"^(?:fun)\s+(\w+)", "func"),
        (r"^interface\s+(\w+)", "interface"),
    ],
    "rs": [
        (r"^(?:pub\s+)?struct\s+(\w+)", "struct"),
        (r"^(?:pub\s+)?enum\s+(\w+)", "enum"),
        (r"^(?:pub\s+)?fn\s+(\w+)", "fn"),
        (r"^impl(?:\s+\w+\s+for)?\s+(\w+)", "impl"),
    ],
    "php": [
        (r"^(?:class|interface|trait)\s+(\w+)", "class"),
        (r"^\s*(?:public|private|protected)\s+function\s+(\w+)", "method"),
    ],
}

_GENERIC_PATTERNS: list[tuple[str, str]] = [
    (r"^(?:class|def|fn|func|function)\s+(\w+)", "symbol"),
]

_PATTERNS_HASH: str = hashlib.md5(
    json.dumps(_REGEX_PATTERNS, sort_keys=True).encode()
).hexdigest()[:8]


def _extract_regex(file_path: Path, depth: str, lang: str) -> str:
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return f"# {file_path.name} [unreadable]"

    patterns = _REGEX_PATTERNS.get(lang, _GENERIC_PATTERNS)
    out = [f"# {file_path.name} [{lang} · {depth}]"]
    seen: set[str] = set()  # dedup by "kind: name" — same symbol in multiple scopes emits once

    for line in source.splitlines():
        stripped = line.strip()
        for pattern, kind in patterns:
            m = re.match(pattern, stripped)
            if m:
                entry = f"{kind}: {m.group(1)}"
                if entry not in seen:
                    out.append(entry)
                    seen.add(entry)
                break

    if len(out) == 1:
        out.append("(no symbols found)")
    return "\n".join(out)


def _field_abbr(fname: str, call: ast.Call) -> str:
    fk_types = {"ForeignKey", "OneToOneField", "ManyToManyField"}
    if fname in fk_types and call.args:
        a = call.args[0]
        target = (a.id if isinstance(a, ast.Name) else
                  a.value if isinstance(a, ast.Constant) else "?")
        return f"FK→{target}"
    abbr = {
        "CharField": "char", "TextField": "text", "IntegerField": "int",
        "FloatField": "float", "BooleanField": "bool", "DateTimeField": "datetime",
        "DateField": "date", "EmailField": "email", "DecimalField": "decimal",
        "JSONField": "json", "UUIDField": "uuid", "URLField": "url",
    }
    return abbr.get(fname, fname)


def _ann_str(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return f"{_ann_str(node.value)}[...]"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return "?"


def _extract_python(file_path: Path, depth: str) -> str:
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
        lines = source.splitlines()
    except Exception:
        return _extract_regex(file_path, depth, "py")

    out = [f"# {file_path.name} [python · {depth}]"]

    if depth == "shallow":
        mods: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods.append(node.module)
        if mods:
            out.append(f"imports: {', '.join(mods[:8])}")

    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        bases = []
        for b in node.bases:
            if isinstance(b, ast.Name):
                bases.append(b.id)
            elif isinstance(b, ast.Attribute):
                bases.append(b.attr)
        base_str = f"({', '.join(bases)})" if bases else ""
        out.append(f"\nclass {node.name}{base_str}:")

        fields: list[str] = []
        for child in node.body:
            if isinstance(child, ast.Assign):
                for t in child.targets:
                    if not isinstance(t, ast.Name):
                        continue
                    if isinstance(child.value, ast.Call):
                        func = child.value.func
                        fname = (func.attr if isinstance(func, ast.Attribute)
                                 else func.id if isinstance(func, ast.Name) else "")
                        if depth == "shallow":
                            fields.append(f"{t.id}({_field_abbr(fname, child.value)})")
                        else:
                            fields.append(f"{t.id}({fname})")
                    else:
                        fields.append(t.id)
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                fields.append(f"{child.target.id}: {_ann_str(child.annotation)}")

        if fields:
            out.append(f"  fields: {', '.join(fields)}")

        methods = [
            c for c in node.body
            if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        if depth == "shallow" and methods:
            out.append(f"  methods: {', '.join(m.name + '()' for m in methods)}")
        elif depth == "medium":
            for m in methods:
                decs = []
                for dec in m.decorator_list:
                    if isinstance(dec, ast.Name):
                        decs.append(f"  @{dec.id}")
                    elif isinstance(dec, ast.Attribute):
                        decs.append(f"  @{dec.attr}")
                    elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                        decs.append(f"  @{dec.func.id}(...)")
                    elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        decs.append(f"  @{dec.func.attr}(...)")
                out.extend(decs)

                args = [a.arg for a in m.args.args if a.arg != "self"][:4]
                sig = f"self, {', '.join(args)}" if args else "self"
                out.append(f"\n  def {m.name}({sig}):")

                doc = ast.get_docstring(m)
                if doc:
                    out.append(f'    """{doc.splitlines()[0]}"""')

                body_nodes = list(m.body)
                # Skip docstring node (Expr containing a Constant string)
                if (body_nodes
                        and isinstance(body_nodes[0], ast.Expr)
                        and isinstance(getattr(body_nodes[0], "value", None), ast.Constant)
                        and isinstance(body_nodes[0].value.value, str)):
                    body_nodes = body_nodes[1:]

                preview = 0
                for bn in body_nodes:
                    if preview >= 5:
                        break
                    start = bn.lineno - 1
                    end = getattr(bn, "end_lineno", bn.lineno)
                    for raw in lines[start:end]:
                        if raw.strip():
                            out.append(f"  {raw.rstrip()}")
                            preview += 1
                            if preview >= 5:
                                break

    # Standalone module-level functions
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        args = [a.arg for a in node.args.args if a.arg != "self"][:4]
        sig = ", ".join(args)

        if depth == "shallow":
            out.append(f"\ndef {node.name}({sig}):")
        else:  # medium
            decs = []
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name):
                    decs.append(f"@{dec.id}")
                elif isinstance(dec, ast.Attribute):
                    decs.append(f"@{dec.attr}")
                elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                    decs.append(f"@{dec.func.id}(...)")
                elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    decs.append(f"@{dec.func.attr}(...)")
            for d in decs:
                out.append(d)

            out.append(f"\ndef {node.name}({sig}):")

            doc = ast.get_docstring(node)
            if doc:
                out.append(f'  """{doc.splitlines()[0]}"""')

            body_nodes = list(node.body)
            if (body_nodes
                    and isinstance(body_nodes[0], ast.Expr)
                    and isinstance(getattr(body_nodes[0], "value", None), ast.Constant)
                    and isinstance(body_nodes[0].value.value, str)):
                body_nodes = body_nodes[1:]

            preview = 0
            for bn in body_nodes:
                if preview >= 5:
                    break
                start = bn.lineno - 1
                end = getattr(bn, "end_lineno", bn.lineno)
                for raw in lines[start:end]:
                    if raw.strip():
                        out.append(f"  {raw.rstrip()}")
                        preview += 1
                        if preview >= 5:
                            break

    return "\n".join(out)


_LANG_MAP: dict[str, str] = {
    ".py": "py", ".js": "js", ".jsx": "js", ".ts": "ts", ".tsx": "ts",
    ".go": "go", ".rb": "rb", ".java": "java", ".kt": "kt",
    ".rs": "rs", ".php": "php",
}


def extract_file(file_path: Path, depth: str) -> str:
    """Single-file dispatcher. Routes to _extract_python, _extract_regex, or raw read."""
    if depth == "deep":
        try:
            return file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""

    suffix = file_path.suffix.lower()
    lang = _LANG_MAP.get(suffix, "generic")

    if suffix == ".py":
        return _extract_python(file_path, depth)
    return _extract_regex(file_path, depth, lang)


def extract_repo(repo_root: Path, architecture: dict, depth: str, output_dir: Path) -> dict:
    """
    Extract code structure for all sections defined in architecture.

    Returns:
      {
        "sections": {section_id: compressed_text_str},
        "cache_hits": int,
        "cache_misses": int,
      }
    """
    cache_path = output_dir / ".extract_cache.json"
    cache = _load_cache(cache_path)
    entries = cache.setdefault("entries", {})
    cache["patterns_hash"] = _PATTERNS_HASH

    hits = 0
    misses = 0
    sections_text: dict[str, str] = {}

    for section in architecture["sections"]:
        parts: list[str] = []
        for rel in section["key_files"]:
            fp = repo_root / rel
            if not fp.exists():
                continue

            if depth == "deep":
                # Deep mode: bypass cache — read raw each time
                raw = extract_file(fp, "deep")
                if raw:
                    parts.append(f"\n### {rel}\n```\n{raw[:3000]}\n```")
                continue

            current_hash = _md5(fp)
            entry = entries.get(rel, {})

            if entry.get("hash") == current_hash and depth in entry:
                parts.append(entry[depth])
                hits += 1
            else:
                extracted = extract_file(fp, depth)
                entries[rel] = {**entry, "hash": current_hash, depth: extracted}
                parts.append(extracted)
                misses += 1

        sections_text[section["id"]] = "\n\n".join(parts)

    if misses > 0:
        output_dir.mkdir(parents=True, exist_ok=True)
        _save_cache(cache_path, cache)

    return {"sections": sections_text, "cache_hits": hits, "cache_misses": misses}


if __name__ == "__main__":
    import argparse as _argparse

    _p = _argparse.ArgumentParser(description="repowiki pre-extractor — compress source files into structural text")
    _p.add_argument("--repo", type=Path, default=Path("."), help="Repository root (default: .)")
    _p.add_argument("--arch", type=Path, required=True, help="Path to _architecture.json")
    _p.add_argument("--output", type=Path, default=Path(".repowiki"), help="Output directory (default: .repowiki)")
    _p.add_argument("--depth", choices=["shallow", "medium", "deep"], default="medium",
                    help="Extraction depth (default: medium)")
    _a = _p.parse_args()

    _repo_root = _a.repo.resolve()
    _arch_data = json.loads(_a.arch.read_text(encoding="utf-8"))
    _result = extract_repo(_repo_root, _arch_data, _a.depth, _a.output)

    # Write each section's extracted text to .tmp/extracted/<section_id>.txt
    _sections_dir = _a.output / ".tmp" / "extracted"
    _sections_dir.mkdir(parents=True, exist_ok=True)
    for _sid, _text in _result["sections"].items():
        (_sections_dir / f"{_sid}.txt").write_text(_text, encoding="utf-8")

    print(
        f"Extracted {len(_result['sections'])} section(s) · "
        f"cache hits: {_result['cache_hits']} · misses: {_result['cache_misses']}"
    )
    print(f"Output: {_sections_dir}/")
