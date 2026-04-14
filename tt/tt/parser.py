"""Parse TypeScript source code into a tree-sitter AST."""
from __future__ import annotations

import tree_sitter_typescript as ts_typescript
from tree_sitter import Language, Parser

TS_LANGUAGE = Language(ts_typescript.language_typescript())


def parse(source: str):
    """Parse TypeScript source string and return a tree-sitter Tree."""
    parser = Parser(TS_LANGUAGE)
    return parser.parse(source.encode("utf-8"))
