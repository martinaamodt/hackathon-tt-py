"""
Tree-sitter based TypeScript parser.

Provides a thin wrapper around tree-sitter-typescript for parsing
TypeScript source files into ASTs that the emitter can walk.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser, Node, Tree


TS_LANGUAGE = Language(tsts.language_typescript())


def create_parser() -> Parser:
    """Create a tree-sitter parser configured for TypeScript."""
    parser = Parser(TS_LANGUAGE)
    return parser


def parse_code(code: str) -> Tree:
    """Parse a TypeScript source string and return the AST."""
    parser = create_parser()
    return parser.parse(bytes(code, "utf-8"))


def parse_file(path: Path) -> tuple[Tree, bytes]:
    """Parse a TypeScript file and return (tree, source_bytes)."""
    source = path.read_bytes()
    parser = create_parser()
    tree = parser.parse(source)
    return tree, source


def node_text(node: Node, source: bytes) -> str:
    """Extract the source text for an AST node."""
    return source[node.start_byte : node.end_byte].decode("utf-8")


def dump_ast(node: Node, source: bytes, indent: int = 0) -> str:
    """Debug helper: dump the AST as an indented tree."""
    lines = []
    text = node_text(node, source)
    short_text = (
        text[:60].replace("\n", "\\n")
        if len(text) < 80
        else text[:60].replace("\n", "\\n") + "..."
    )
    lines.append(
        f"{'  ' * indent}{node.type} [{node.start_point[0]}:{node.start_point[1]}] = {short_text!r}"
    )
    for child in node.children:
        lines.append(dump_ast(child, source, indent + 1))
    return "\n".join(lines)


def find_nodes(node: Node, type_name: str) -> list[Node]:
    """Recursively find all nodes of a given type."""
    results = []
    if node.type == type_name:
        results.append(node)
    for child in node.children:
        results.extend(find_nodes(child, type_name))
    return results


def find_first(node: Node, type_name: str) -> Node | None:
    """Find the first node of a given type (depth-first)."""
    if node.type == type_name:
        return node
    for child in node.children:
        result = find_first(child, type_name)
        if result:
            return result
    return None
