"""
Python code emitter — walks a tree-sitter TypeScript AST and produces Python.

This is the core of the translation tool. It handles:
- Class/method structure → Python class/def
- Big.js operations → Decimal arithmetic
- TypeScript types → stripped
- date-fns helpers → Python datetime equivalents
- Lodash helpers → Python builtins
- Control flow → Python equivalents
- Optional chaining, nullish coalescing, destructuring
"""

from __future__ import annotations

import re
from tree_sitter import Node


# Big.js method → Python operator/function mapping
BIG_METHODS = {
    "plus": "+",
    "add": "+",
    "minus": "-",
    "sub": "-",
    "mul": "*",
    "times": "*",
    "div": "/",
    "mod": "%",
}

BIG_COMPARISONS = {
    "eq": "==",
    "gt": ">",
    "lt": "<",
    "gte": ">=",
    "lte": "<=",
}

# date-fns function → Python equivalent
DATE_FUNCTIONS = {
    "differenceInDays",
    "format",
    "isBefore",
    "isAfter",
    "addMilliseconds",
    "eachDayOfInterval",
    "eachYearOfInterval",
    "endOfDay",
    "startOfDay",
    "endOfYear",
    "startOfYear",
    "startOfMonth",
    "startOfWeek",
    "subDays",
    "subYears",
    "min",
    "max",
    "isThisYear",
    "isWithinInterval",
    "resetHours",
    "parseDate",
    "isNumber",
    "isFinite",
}


class PythonEmitter:
    """Walks a tree-sitter TypeScript AST and emits Python code."""

    def __init__(self, source: bytes, import_map: dict | None = None):
        self.source = source
        self.import_map = import_map or {}
        self.indent = 0
        self.lines: list[str] = []
        self._in_class = False
        self._class_name = ""
        self._base_class = ""
        self._class_fields: list[tuple[str, str]] = []  # (name, default)
        self._imports_needed: set[str] = set()
        self._method_names: list[str] = []
        self._skip_export = False

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

    # -----------------------------------------------------------------------
    # Top-level visitors
    # -----------------------------------------------------------------------

    def _visit_program(self, node: Node) -> None:
        for child in node.named_children:
            self._visit_stmt(child)

    def _visit_stmt(self, node: Node) -> None:
        """Dispatch a statement node."""
        t = node.type

        if t == "export_statement":
            # Unwrap export and visit the inner declaration
            for child in node.named_children:
                self._visit_stmt(child)

        elif t == "class_declaration":
            self._visit_class(node)

        elif t == "import_statement":
            # Skip TS imports — we generate our own
            pass

        elif t in ("lexical_declaration", "variable_declaration"):
            self._visit_var_decl(node)

        elif t == "expression_statement":
            expr = node.named_children[0] if node.named_children else None
            if expr:
                code = self._expr(expr)
                if code and not code.startswith("#"):
                    self._line(code)

        elif t == "if_statement":
            self._visit_if(node)

        elif t == "for_in_statement":
            self._visit_for_in(node)

        elif t == "for_statement":
            self._visit_for(node)

        elif t == "while_statement":
            self._visit_while(node)

        elif t == "return_statement":
            self._visit_return(node)

        elif t == "break_statement":
            self._line("break")

        elif t == "continue_statement":
            self._line("continue")

        elif t == "switch_statement":
            self._visit_switch(node)

        elif t == "try_statement":
            self._visit_try(node)

        elif t == "throw_statement":
            expr = node.named_children[0] if node.named_children else None
            self._line(f"raise Exception({self._expr(expr) if expr else ''})")

        elif t == "type_alias_declaration":
            # Skip type aliases
            pass

        elif t == "interface_declaration":
            # Skip interfaces
            pass

        elif t == "enum_declaration":
            self._visit_enum(node)

        elif t == "function_declaration":
            self._visit_function(node)

        elif t == "empty_statement":
            pass

        elif t == "comment":
            text = self.text(node).strip()
            if text.startswith("//"):
                self._line(f"# {text[2:].strip()}")
            elif text.startswith("/*"):
                content = text[2:-2].strip()
                for line in content.split("\n"):
                    line = line.strip().lstrip("* ")
                    if line:
                        self._line(f"# {line}")

        elif t == "statement_block":
            self._visit_block(node)

        else:
            # Fallback: try as expression
            code = self._expr(node)
            if code:
                self._line(code)

    def _visit_block(self, node: Node) -> None:
        """Visit children of a statement_block (skip braces)."""
        for child in node.named_children:
            self._visit_stmt(child)

    # -----------------------------------------------------------------------
    # Class
    # -----------------------------------------------------------------------

    def _visit_class(self, node: Node) -> None:
        name_node = node.child_by_field_name("name")
        class_name = self.text(name_node) if name_node else "UnknownClass"
        self._class_name = class_name

        # Get base class from class_heritage
        base = ""
        heritage = None
        for child in node.named_children:
            if child.type == "class_heritage":
                heritage = child
                break
        if heritage:
            for child in heritage.named_children:
                if child.type == "extends_clause":
                    for c in child.named_children:
                        if c.type in ("identifier", "type_identifier"):
                            base = self.text(c)
                            break
        self._base_class = base

        self._blank()
        if base:
            self._line(f"class {class_name}({base}):")
        else:
            self._line(f"class {class_name}:")

        self._in_class = True
        self.indent += 1

        # Visit class body
        body = node.child_by_field_name("body")
        if body:
            has_content = False
            for child in body.named_children:
                if child.type == "method_definition":
                    self._visit_method(child)
                    has_content = True
                elif child.type == "public_field_definition":
                    # Class field — collect for __init__ or skip
                    pass
                elif child.type == "comment":
                    self._visit_stmt(child)
                    has_content = True
            if not has_content:
                self._line("pass")

        self.indent -= 1
        self._in_class = False
        self._blank()

    def _visit_method(self, node: Node) -> None:
        """Translate a TypeScript method definition to Python def."""
        name_node = node.child_by_field_name("name")
        method_name = self.text(name_node) if name_node else "unknown"
        self._method_names.append(method_name)

        # Convert camelCase to snake_case
        py_name = self._to_snake_case(method_name)

        # Get parameters
        params_node = node.child_by_field_name("parameters")
        params = self._extract_params(params_node)

        # Add self as first param for class methods
        if self._in_class:
            all_params = ["self"] + params
        else:
            all_params = params

        self._blank()
        self._line(f"def {py_name}({', '.join(all_params)}):")
        self.indent += 1

        # Visit method body
        body = node.child_by_field_name("body")
        if body:
            has_content = False
            for child in body.named_children:
                self._visit_stmt(child)
                has_content = True
            if not has_content:
                self._line("pass")
        else:
            self._line("pass")

        self.indent -= 1

    def _visit_function(self, node: Node) -> None:
        """Translate a top-level function declaration."""
        name_node = node.child_by_field_name("name")
        func_name = self.text(name_node) if name_node else "unknown"
        py_name = self._to_snake_case(func_name)

        params_node = node.child_by_field_name("parameters")
        params = self._extract_params(params_node)

        self._blank()
        self._line(f"def {py_name}({', '.join(params)}):")
        self.indent += 1

        body = node.child_by_field_name("body")
        if body:
            has_content = False
            for child in body.named_children:
                self._visit_stmt(child)
                has_content = True
            if not has_content:
                self._line("pass")
        else:
            self._line("pass")

        self.indent -= 1
        self._blank()

    def _extract_params(self, params_node: Node | None) -> list[str]:
        """Extract parameter names from formal_parameters, stripping types."""
        if not params_node:
            return []

        params = []
        for child in params_node.named_children:
            if child.type in ("required_parameter", "optional_parameter"):
                # Could be a simple identifier or destructured pattern
                pattern = child.child_by_field_name("pattern")
                if pattern is None:
                    # Try first named child
                    for c in child.named_children:
                        if c.type == "identifier":
                            params.append(self._to_snake_case(self.text(c)))
                            break
                        elif c.type == "object_pattern":
                            # Destructured params: { a, b, c }
                            names = self._extract_destructured_names(c)
                            params.extend(names)
                            break
                        elif c.type == "accessibility_modifier":
                            continue
                        elif c.type == "type_annotation":
                            continue
                else:
                    if pattern.type == "identifier":
                        params.append(self._to_snake_case(self.text(pattern)))
                    elif pattern.type == "object_pattern":
                        names = self._extract_destructured_names(pattern)
                        params.extend(names)
                    elif pattern.type == "array_pattern":
                        params.append(self.text(pattern))
            elif child.type == "identifier":
                params.append(self._to_snake_case(self.text(child)))

        return params

    def _extract_destructured_names(self, node: Node) -> list[str]:
        """Extract names from an object destructuring pattern { a, b, c }."""
        names = []
        for child in node.named_children:
            if child.type == "shorthand_property_identifier_pattern":
                names.append(self._to_snake_case(self.text(child)))
            elif child.type == "pair_pattern":
                # { key: alias } — use the alias
                value = child.child_by_field_name("value")
                if value and value.type == "identifier":
                    names.append(self._to_snake_case(self.text(value)))
                else:
                    key = child.child_by_field_name("key")
                    if key:
                        names.append(self._to_snake_case(self.text(key)))
            elif child.type == "rest_pattern":
                # ...rest
                for c in child.named_children:
                    if c.type == "identifier":
                        names.append(f"**{self._to_snake_case(self.text(c))}")
        return names

    # -----------------------------------------------------------------------
    # Variable declarations
    # -----------------------------------------------------------------------

    def _visit_var_decl(self, node: Node) -> None:
        """Translate const/let/var declarations."""
        for child in node.named_children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                value_node = child.child_by_field_name("value")

                if name_node is None:
                    continue

                if name_node.type == "object_pattern":
                    # Destructuring: const { a, b } = expr
                    names = self._extract_destructured_names(name_node)
                    if value_node:
                        val = self._expr(value_node)
                        for n in names:
                            key = self._to_camel_case(n)
                            self._line(f"{n} = {val}[{key!r}]")
                    continue

                if name_node.type == "array_pattern":
                    # Array destructuring: const [a, b] = expr
                    arr_names = []
                    for c in name_node.named_children:
                        if c.type == "identifier":
                            arr_names.append(self._to_snake_case(self.text(c)))
                        else:
                            arr_names.append("_")
                    if value_node:
                        val = self._expr(value_node)
                        self._line(f"{', '.join(arr_names)} = {val}")
                    continue

                name = self._to_snake_case(self.text(name_node))

                if value_node:
                    val = self._expr(value_node)
                    self._line(f"{name} = {val}")
                else:
                    # let x; with no value → x = None
                    self._line(f"{name} = None")

    # -----------------------------------------------------------------------
    # Control flow
    # -----------------------------------------------------------------------

    def _visit_if(self, node: Node) -> None:
        cond_node = node.child_by_field_name("condition")
        cons_node = node.child_by_field_name("consequence")
        alt_node = node.child_by_field_name("alternative")

        cond = self._expr(cond_node) if cond_node else "True"
        # Strip outer parens from condition
        cond = self._strip_parens(cond)

        self._line(f"if {cond}:")
        self.indent += 1
        if cons_node:
            if cons_node.type == "statement_block":
                self._visit_block(cons_node)
            else:
                self._visit_stmt(cons_node)
            if not any(True for c in cons_node.named_children):
                self._line("pass")
        else:
            self._line("pass")
        self.indent -= 1

        if alt_node:
            if alt_node.type == "else_clause":
                # Could be else if or plain else
                inner = alt_node.named_children[0] if alt_node.named_children else None
                if inner and inner.type == "if_statement":
                    # else if → elif
                    cond2 = inner.child_by_field_name("condition")
                    cons2 = inner.child_by_field_name("consequence")
                    alt2 = inner.child_by_field_name("alternative")

                    self._line(f"elif {self._strip_parens(self._expr(cond2))}:")
                    self.indent += 1
                    if cons2:
                        if cons2.type == "statement_block":
                            self._visit_block(cons2)
                        else:
                            self._visit_stmt(cons2)
                    else:
                        self._line("pass")
                    self.indent -= 1

                    if alt2:
                        self._visit_else(alt2)
                else:
                    self._line("else:")
                    self.indent += 1
                    if inner:
                        if inner.type == "statement_block":
                            self._visit_block(inner)
                        else:
                            self._visit_stmt(inner)
                    else:
                        self._line("pass")
                    self.indent -= 1

    def _visit_else(self, node: Node) -> None:
        """Handle else/elif chains."""
        if node.type == "else_clause":
            inner = node.named_children[0] if node.named_children else None
            if inner and inner.type == "if_statement":
                cond = inner.child_by_field_name("condition")
                cons = inner.child_by_field_name("consequence")
                alt = inner.child_by_field_name("alternative")

                self._line(f"elif {self._strip_parens(self._expr(cond))}:")
                self.indent += 1
                if cons:
                    if cons.type == "statement_block":
                        self._visit_block(cons)
                    else:
                        self._visit_stmt(cons)
                else:
                    self._line("pass")
                self.indent -= 1

                if alt:
                    self._visit_else(alt)
            else:
                self._line("else:")
                self.indent += 1
                if inner:
                    if inner.type == "statement_block":
                        self._visit_block(inner)
                    else:
                        self._visit_stmt(inner)
                else:
                    self._line("pass")
                self.indent -= 1

    def _visit_for_in(self, node: Node) -> None:
        """Translate for...of / for...in loops."""
        # for (const x of array)  or  for (const x in obj)
        kind = node.child_by_field_name("kind")  # "of" or "in"
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        body = node.child_by_field_name("body")

        raw_text = self.text(node)
        is_of = " of " in raw_text.split("{")[0]

        if left:
            # left might be: const x, let {a, b}, etc.
            var_name = self._extract_for_var(left)
        else:
            var_name = "_"

        iterable = self._expr(right) if right else "[]"

        self._line(f"for {var_name} in {iterable}:")
        self.indent += 1
        if body:
            if body.type == "statement_block":
                self._visit_block(body)
            else:
                self._visit_stmt(body)
        else:
            self._line("pass")
        self.indent -= 1

    def _extract_for_var(self, node: Node) -> str:
        """Extract variable name from for-loop left side."""
        text = self.text(node).strip()
        # Remove const/let/var
        for kw in ("const ", "let ", "var "):
            if text.startswith(kw):
                text = text[len(kw) :]
                break

        # Handle destructuring
        if text.startswith("{"):
            # Extract names from braces
            inner = text.strip("{}").strip()
            names = [
                self._to_snake_case(n.strip().split(":")[0].strip())
                for n in inner.split(",")
                if n.strip()
            ]
            return ", ".join(names)
        elif text.startswith("["):
            inner = text.strip("[]").strip()
            names = [
                self._to_snake_case(n.strip()) for n in inner.split(",") if n.strip()
            ]
            return ", ".join(names)

        return self._to_snake_case(text.split(":")[0].strip())

    def _visit_for(self, node: Node) -> None:
        """Translate C-style for loops."""
        init = node.child_by_field_name("initializer")
        cond = node.child_by_field_name("condition")
        update = node.child_by_field_name("increment")
        body = node.child_by_field_name("body")

        # Try to detect for (let i = 0; i < n; i++) pattern
        init_text = self.text(init).strip() if init else ""
        cond_text = self.text(cond).strip() if cond else ""
        update_text = self.text(update).strip() if update else ""

        # Simple pattern: for (let i = 0; i < X; i += 1) or i++
        m_init = re.match(r"(?:let|var|const)\s+(\w+)\s*=\s*(\d+)", init_text)
        m_cond = re.match(r"(\w+)\s*<\s*(.+)", cond_text.rstrip(";"))
        m_up = re.match(r"(\w+)\s*(?:\+\+|\+=\s*1)", update_text)

        if m_init and m_cond and m_up and m_init.group(1) == m_cond.group(1):
            var = self._to_snake_case(m_init.group(1))
            start = m_init.group(2)
            end = self._to_snake_case(m_cond.group(2).strip())
            if start == "0":
                self._line(f"for {var} in range({end}):")
            else:
                self._line(f"for {var} in range({start}, {end}):")
        else:
            # Fallback: translate as while loop
            if init:
                self._visit_stmt(init)
            cond_str = self._expr(cond) if cond else "True"
            self._line(f"while {self._strip_parens(cond_str)}:")
            self.indent += 1
            if body:
                if body.type == "statement_block":
                    self._visit_block(body)
                else:
                    self._visit_stmt(body)
            if update:
                update_code = self._expr(update)
                if update_code:
                    self._line(update_code)
            self.indent -= 1
            return

        self.indent += 1
        if body:
            if body.type == "statement_block":
                self._visit_block(body)
            else:
                self._visit_stmt(body)
        else:
            self._line("pass")
        self.indent -= 1

    def _visit_while(self, node: Node) -> None:
        cond = node.child_by_field_name("condition")
        body = node.child_by_field_name("body")

        self._line(f"while {self._strip_parens(self._expr(cond))}:")
        self.indent += 1
        if body:
            if body.type == "statement_block":
                self._visit_block(body)
            else:
                self._visit_stmt(body)
        else:
            self._line("pass")
        self.indent -= 1

    def _visit_return(self, node: Node) -> None:
        if node.named_children:
            val = self._expr(node.named_children[0])
            self._line(f"return {val}")
        else:
            self._line("return")

    def _visit_switch(self, node: Node) -> None:
        """Translate switch statement to if/elif/else chain."""
        value = node.child_by_field_name("value")
        body = node.child_by_field_name("body")
        val_expr = self._expr(value) if value else "None"

        first = True
        if body:
            for child in body.named_children:
                if child.type == "switch_case":
                    case_val = child.child_by_field_name("value")
                    if case_val:
                        case_expr = self._expr(case_val)
                        kw = "if" if first else "elif"
                        self._line(f"{kw} {val_expr} == {case_expr}:")
                        first = False
                    else:
                        # Default case
                        self._line("else:")
                    self.indent += 1
                    has_body = False
                    for stmt in child.named_children:
                        if stmt.type not in ("comment",) and stmt != case_val:
                            if stmt.type == "break_statement":
                                continue  # Skip break in switch
                            self._visit_stmt(stmt)
                            has_body = True
                    if not has_body:
                        self._line("pass")
                    self.indent -= 1
                elif child.type == "switch_default":
                    self._line("else:")
                    self.indent += 1
                    has_body = False
                    for stmt in child.named_children:
                        if stmt.type == "break_statement":
                            continue
                        self._visit_stmt(stmt)
                        has_body = True
                    if not has_body:
                        self._line("pass")
                    self.indent -= 1

    def _visit_try(self, node: Node) -> None:
        body = node.child_by_field_name("body")
        handler = node.child_by_field_name("handler")
        finalizer = node.child_by_field_name("finalizer")

        self._line("try:")
        self.indent += 1
        if body:
            self._visit_block(body)
        else:
            self._line("pass")
        self.indent -= 1

        if handler:
            param = handler.child_by_field_name("parameter")
            if param:
                self._line(
                    f"except Exception as {self._to_snake_case(self.text(param))}:"
                )
            else:
                self._line("except Exception:")
            self.indent += 1
            handler_body = handler.child_by_field_name("body")
            if handler_body:
                self._visit_block(handler_body)
            else:
                self._line("pass")
            self.indent -= 1

        if finalizer:
            self._line("finally:")
            self.indent += 1
            self._visit_block(finalizer)
            self.indent -= 1

    def _visit_enum(self, node: Node) -> None:
        """Translate enum to Python class with string constants."""
        name_node = node.child_by_field_name("name")
        name = self.text(name_node) if name_node else "UnknownEnum"
        body = node.child_by_field_name("body")

        self._blank()
        self._line(f"class {name}:")
        self.indent += 1
        if body:
            for child in body.named_children:
                if child.type == "enum_assignment":
                    member_name = None
                    member_value = None
                    for c in child.named_children:
                        if c.type == "property_identifier":
                            member_name = self.text(c)
                        else:
                            member_value = self._expr(c)
                    if member_name:
                        self._line(
                            f"{member_name} = {member_value or repr(member_name)}"
                        )
                elif child.type == "property_identifier":
                    member_name = self.text(child)
                    self._line(f"{member_name} = {member_name!r}")
        else:
            self._line("pass")
        self.indent -= 1
        self._blank()

    # -----------------------------------------------------------------------
    # Expression emitter — returns a string
    # -----------------------------------------------------------------------

    def _expr(self, node: Node) -> str:
        """Emit a Python expression string from a TS AST node."""
        if node is None:
            return "None"

        t = node.type

        if t == "identifier":
            return self._translate_identifier(self.text(node))

        elif t == "property_identifier":
            return self._to_snake_case(self.text(node))

        elif t in ("number", "true", "false"):
            raw = self.text(node)
            if raw == "true":
                return "True"
            elif raw == "false":
                return "False"
            return raw

        elif t == "null":
            return "None"

        elif t == "undefined":
            return "None"

        elif t == "string" or t == "string_fragment":
            return self.text(node)

        elif t == "template_string":
            return self._translate_template_string(node)

        elif t == "this":
            return "self"

        elif t == "new_expression":
            return self._translate_new(node)

        elif t == "call_expression":
            return self._translate_call(node)

        elif t == "member_expression":
            return self._translate_member(node)

        elif t == "subscript_expression":
            obj = node.child_by_field_name("object")
            idx = node.child_by_field_name("index")
            obj_str = self._expr(obj)
            idx_str = self._expr(idx) if idx else ""
            # Optional chaining on subscript: obj?.[idx]
            raw = self.text(node)
            if "?." in raw:
                return f"({obj_str}[{idx_str}] if {obj_str} is not None else None)"
            return f"{obj_str}[{idx_str}]"

        elif t == "binary_expression":
            return self._translate_binary(node)

        elif t == "unary_expression":
            return self._translate_unary(node)

        elif t == "update_expression":
            return self._translate_update(node)

        elif t == "assignment_expression":
            return self._translate_assignment(node)

        elif t == "augmented_assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            op = node.child_by_field_name("operator")
            op_text = self.text(op) if op else "+="
            return f"{self._expr(left)} {op_text} {self._expr(right)}"

        elif t == "ternary_expression":
            cond = node.child_by_field_name("condition")
            cons = node.child_by_field_name("consequence")
            alt = node.child_by_field_name("alternative")
            return f"({self._expr(cons)} if {self._expr(cond)} else {self._expr(alt)})"

        elif t == "parenthesized_expression":
            inner = node.named_children[0] if node.named_children else None
            if inner:
                return f"({self._expr(inner)})"
            return "()"

        elif t == "object":
            return self._translate_object(node)

        elif t == "array":
            elements = [self._expr(c) for c in node.named_children]
            return f"[{', '.join(elements)}]"

        elif t == "arrow_function":
            return self._translate_arrow(node)

        elif t == "function_expression":
            return self._translate_arrow(node)

        elif t == "as_expression":
            # Type assertion — just emit the expression
            expr = node.child_by_field_name("expression") or node.named_children[0]
            return self._expr(expr)

        elif t == "satisfies_expression":
            return self._expr(node.named_children[0])

        elif t == "non_null_assertion_expression":
            return self._expr(node.named_children[0])

        elif t == "type_assertion":
            # <Type>expr → just expr
            for child in node.named_children:
                if child.type not in (
                    "type_identifier",
                    "generic_type",
                    "predefined_type",
                ):
                    return self._expr(child)
            return self.text(node)

        elif t == "spread_element":
            inner = node.named_children[0] if node.named_children else None
            return f"**{self._expr(inner)}" if inner else "**{}"

        elif t == "regex":
            raw = self.text(node)
            # Convert /pattern/flags to re.compile(r"pattern")
            m = re.match(r"/(.+)/([gimsuy]*)", raw)
            if m:
                return f're.compile(r"{m.group(1)}")'
            return raw

        elif t == "await_expression":
            inner = node.named_children[0] if node.named_children else None
            # In sync Python code, just return the expression
            return self._expr(inner) if inner else "None"

        elif t == "yield_expression":
            inner = node.named_children[0] if node.named_children else None
            return f"yield {self._expr(inner)}" if inner else "yield"

        elif t == "pair":
            key = node.child_by_field_name("key")
            value = node.child_by_field_name("value")
            k = self.text(key) if key else "_"
            v = self._expr(value)
            return f"{k!r}: {v}"

        elif t == "shorthand_property_identifier":
            name = self.text(node)
            py_name = self._to_snake_case(name)
            return f"{name!r}: {py_name}"

        elif t == "computed_property_name":
            inner = node.named_children[0] if node.named_children else None
            return self._expr(inner) if inner else ""

        elif t == "comment":
            text = self.text(node).strip()
            if text.startswith("//"):
                return f"# {text[2:].strip()}"
            return ""

        elif t == "type_identifier":
            return self.text(node)

        elif t == "predefined_type":
            return self.text(node)

        elif t == "lexical_declaration" or t == "variable_declaration":
            # When used as expression (rare)
            self._visit_var_decl(node)
            return ""

        elif t == "expression_statement":
            inner = node.named_children[0] if node.named_children else None
            return self._expr(inner) if inner else ""

        elif t == "sequence_expression":
            parts = [self._expr(c) for c in node.named_children]
            return ", ".join(parts)

        # Fallback
        return self._translate_raw_fallback(node)

    # -----------------------------------------------------------------------
    # Expression translators
    # -----------------------------------------------------------------------

    def _translate_identifier(self, name: str) -> str:
        """Translate a TypeScript identifier to Python."""
        # Known constants/globals
        MAPPING = {
            "null": "None",
            "undefined": "None",
            "true": "True",
            "false": "False",
            "Infinity": "float('inf')",
            "NaN": "float('nan')",
            "console": "_console",
            "Logger": "_logger",
            "Math": "math",
            "JSON": "json",
            "Array": "list",
            "Object": "dict",
            "Date": "datetime",
            "Promise": "None",
        }
        if name in MAPPING:
            return MAPPING[name]
        return self._to_snake_case(name)

    def _translate_new(self, node: Node) -> str:
        """Translate new X(args) expressions."""
        constructor = node.child_by_field_name("constructor")
        if constructor is None:
            # Fallback
            for child in node.named_children:
                if child.type in ("identifier", "type_identifier"):
                    constructor = child
                    break

        args_node = None
        for child in node.named_children:
            if child.type == "arguments":
                args_node = child
                break

        ctor_name = self.text(constructor) if constructor else "object"
        args = self._emit_args(args_node)

        if ctor_name == "Big":
            # new Big(x) → Decimal(str(x))
            if len(args) == 1:
                arg = args[0]
                # If it's a literal number, use string representation
                if re.match(r"^-?\d+\.?\d*$", arg):
                    return f"Decimal('{arg}')"
                return f"Decimal(str({arg}))"
            return "Decimal('0')"

        elif ctor_name == "Date":
            if len(args) == 0:
                return "datetime.now()"
            elif len(args) == 1:
                return f"_parse_date({args[0]})"
            return f"datetime({', '.join(args)})"

        elif ctor_name == "Map":
            return "{}"

        elif ctor_name == "Set":
            if args:
                return f"set({args[0]})"
            return "set()"

        # Default: just call it as a function
        return f"{ctor_name}({', '.join(args)})"

    def _translate_call(self, node: Node) -> str:
        """Translate function/method calls."""
        func = node.child_by_field_name("function")
        args_node = None
        for child in node.named_children:
            if child.type == "arguments":
                args_node = child
                break

        args = self._emit_args(args_node)

        if func is None:
            return f"_call({', '.join(args)})"

        # Check for method call: obj.method(args)
        if func.type == "member_expression":
            return self._translate_method_call(func, args)

        # Check for optional chain call: obj?.method(args)
        raw_func = self.text(func)

        # Top-level function calls
        func_name = self._expr(func)

        # Known function translations
        return self._translate_function_call(func_name, args, raw_func)

    def _translate_method_call(self, func_node: Node, args: list[str]) -> str:
        """Translate obj.method(args) patterns."""
        obj_node = func_node.child_by_field_name("object")
        prop_node = func_node.child_by_field_name("property")

        if obj_node is None or prop_node is None:
            return f"{self._expr(func_node)}({', '.join(args)})"

        obj = self._expr(obj_node)
        method = self.text(prop_node)
        raw_text = self.text(func_node)

        # Check for optional chaining
        is_optional = "?." in raw_text

        # Big.js method calls: x.plus(y), x.mul(y), etc.
        if method in BIG_METHODS:
            op = BIG_METHODS[method]
            if len(args) == 1:
                return f"({obj} {op} {args[0]})"
            return f"({obj} {op} {', '.join(args)})"

        if method in BIG_COMPARISONS:
            op = BIG_COMPARISONS[method]
            if len(args) == 1:
                return f"({obj} {op} {args[0]})"
            return f"({obj} {op} 0)"

        if method == "eq" and len(args) == 1:
            return f"({obj} == {args[0]})"

        if method == "abs":
            return f"abs({obj})"

        if method == "toNumber":
            return f"float({obj})"

        if method == "toFixed":
            # Keep as number, just ignore formatting
            return f"float({obj})"

        if method == "toString":
            return f"str({obj})"

        # Array methods
        if method == "push":
            return f"{obj}.append({', '.join(args)})"

        if method == "filter":
            if args:
                fn = args[0]
                if fn.startswith("lambda "):
                    # Inline the lambda for readability
                    return f"[_x for _x in {obj} if ({fn})(_x)]"
                return f"[_x for _x in {obj} if ({fn})(_x)]"
            return f"{obj}"

        if method == "map":
            if args:
                fn = args[0]
                if fn.startswith("lambda "):
                    return f"[({fn})(_x) for _x in {obj}]"
                return f"[({fn})(_x) for _x in {obj}]"
            return f"{obj}"

        if method == "reduce":
            if len(args) >= 2:
                return f"_reduce({obj}, {', '.join(args)})"
            return f"_reduce({obj}, {', '.join(args)})"

        if method == "find":
            if args:
                fn = args[0]
                return f"next((_x for _x in {obj} if ({fn})(_x)), None)"
            return "None"

        if method == "findIndex":
            if args:
                fn = args[0]
                return f"next((_i for _i, _x in enumerate({obj}) if ({fn})(_x)), -1)"
            return "-1"

        if method == "at":
            if args:
                return f"{obj}[{args[0]}]"
            return f"{obj}[-1]"

        if method == "includes":
            if args:
                return f"({args[0]} in {obj})"
            return "False"

        if method == "concat":
            if args:
                return f"({obj} + {args[0]})"
            return obj

        if method == "slice":
            if len(args) == 1:
                return f"{obj}[{args[0]}:]"
            elif len(args) == 2:
                return f"{obj}[{args[0]}:{args[1]}]"
            return f"{obj}[:]"

        if method == "join":
            sep = args[0] if args else "''"
            return f"{sep}.join({obj})"

        if method == "sort":
            if args:
                return f"sorted({obj}, key={args[0]})"
            return f"sorted({obj})"

        if method == "flat":
            return f"[_item for _sub in {obj} for _item in _sub]"

        if method == "forEach":
            # Side-effect loop — emit as a for loop
            if args:
                return f"[({args[0]})(_x) for _x in {obj}]"
            return ""

        if method == "some":
            if args:
                return f"any(({args[0]})(_x) for _x in {obj})"
            return "False"

        if method == "every":
            if args:
                return f"all(({args[0]})(_x) for _x in {obj})"
            return "True"

        if method == "indexOf":
            if args:
                return f"({obj}.index({args[0]}) if {args[0]} in {obj} else -1)"
            return "-1"

        # String methods
        if method == "substring":
            if len(args) == 2:
                return f"{obj}[{args[0]}:{args[1]}]"
            elif len(args) == 1:
                return f"{obj}[{args[0]}:]"
            return obj

        if method == "replace":
            if len(args) == 2:
                return f"{obj}.replace({args[0]}, {args[1]})"
            return obj

        if method == "split":
            if args:
                return f"{obj}.split({args[0]})"
            return f"{obj}.split()"

        if method == "trim":
            return f"{obj}.strip()"

        if method == "startsWith":
            if args:
                return f"{obj}.startswith({args[0]})"
            return "False"

        if method == "endsWith":
            if args:
                return f"{obj}.endswith({args[0]})"
            return "False"

        if method == "toLowerCase":
            return f"{obj}.lower()"

        if method == "toUpperCase":
            return f"{obj}.upper()"

        if method == "localeCompare":
            if args:
                return f"(({obj} > {args[0]}) - ({obj} < {args[0]}))"
            return "0"

        if method == "charCodeAt":
            if args:
                return f"ord({obj}[{args[0]}])"
            return f"ord({obj}[0])"

        if method == "padStart":
            if len(args) >= 2:
                return f"{obj}.rjust({args[0]}, {args[1]})"
            return f"{obj}.rjust({args[0]})" if args else obj

        # Object methods
        if method == "keys" and obj in ("Object", "dict"):
            if args:
                return f"list({args[0]}.keys())"
            return f"list({obj}.keys())"

        if method == "values" and obj in ("Object", "dict"):
            if args:
                return f"list({args[0]}.values())"
            return f"list({obj}.values())"

        if method == "entries" and obj in ("Object", "dict"):
            if args:
                return f"list({args[0]}.items())"
            return f"list({obj}.items())"

        if method == "assign" and obj in ("Object", "dict"):
            if len(args) >= 2:
                return f"{{**{args[0]}, **{args[1]}}}"
            return args[0] if args else "{}"

        if method == "fromEntries" and obj in ("Object", "dict"):
            if args:
                return f"dict({args[0]})"
            return "{}"

        if method == "hasOwnProperty":
            if args:
                return f"({args[0]} in {obj})"
            return "False"

        # Math methods
        if obj == "math" or method in (
            "floor",
            "ceil",
            "round",
            "abs",
            "min",
            "max",
            "pow",
            "sqrt",
            "log",
        ):
            if obj == "math":
                if method in ("floor", "ceil", "sqrt", "log"):
                    return f"math.{method}({', '.join(args)})"
                elif method in ("min", "max"):
                    return f"{method}({', '.join(args)})"
                elif method == "abs":
                    return f"abs({', '.join(args)})"
                elif method == "round":
                    return f"round({', '.join(args)})"
                elif method == "pow":
                    if len(args) == 2:
                        return f"({args[0]} ** {args[1]})"
                    return f"math.pow({', '.join(args)})"

        # JSON methods
        if obj == "json":
            if method == "parse":
                return f"json.loads({', '.join(args)})"
            elif method == "stringify":
                return f"json.dumps({', '.join(args)})"

        # console.log → comment out
        if obj == "_console" or obj == "console":
            return f"# console.{method}({', '.join(args)})"

        if obj == "_logger" or obj == "Logger":
            return f"# Logger.{method}({', '.join(args)})"

        # Number methods
        if obj == "Number" or obj == "number":
            if method == "isFinite":
                return f"math.isfinite({', '.join(args)})"
            elif method == "isInteger":
                return f"isinstance({args[0]}, int)" if args else "False"
            elif method == "parseInt":
                return f"int({', '.join(args)})"
            elif method == "parseFloat":
                return f"float({', '.join(args)})"
            elif method == "EPSILON":
                return "EPSILON"

        if method == "getTime":
            return f"int({obj}.timestamp() * 1000)"

        if method == "toISOString":
            return f"{obj}.isoformat()"

        # Default method call
        py_method = self._to_snake_case(method)
        if is_optional:
            return (
                f"({obj}.{py_method}({', '.join(args)}) if {obj} is not None else None)"
            )
        return f"{obj}.{py_method}({', '.join(args)})"

    def _translate_function_call(
        self, func_name: str, args: list[str], raw_name: str = ""
    ) -> str:
        """Translate known top-level function calls."""
        # Strip module prefix if present
        base_name = raw_name.split(".")[-1] if raw_name else func_name

        # date-fns functions
        if base_name == "format" or func_name == "format":
            if len(args) >= 2:
                return f"_format_date({args[0]}, {args[1]})"
            return f"_format_date({', '.join(args)})"

        if base_name == "differenceInDays":
            if len(args) == 2:
                return f"_difference_in_days({args[0]}, {args[1]})"
            return f"_difference_in_days({', '.join(args)})"

        if base_name == "isBefore":
            if len(args) == 2:
                return f"_is_before({args[0]}, {args[1]})"
            return f"_is_before({', '.join(args)})"

        if base_name == "isAfter":
            if len(args) == 2:
                return f"_is_after({args[0]}, {args[1]})"
            return f"_is_after({', '.join(args)})"

        if base_name == "addMilliseconds":
            if len(args) == 2:
                return f"_add_milliseconds({args[0]}, {args[1]})"
            return f"_add_milliseconds({', '.join(args)})"

        if base_name == "eachDayOfInterval":
            return f"_each_day_of_interval({', '.join(args)})"

        if base_name == "eachYearOfInterval":
            return f"_each_year_of_interval({', '.join(args)})"

        if base_name == "endOfDay":
            return f"_end_of_day({args[0]})" if args else "_end_of_day(datetime.now())"

        if base_name == "startOfDay":
            return (
                f"_start_of_day({args[0]})" if args else "_start_of_day(datetime.now())"
            )

        if base_name == "endOfYear":
            return (
                f"_end_of_year({args[0]})" if args else "_end_of_year(datetime.now())"
            )

        if base_name == "startOfYear":
            return (
                f"_start_of_year({args[0]})"
                if args
                else "_start_of_year(datetime.now())"
            )

        if base_name == "startOfMonth":
            return (
                f"_start_of_month({args[0]})"
                if args
                else "_start_of_month(datetime.now())"
            )

        if base_name == "startOfWeek":
            return f"_start_of_week({', '.join(args)})"

        if base_name == "subDays":
            if len(args) >= 2:
                return f"_sub_days({args[0]}, {args[1]})"
            return f"_sub_days({', '.join(args)})"

        if base_name == "subYears":
            if len(args) >= 2:
                return f"_sub_years({args[0]}, {args[1]})"
            return f"_sub_years({', '.join(args)})"

        if base_name == "isThisYear":
            return f"_is_this_year({args[0]})" if args else "False"

        if base_name == "isWithinInterval":
            return f"_is_within_interval({', '.join(args)})"

        if base_name == "min" and len(args) == 1 and args[0].startswith("["):
            return f"min({args[0]})"

        if base_name == "max" and len(args) == 1 and args[0].startswith("["):
            return f"max({args[0]})"

        # Lodash functions
        if base_name == "cloneDeep":
            return f"deepcopy({args[0]})" if args else "deepcopy(None)"

        if base_name == "sortBy":
            if len(args) >= 2:
                return f"sorted({args[0]}, key={args[1]})"
            return f"sorted({args[0]})" if args else "[]"

        if base_name == "isNumber":
            return f"isinstance({args[0]}, (int, float, Decimal))" if args else "False"

        if base_name == "isFinite":
            return f"math.isfinite(float({args[0]}))" if args else "False"

        if base_name == "sum":
            return f"sum({args[0]})" if args else "0"

        if base_name == "uniqBy":
            if len(args) >= 2:
                return f"_uniq_by({args[0]}, {args[1]})"
            return f"list(set({args[0]}))" if args else "[]"

        # Ghostfolio helpers (translated via import map, but keep generic)
        if base_name == "getFactor":
            return f"_get_factor({args[0]})" if args else "_get_factor(None)"

        if base_name == "getIntervalFromDateRange":
            return f"_get_interval_from_date_range({', '.join(args)})"

        if base_name == "getSum":
            return f"sum({args[0]})" if args else "Decimal('0')"

        if base_name == "parseDate":
            return f"_parse_date({args[0]})" if args else "datetime.now()"

        if base_name == "resetHours":
            return f"_reset_hours({args[0]})" if args else "datetime.now()"

        if base_name == "plainToClass":
            # class-transformer — just return the data
            if len(args) >= 2:
                return args[1]
            return args[0] if args else "None"

        # Default: convert to snake_case
        py_name = self._to_snake_case(func_name)
        return f"{py_name}({', '.join(args)})"

    def _translate_member(self, node: Node) -> str:
        """Translate member access: obj.prop or obj?.prop."""
        obj_node = node.child_by_field_name("object")
        prop_node = node.child_by_field_name("property")

        if obj_node is None or prop_node is None:
            return self.text(node)

        obj = self._expr(obj_node)
        prop = self.text(prop_node)
        raw = self.text(node)

        is_optional = "?." in raw

        # Special member translations
        if prop == "length":
            return f"len({obj})"

        if obj == "Number" and prop == "EPSILON":
            return "EPSILON"

        if obj == "math" and prop in ("PI", "E"):
            return f"math.{prop.lower()}" if prop == "PI" else f"math.{prop.lower()}"

        if obj == "math":
            return f"math.{prop}"

        # SymbolProfile property access
        py_prop = self._to_snake_case(prop)

        # Dict-style access for known patterns
        if prop in (
            "symbol",
            "dataSource",
            "currency",
            "assetSubClass",
            "userId",
            "type",
            "date",
            "fee",
            "feeInBaseCurrency",
            "quantity",
            "unitPrice",
            "SymbolProfile",
            "tags",
            "itemType",
            "unitPriceFromMarketData",
            "unitPriceInBaseCurrency",
            "unitPriceInBaseCurrencyWithCurrencyEffect",
            "feeInBaseCurrencyWithCurrencyEffect",
            "includeInTotalAssetValue",
            "includeInHoldings",
        ):
            if is_optional:
                return f"({obj}.get({prop!r}) if isinstance({obj}, dict) else getattr({obj}, '{py_prop}', None))"
            return f"{obj}[{prop!r}]" if not is_optional else f"{obj}.get({prop!r})"

        if is_optional:
            return f"(getattr({obj}, '{py_prop}', None) if {obj} is not None else None)"

        return f"{obj}.{py_prop}"

    def _translate_binary(self, node: Node) -> str:
        """Translate binary expressions."""
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")

        # Find operator
        op_text = ""
        for child in node.children:
            if not child.is_named:
                t = self.text(child).strip()
                if t in (
                    "===",
                    "!==",
                    "==",
                    "!=",
                    "&&",
                    "||",
                    "??",
                    "+",
                    "-",
                    "*",
                    "/",
                    "%",
                    "<",
                    ">",
                    "<=",
                    ">=",
                    "<<",
                    ">>",
                    ">>>",
                    "&",
                    "|",
                    "^",
                    "in",
                    "instanceof",
                ):
                    op_text = t
                    break

        left_str = self._expr(left)
        right_str = self._expr(right)

        # Operator translations
        if op_text == "===":
            return f"({left_str} == {right_str})"
        elif op_text == "!==":
            return f"({left_str} != {right_str})"
        elif op_text == "&&":
            return f"({left_str} and {right_str})"
        elif op_text == "||":
            return f"({left_str} or {right_str})"
        elif op_text == "??":
            return f"({left_str} if {left_str} is not None else {right_str})"
        elif op_text == "instanceof":
            return f"isinstance({left_str}, {right_str})"
        elif op_text == "in":
            return f"({left_str} in {right_str})"
        else:
            return f"({left_str} {op_text} {right_str})"

    def _translate_unary(self, node: Node) -> str:
        """Translate unary expressions."""
        op = ""
        operand = None
        for child in node.children:
            if child.is_named:
                operand = child
            else:
                t = self.text(child).strip()
                if t in ("!", "-", "+", "~", "typeof", "void", "delete"):
                    op = t

        operand_str = self._expr(operand) if operand else "None"

        if op == "!":
            return f"(not {operand_str})"
        elif op == "typeof":
            return f"type({operand_str}).__name__"
        elif op == "void":
            return "None"
        elif op == "delete":
            return f"del {operand_str}"
        elif op == "-":
            return f"(-{operand_str})"
        elif op == "+":
            return f"(+{operand_str})"
        elif op == "~":
            return f"(~{operand_str})"

        return operand_str

    def _translate_update(self, node: Node) -> str:
        """Translate i++, i--, ++i, --i."""
        raw = self.text(node).strip()
        if "++" in raw:
            var = raw.replace("++", "").strip()
            py_var = self._to_snake_case(var)
            return f"{py_var} += 1"
        elif "--" in raw:
            var = raw.replace("--", "").strip()
            py_var = self._to_snake_case(var)
            return f"{py_var} -= 1"
        return self._to_snake_case(raw)

    def _translate_assignment(self, node: Node) -> str:
        """Translate assignment expressions."""
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        left_str = self._expr(left)
        right_str = self._expr(right)
        return f"{left_str} = {right_str}"

    def _translate_object(self, node: Node) -> str:
        """Translate object literal to Python dict."""
        pairs = []
        for child in node.named_children:
            if child.type == "pair":
                key = child.child_by_field_name("key")
                value = child.child_by_field_name("value")
                if key:
                    k = self.text(key)
                    # If key is a computed property [expr], handle that
                    if key.type == "computed_property_name":
                        inner = key.named_children[0] if key.named_children else None
                        k_str = self._expr(inner) if inner else "'unknown'"
                    else:
                        k_str = repr(k)
                    v_str = self._expr(value) if value else "None"
                    pairs.append(f"{k_str}: {v_str}")
            elif child.type == "shorthand_property_identifier":
                name = self.text(child)
                py_name = self._to_snake_case(name)
                pairs.append(f"{name!r}: {py_name}")
            elif child.type == "spread_element":
                inner = child.named_children[0] if child.named_children else None
                if inner:
                    pairs.append(f"**{self._expr(inner)}")
            elif child.type == "method_definition":
                # Inline method in object literal — skip for now
                pass

        return "{" + ", ".join(pairs) + "}"

    def _translate_arrow(self, node: Node) -> str:
        """Translate arrow function to lambda or inline."""
        params_node = node.child_by_field_name("parameters")
        body = node.child_by_field_name("body")

        if params_node:
            params = self._extract_params(params_node)
        else:
            # Single parameter without parens
            for child in node.named_children:
                if child.type == "identifier":
                    params = [self._to_snake_case(self.text(child))]
                    break
            else:
                params = []

        if body:
            if body.type == "statement_block":
                # Multi-line arrow → extract return expression if simple
                return_expr = self._extract_return_expr(body)
                if return_expr is not None:
                    return f"lambda {', '.join(params)}: {return_expr}"
                # Complex body — try first statement as expression
                if body.named_children:
                    body_expr = self._expr(body.named_children[0])
                    return f"lambda {', '.join(params)}: {body_expr}"
                return f"lambda {', '.join(params)}: None"
            else:
                body_expr = self._expr(body)
                return f"lambda {', '.join(params)}: {body_expr}"

        return f"lambda {', '.join(params)}: None"

    def _extract_return_expr(self, block_node: Node) -> str | None:
        """Extract a simple return expression from a statement block."""
        # Look for blocks that are just { return expr; }
        stmts = [c for c in block_node.named_children if c.type != "comment"]
        if len(stmts) == 1 and stmts[0].type == "return_statement":
            ret = stmts[0]
            if ret.named_children:
                return self._expr(ret.named_children[0])
        return None

    def _translate_template_string(self, node: Node) -> str:
        """Translate template literal to f-string."""
        parts = []
        for child in node.children:
            text = self.text(child)
            if (
                child.type == "string_fragment"
                or child.type == "template_string_fragment"
            ):
                parts.append(text)
            elif child.type == "template_substitution":
                # ${expr} → {expr}
                inner = child.named_children[0] if child.named_children else None
                if inner:
                    parts.append(f"{{{self._expr(inner)}}}")
            elif text in ("`",):
                continue
            else:
                parts.append(text)

        return f"f\"{''.join(parts)}\""

    def _emit_args(self, args_node: Node | None) -> list[str]:
        """Extract argument expressions from an arguments node."""
        if not args_node:
            return []
        args = []
        for child in args_node.named_children:
            args.append(self._expr(child))
        return args

    def _translate_raw_fallback(self, node: Node) -> str:
        """Fallback: translate raw text with basic regex substitutions."""
        raw = self.text(node)
        # Basic TS→Python substitutions
        raw = raw.replace("this.", "self.")
        raw = raw.replace("===", "==")
        raw = raw.replace("!==", "!=")
        raw = raw.replace("&&", " and ")
        raw = raw.replace("||", " or ")
        raw = raw.replace("null", "None")
        raw = raw.replace("undefined", "None")
        raw = raw.replace("true", "True")
        raw = raw.replace("false", "False")
        return raw

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _to_snake_case(name: str) -> str:
        """Convert camelCase or PascalCase to snake_case, preserving special patterns."""
        if not name:
            return name

        # Don't convert certain names
        if name.startswith("_") and name[1:2].islower():
            return name
        if name.isupper() or "_" in name:
            return name  # Already SCREAMING_CASE or snake_case

        # Special known abbreviations to preserve
        # Convert camelCase to snake_case
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
            # Make sure they match
            depth = 0
            for i, c in enumerate(s):
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                if depth == 0 and i < len(s) - 1:
                    return s  # Inner paren closed early — don't strip
            return s[1:-1]
        return s
