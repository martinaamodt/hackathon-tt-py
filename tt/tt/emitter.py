"""
Python code emitter — walks a tree-sitter TypeScript AST and produces Python.

PythonEmitter composes StmtMixin (statement visitors) and ExprMixin (expression
translators). This file contains only the core state and utility methods shared
by both mixins.
"""
from __future__ import annotations

import re
from tree_sitter import Node

from .emitter_stmt import StmtMixin
from .emitter_expr import ExprMixin


class PythonEmitter(StmtMixin, ExprMixin):
    """Walks a tree-sitter TypeScript AST and emits Python code."""

    def __init__(self, source: bytes, import_map: dict | None = None):
        self.source = source
        self.import_map = import_map or {}
        self.indent = 0
        self.lines: list[str] = []
        self._in_class = False
        self._class_name = ""
        self._base_class = ""
        self._class_fields: list[tuple[str, str]] = []
        self._imports_needed: set[str] = set()
        self._method_names: list[str] = []

    def text(self, node: Node) -> str:
        """Get source text for a node."""
        return self.source[node.start_byte : node.end_byte].decode("utf-8")

    def emit(self, tree) -> str:
        """Emit Python code from a tree-sitter AST."""
        self._visit_program(tree.root_node)
        return "\n".join(self.lines)

    def _line(self, text: str) -> None:
        """Append an indented line."""
        if text.strip() == "":
            self.lines.append("")
        else:
            self.lines.append("    " * self.indent + text)

    def _blank(self) -> None:
        """Append a blank line if the last line isn't already blank."""
        if self.lines and self.lines[-1].strip() != "":
            self.lines.append("")

    @staticmethod
    def _to_snake_case(name: str) -> str:
        """Convert camelCase or PascalCase to snake_case."""
        if not name:
            return name
        if name.startswith("_") and name[1:2].islower():
            return name
        if name.isupper() or "_" in name:
            return name
        result = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        result = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", result)
        return result.lower()

    @staticmethod
    def _to_camel_case(name: str) -> str:
        """Convert snake_case back to camelCase."""
        parts = name.split("_")
        if len(parts) <= 1:
            return name
        return parts[0] + "".join(p.capitalize() for p in parts[1:])

    @staticmethod
    def _strip_parens(s: str) -> str:
        """Strip outer parentheses from a string."""
        s = s.strip()
        if s.startswith("(") and s.endswith(")"):
            depth = 0
            for i, c in enumerate(s):
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                if depth == 0 and i < len(s) - 1:
                    return s
            return s[1:-1]
        return s
