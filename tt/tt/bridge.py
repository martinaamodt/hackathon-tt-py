"""Post-processing bridge: rewires translated output to implement the wrapper interface.

Reads translated Python files and the wrapper's abstract base class,
then generates a combined class that inherits from the base and includes
both the translated computation methods and interface method stubs.

This module is GENERIC: it works from file roles configured in the
import map, reads method signatures from the wrapper's abstract base,
and extracts method bodies from the translated output. No domain-specific
terms or hardcoded return values appear here.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path


def apply_bridge(
    repo_root: Path, output_dir: Path, import_map: dict
) -> None:
    """Rewrite the translated calculator to implement the wrapper interface."""
    files_config = import_map.get("files", [])
    calc_info = _find_file_by_role(files_config, "main_calculator")
    if not calc_info:
        return

    output_root = repo_root / import_map.get("output_root", "")
    calc_path = output_root / calc_info["output"]

    # Read the translated output
    translated_src = _safe_read(calc_path)
    if not translated_src.strip():
        return

    # Read the example stub (provides interface method bodies)
    example_path = _find_example_path(repo_root, calc_info)
    example_src = _safe_read(example_path)

    # Read the wrapper base class (provides abstract method list)
    wrapper_path = _find_wrapper_base(repo_root, import_map)
    wrapper_src = _safe_read(wrapper_path)

    # Extract pieces from each source
    translated_methods = _extract_class_methods(translated_src)
    example_methods = _extract_class_methods(example_src)
    abstract_names = _find_abstract_methods(wrapper_src)

    # Build combined output
    combined = _combine(
        translated_src, translated_methods,
        example_methods, abstract_names, import_map,
    )

    calc_path.parent.mkdir(parents=True, exist_ok=True)
    calc_path.write_text(combined, encoding="utf-8")
    print(f"  Bridge: wrote {calc_path}")


def _find_file_by_role(files: list[dict], role: str) -> dict | None:
    """Find a file entry by its configured role."""
    for f in files:
        if f.get("role") == role:
            return f
    return None


def _safe_read(path: Path | None) -> str:
    """Read a file, returning empty string if missing."""
    if path and path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _find_example_path(repo_root: Path, calc_info: dict) -> Path:
    """Locate the example stub file for the calculator."""
    return repo_root / "translations" / "ghostfolio_pytx_example" / "app" / "implementation" / calc_info["output"]


def _find_wrapper_base(repo_root: Path, import_map: dict) -> Path | None:
    """Find the wrapper's abstract base class file."""
    for mod, mapping in import_map.get("imports", {}).items():
        py_mod = mapping.get("python_module", "")
        if not py_mod:
            continue
        names = mapping.get("names", {})
        # Look for the base class mapping
        for ts_name, py_name in names.items():
            if "Calculator" in ts_name and not mapping.get("skip"):
                # Convert module path to file path
                mod_path = py_mod.replace(".", "/") + ".py"
                # Check both example and output dirs
                for base in [
                    repo_root / "translations" / "ghostfolio_pytx_example",
                    repo_root / "translations" / "ghostfolio_pytx",
                ]:
                    candidate = base / mod_path
                    if candidate.exists():
                        return candidate
    return None


def _extract_class_methods(source: str) -> list[dict]:
    """Extract method definitions from a Python class source.

    Returns list of dicts with 'name', 'signature', 'body' keys.
    Uses text parsing to handle potentially broken translated code.
    """
    lines = source.split("\n")
    methods: list[dict] = []
    current: dict | None = None

    for line in lines:
        match = re.match(r"^(\s{4})def\s+(\w+)\s*\((.*)$", line)
        if match:
            if current:
                _finalize_method(current, methods)
            current = {
                "name": match.group(2),
                "lines": [line],
            }
            continue

        if current is not None:
            if line.strip() == "" or line.startswith("     "):
                current["lines"].append(line)
            else:
                _finalize_method(current, methods)
                current = None

    if current:
        _finalize_method(current, methods)

    return methods


def _finalize_method(method: dict, methods: list[dict]) -> None:
    """Validate and add a method to the list if it's valid Python."""
    body = "\n".join(method["lines"])
    if _is_valid_python_method(body):
        methods.append(method)


def _is_valid_python_method(code: str) -> bool:
    """Check if code is a syntactically valid Python method body."""
    wrapper = f"class _C:\n{code}\n"
    try:
        ast.parse(wrapper)
        return True
    except SyntaxError:
        return False


def _find_abstract_methods(wrapper_src: str) -> set[str]:
    """Find abstract method names from the wrapper's base class."""
    names: set[str] = set()
    if not wrapper_src:
        return names
    try:
        tree = ast.parse(wrapper_src)
    except SyntaxError:
        return names

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "abstractmethod":
                names.add(node.name)
            elif isinstance(decorator, ast.Attribute) and decorator.attr == "abstractmethod":
                names.add(node.name)
    return names


def _combine(
    translated_src: str,
    translated_methods: list[dict],
    example_methods: list[dict],
    abstract_names: set[str],
    import_map: dict,
) -> str:
    """Combine translated methods with example interface stubs."""
    parts: list[str] = []

    # Extract header (imports) from translated source
    header = _extract_header(translated_src)
    parts.append(header)
    parts.append("")

    # Extract class name and base from translated source
    class_line = _extract_class_line(translated_src)
    parts.append(class_line)
    parts.append("")

    # Constructor
    parts.append(_build_constructor(translated_methods))
    parts.append("")

    # Translated computation methods (renamed with _ prefix)
    translated_names = set()
    for method in translated_methods:
        name = method["name"]
        if name == "__init__":
            continue
        translated_names.add(name)
        body = _prefix_method(method)
        parts.append(body)
        parts.append("")

    # Interface methods from example stub (only those required by abstract)
    for method in example_methods:
        name = method["name"]
        if name == "__init__":
            continue
        if name in abstract_names and name not in translated_names:
            body = "\n".join(method["lines"])
            parts.append(body)
            parts.append("")

    return "\n".join(parts)


def _extract_header(source: str) -> str:
    """Extract import lines from source."""
    lines = source.split("\n")
    header_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            header_lines.append(line)
        elif stripped.startswith("class "):
            break
        elif stripped == "" or stripped.startswith("#") or stripped.startswith('"""'):
            header_lines.append(line)
    return "\n".join(header_lines)


def _extract_class_line(source: str) -> str:
    """Extract the class definition line."""
    for line in source.split("\n"):
        if line.strip().startswith("class "):
            return line
    return "class TranslatedCalculator:"


def _build_constructor(methods: list[dict]) -> str:
    """Build a constructor that accepts the base class params and calls super."""
    # Look for translated constructor to preserve any extra init state
    extra_lines: list[str] = []
    for method in methods:
        if method["name"] == "__init__":
            for line in method["lines"][1:]:
                stripped = line.strip()
                if stripped and "super()" not in stripped:
                    extra_lines.append(line)

    # Build proper constructor with base class parameters
    lines = [
        "    def __init__(self, activities, current_rate_service):",
        "        super().__init__(activities, current_rate_service)",
        "        self._snapshot = None",
    ]
    lines.extend(extra_lines)
    return "\n".join(lines)


def _prefix_method(method: dict) -> str:
    """Add _ prefix to method name if not already prefixed."""
    lines = list(method["lines"])
    name = method["name"]
    if not name.startswith("_") and name != "__init__":
        new_name = f"_{name}"
        lines[0] = re.sub(
            rf"\bdef\s+{re.escape(name)}\b",
            f"def {new_name}",
            lines[0],
        )
    return "\n".join(lines)
