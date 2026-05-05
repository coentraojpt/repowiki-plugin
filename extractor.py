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
        if data.get("version") == _CACHE_VERSION:
            return data
    except Exception:
        pass
    return {"version": _CACHE_VERSION, "entries": {}}


def _save_cache(cache_path: Path, cache: dict) -> None:
    cache_path.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _extract_regex(file_path: Path, depth: str, lang: str) -> str:
    """Stub — replaced in Task 4."""
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return f"# {file_path.name} [unreadable]"
    # Minimal generic fallback: find class/def lines
    lines = [f"# {file_path.name} [{lang} · {depth}]"]
    for line in source.splitlines():
        m = re.match(r"^(class|def)\s+(\w+)", line.strip())
        if m:
            lines.append(f"{m.group(1)}: {m.group(2)}")
    return "\n".join(lines) if len(lines) > 1 else lines[0] + "\n(no symbols found)"


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
                        fields.append(f"{t.id}({_field_abbr(fname, child.value)})")
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

    return "\n".join(out)
