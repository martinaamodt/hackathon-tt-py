"""
Generic import mapping module.

Loads a project-specific tt_import_map.json config and maps
TypeScript imports to Python import statements.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def load_import_map(config_path: Path) -> dict:
    """Load import mapping configuration from JSON file."""
    with open(config_path) as f:
        return json.load(f)


def _match_wildcard(module: str, pattern: str) -> bool:
    """Check if a module path matches a wildcard pattern like '@scope/*'."""
    if "*" not in pattern:
        return module == pattern
    regex = re.escape(pattern).replace(r"\*", ".*")
    return re.fullmatch(regex, module) is not None


def _find_mapping(module: str, import_map: dict) -> dict | None:
    """Find the best mapping for a module path.

    Checks exact matches first, then wildcard patterns,
    then skip_patterns.
    """
    imports = import_map.get("imports", {})

    # Exact match
    if module in imports:
        return imports[module]

    # Check skip_patterns
    skip_patterns = import_map.get("skip_patterns", [])
    for pattern in skip_patterns:
        if module == pattern or module.startswith(pattern + "/"):
            return {"python_module": None, "skip": True}

    # Wildcard match (longest pattern wins)
    best_match = None
    best_len = 0
    for pattern, mapping in imports.items():
        if "*" in pattern and _match_wildcard(module, pattern):
            if len(pattern) > best_len:
                best_match = mapping
                best_len = len(pattern)

    return best_match


def map_imports(ts_imports: list[dict], import_map: dict) -> list[str]:
    """Convert TypeScript imports to Python import statements.

    ts_imports: list of {"module": str, "names": list[str]} parsed from TS
    import_map: the loaded config with import mappings

    Returns list of Python import lines.
    """
    result: list[str] = []

    for ts_import in ts_imports:
        module = ts_import.get("module", "")
        names = ts_import.get("names", [])
        mapping = _find_mapping(module, import_map)

        if mapping is None:
            continue
        if mapping.get("skip"):
            continue
        if mapping.get("inline"):
            continue

        py_module = mapping.get("python_module")
        if not py_module:
            continue

        name_map = mapping.get("names", {})
        py_names = _resolve_names(names, name_map)

        if py_names:
            result.append(f"from {py_module} import {', '.join(py_names)}")

    return result


def _resolve_names(ts_names: list[str], name_map: dict) -> list[str]:
    """Resolve TypeScript import names to Python names using the name map."""
    resolved: list[str] = []
    for name in ts_names:
        if name in name_map:
            py_name = name_map[name]
            if py_name:
                resolved.append(py_name)
        else:
            # Pass through unmapped names as-is
            resolved.append(name)
    return resolved


def get_files_to_translate(import_map: dict, project_root: Path) -> list[dict]:
    """Get list of TypeScript files to translate from config.

    Returns list of {"source": Path, "output": Path, "role": str} dicts.
    """
    source_root = import_map.get("source_root", "")
    output_root = import_map.get("output_root", "")
    files = import_map.get("files", [])

    result: list[dict] = []
    for entry in files:
        source = project_root / source_root / entry["source"]
        output = project_root / output_root / entry["output"]
        result.append({
            "source": source,
            "output": output,
            "role": entry.get("role", ""),
        })

    return result


def get_constants(import_map: dict) -> dict[str, object]:
    """Extract inlined constants from import mappings.

    Some TS modules export constants that we inline directly
    rather than importing. Returns a flat dict of constant_name -> value.
    """
    constants: dict[str, object] = {}
    imports = import_map.get("imports", {})

    for mapping in imports.values():
        if "constants" in mapping:
            constants.update(mapping["constants"])

    return constants
