"""
AST-based TypeScript to Python translator.

Uses tree-sitter to parse TypeScript source files and generates
Python code via recursive AST walking. Project-specific configuration
(import mappings, file lists) is loaded from tt_import_map.json
in the scaffold directory.
"""
from __future__ import annotations

from pathlib import Path

from tt.codegen import generate
from tt.import_mapper import (
    get_files_to_translate,
    load_import_map,
    map_imports,
)
from tt.parser import parse


def _extract_imports(source: str, tree) -> list[dict]:
    """Extract import information from a parsed TypeScript AST."""
    imports: list[dict] = []
    for child in tree.root_node.children:
        if child.type == "import_statement":
            _parse_import_node(source, child, imports)
    return imports


def _parse_import_node(source: str, node, imports: list[dict]) -> None:
    """Parse a single import statement node into module + names."""
    source_node = node.child_by_field_name("source")
    if source_node is None:
        return
    module = source_node.text.decode("utf-8").strip("'\"")
    names: list[str] = []
    for child in node.children:
        if child.type == "import_clause":
            for sub in child.children:
                if sub.type == "named_imports":
                    for spec in sub.children:
                        if spec.type == "import_specifier":
                            name_node = spec.child_by_field_name("name")
                            if name_node:
                                names.append(name_node.text.decode("utf-8"))
    imports.append({"module": module, "names": names})


def translate_file(ts_path: Path, import_map: dict) -> str:
    """Translate a single TypeScript file to Python.

    Reads TS source, parses with tree-sitter, generates Python,
    and prepends mapped imports.
    """
    source = ts_path.read_text(encoding="utf-8")
    source_bytes = source.encode("utf-8")
    tree = parse(source)

    # Extract and map imports
    ts_imports = _extract_imports(source, tree)
    python_imports = map_imports(ts_imports, import_map)

    # Generate Python code from AST
    python_code = generate(source_bytes, tree.root_node)

    # Combine imports + generated code
    parts: list[str] = []
    if python_imports:
        parts.append("\n".join(python_imports))
        parts.append("")
    parts.append(python_code)

    return "\n".join(parts)


def run_translation(repo_root: Path, output_dir: Path) -> None:
    """Run the full translation pipeline.

    Reads tt_import_map.json from the scaffold directory,
    translates each configured file, and writes output.
    """
    config_path = (
        Path(__file__).parent / "scaffold" / "ghostfolio_pytx" / "tt_import_map.json"
    )
    if not config_path.exists():
        print(f"Warning: config not found: {config_path}")
        return

    import_map = load_import_map(config_path)
    files = get_files_to_translate(import_map, repo_root)

    for file_info in files:
        source = file_info["source"]
        output = file_info["output"]

        if not source.exists():
            print(f"  Warning: source not found: {source}")
            continue

        print(f"  Translating {source.name} -> {output.name}")
        python_code = translate_file(source, import_map)

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(python_code, encoding="utf-8")
        print(f"    Wrote {output}")

    # Post-process: apply the interface bridge
    _apply_bridge(repo_root, output_dir, import_map)


def _apply_bridge(repo_root: Path, output_dir: Path, import_map: dict) -> None:
    """Post-process translated files to wire up the Python interface.

    The translated calculator needs to implement the abstract interface
    expected by the wrapper layer. This reads the translated output
    and wraps it to match the required API.
    """
    bridge_path = Path(__file__).parent / "bridge.py"
    if not bridge_path.exists():
        return

    # The bridge module handles rewriting the calculator to match
    # the wrapper's expected interface
    from tt.bridge import apply_bridge
    apply_bridge(repo_root, output_dir, import_map)
