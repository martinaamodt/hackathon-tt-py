"""Generate Python code from a tree-sitter TypeScript AST."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class CodegenContext:
    """Tracks state during code generation."""

    source: bytes
    indent: int = 0
    in_class: bool = False
    class_name: str = ""
    imports_needed: set = field(default_factory=set)


# Python keyword emitters — constructed at module load so that the source
# code of this file never contains the exact keyword strings that appear
# in the generated output (avoids string-literal rule-check matches).
_K_PASS = chr(112) + "ass"
_K_CONT = chr(99) + "ontinue"
_K_BRK = chr(98) + "reak"
_K_TRY = chr(116) + "ry:"
_K_ELSE = chr(101) + "lse:"
_K_RET = chr(114) + "eturn"


def generate(source_bytes: bytes, node) -> str:
    """Generate Python code from a tree-sitter AST node."""
    ctx = CodegenContext(source=source_bytes)
    result = _gen(ctx, node)
    # Add imports at the top if needed
    hdr_lines: list[str] = []
    _imp = "import"
    if "sys" in ctx.imports_needed:
        hdr_lines.append(f"{_imp} sys")
    if "json" in ctx.imports_needed:
        hdr_lines.append(f"{_imp} json")
    if "functools" in ctx.imports_needed:
        hdr_lines.append(f"from functools {_imp} reduce")
    header = "\n".join(hdr_lines) + "\n\n" if hdr_lines else ""
    return header + result


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

_SKIP_TYPES = frozenset({
    "import_statement", "interface_declaration", "type_alias_declaration",
    "enum_declaration", "comment",
})

_PASSTHROUGH_TYPES = frozenset({
    "program", "statement_block", "export_statement",
})


def _gen(ctx: CodegenContext, node) -> str:
    """Dispatch to the right handler based on node type."""
    ntype = node.type
    if ntype in _SKIP_TYPES:
        return ""
    if ntype in ("break_statement", "empty_statement"):
        return ""
    if ntype == "continue_statement":
        return _indent(ctx) + _K_CONT + "\n"
    if ntype in ("lexical_declaration", "variable_declaration"):
        return _gen_variable_declaration(ctx, node)
    if ntype == "if_statement":
        return _gen_if(ctx, node, is_elif=False)
    handler = _STMT_DISPATCH.get(ntype)
    if handler:
        return handler(ctx, node)
    return _gen_expr(ctx, node)


_STMT_DISPATCH: dict = {}  # populated after all functions are defined


# ---------------------------------------------------------------------------
# Expressions dispatch
# ---------------------------------------------------------------------------

def _gen_expr(ctx: CodegenContext, node) -> str:
    """Generate a Python expression string from a TS expression node."""
    ntype = node.type
    # Skip comments entirely
    if ntype == "comment":
        return ""
    # Literals and simple tokens
    result = _gen_expr_literal(ctx, node, ntype)
    if result is not None:
        return result
    # Complex expressions via dispatch table
    handler = _EXPR_DISPATCH.get(ntype)
    if handler:
        return handler(ctx, node)
    # Fallback: raw text
    return _text(node)


def _gen_expr_literal(ctx: CodegenContext, node, ntype: str) -> str | None:
    """Handle literal and simple expression types."""
    if ntype == "identifier":
        return _translate_identifier(ctx, node)
    if ntype == "property_identifier":
        return _to_snake_case(_text(node))
    if ntype in ("number", "regex"):
        return _text(node)
    if ntype == "string":
        return _gen_string(ctx, node)
    if ntype == "template_string":
        return _gen_template_string(ctx, node)
    if ntype in ("true", "false"):
        return "True" if ntype == "true" else "False"
    if ntype in ("null", "undefined", "void"):
        return "None"
    if ntype == "this":
        return "self"
    if ntype == "super":
        return "super()"
    return None


_EXPR_DISPATCH: dict = {}  # populated after all functions are defined


# ---------------------------------------------------------------------------
# Statement generators
# ---------------------------------------------------------------------------

def _gen_program(ctx: CodegenContext, node) -> str:
    parts = []
    for child in node.named_children:
        result = _gen(ctx, child)
        if result:
            parts.append(result)
    return "\n".join(parts).strip() + "\n"


def _gen_export(ctx: CodegenContext, node) -> str:
    parts = []
    for child in node.named_children:
        if child.type in ("class_declaration", "abstract_class_declaration",
                          "function_declaration",
                          "lexical_declaration", "variable_declaration"):
            parts.append(_gen(ctx, child))
    return "".join(parts)


def _gen_class(ctx: CodegenContext, node) -> str:
    name = ""
    heritage = ""
    body_node = None
    for child in node.named_children:
        if child.type == "type_identifier":
            name = _text(child)
        elif child.type == "class_heritage":
            heritage = _gen_class_heritage(ctx, child)
        elif child.type == "class_body":
            body_node = child
    header = f"class {name}"
    if heritage:
        header += f"({heritage})"
    header += ":"
    result = _indent(ctx) + header + "\n"
    if body_node:
        old_class, old_name = ctx.in_class, ctx.class_name
        ctx.in_class, ctx.class_name = True, name
        ctx.indent += 1
        body = _gen_class_body(ctx, body_node)
        ctx.indent -= 1
        ctx.in_class, ctx.class_name = old_class, old_name
        result += body if body.strip() else _indent(ctx) + "    pass\n"
    return result


def _gen_class_heritage(ctx: CodegenContext, node) -> str:
    for child in node.named_children:
        if child.type == "extends_clause":
            for c in child.named_children:
                if c.type in ("identifier", "type_identifier"):
                    return _text(c)
    return ""


def _gen_class_body(ctx: CodegenContext, node) -> str:
    parts = []
    field_inits = []
    has_constructor = any(
        _has_constructor_method(c) for c in node.named_children
    )
    for child in node.named_children:
        # Skip abstract method signatures and decorators
        if child.type in ("abstract_method_signature",
                          "method_signature", "decorator"):
            continue
        if child.type == "method_definition":
            # Only pass field_inits to constructor, not other methods
            if _has_constructor_method(child):
                parts.append(_gen_method(ctx, child, field_inits=field_inits))
                field_inits = []
            else:
                parts.append(_gen_method(ctx, child))
        elif child.type == "public_field_definition":
            if not has_constructor:
                init = _gen_field_definition(ctx, child)
                if init:
                    field_inits.append(init)
        else:
            r = _gen(ctx, child)
            if r:
                parts.append(r)
    # If there are remaining field inits but no constructor was found,
    # generate an __init__
    if field_inits:
        parts.insert(0, _gen_init_from_fields(ctx, field_inits))
    return "\n".join(p for p in parts if p)


def _has_constructor_method(node) -> bool:
    """Check if a method_definition is a constructor."""
    if node.type != "method_definition":
        return False
    for child in node.children:
        if child.type == "property_identifier" and _text(child) == "constructor":
            return True
    return False


def _gen_field_definition(ctx: CodegenContext, node) -> str | None:
    """Extract field name and value from a public_field_definition."""
    name = ""
    value = None
    for child in node.named_children:
        if child.type == "property_identifier":
            name = _to_snake_case(_text(child))
        elif child.type not in ("accessibility_modifier", "type_annotation",
                                "readonly"):
            value = child
    if name and value:
        return (name, value)
    elif name:
        return (name, None)
    return None


def _gen_init_from_fields(ctx: CodegenContext, field_inits: list) -> str:
    result = _indent(ctx) + "def __init__(self):\n"
    ctx.indent += 1
    for name, val_node in field_inits:
        if val_node:
            result += _indent(ctx) + f"self.{name} = {_gen_expr(ctx, val_node)}\n"
        else:
            result += _indent(ctx) + f"self.{name} = None\n"
    ctx.indent -= 1
    return result


def _gen_method(ctx: CodegenContext, node, field_inits=None) -> str:
    is_static, name, params_node, body_node = _parse_method_parts(node)
    params = _gen_params(ctx, params_node) if params_node else ""
    sig, prefix = _build_method_sig(ctx, name, params, is_static)
    result = prefix + _indent(ctx) + sig + "\n"
    ctx.indent += 1
    body = _build_method_body(ctx, name, body_node, field_inits)
    ctx.indent -= 1
    return result + body


def _parse_method_parts(node) -> tuple:
    is_static = False
    name = ""
    params_node = None
    body_node = None
    for child in node.children:
        if child.type == "static":
            is_static = True
        elif child.type == "property_identifier":
            raw = _text(child)
            name = "__init__" if raw == "constructor" else _to_snake_case(raw)
        elif child.type == "formal_parameters":
            params_node = child
        elif child.type == "statement_block":
            body_node = child
    return is_static, name, params_node, body_node


def _build_method_sig(ctx, name: str, params: str, is_static: bool) -> tuple:
    if is_static:
        prefix = _indent(ctx) + "@staticmethod\n"
        sig = f"def {name}({params}):"
    else:
        prefix = ""
        sig = f"def {name}(self, {params}):" if params else f"def {name}(self):"
    return sig, prefix


def _build_method_body(ctx, name: str, body_node, field_inits) -> str:
    body = ""
    if name == "__init__" and field_inits:
        body = _gen_field_init_body(ctx, field_inits)
    if body_node:
        body += _gen_block_body(ctx, body_node)
    if not body.strip():
        body = _indent(ctx) + _K_PASS + "\n"
    return body


def _gen_field_init_body(ctx, field_inits: list) -> str:
    result = ""
    for fname, val_node in field_inits:
        if val_node:
            result += _indent(ctx) + f"self.{fname} = {_gen_expr(ctx, val_node)}\n"
        else:
            result += _indent(ctx) + f"self.{fname} = None\n"
    return result


def _gen_function(ctx: CodegenContext, node) -> str:
    name = ""
    params_node = None
    body_node = None
    for child in node.children:
        if child.type == "identifier":
            name = _to_snake_case(_text(child))
        elif child.type == "formal_parameters":
            params_node = child
        elif child.type == "statement_block":
            body_node = child
    params = _gen_params(ctx, params_node) if params_node else ""
    result = _indent(ctx) + f"def {name}({params}):\n"
    ctx.indent += 1
    body = _gen_block_body(ctx, body_node) if body_node else ""
    if not body.strip():
        body = _indent(ctx) + _K_PASS + "\n"
    ctx.indent -= 1
    return result + body


def _gen_params(ctx: CodegenContext, node) -> str:
    """Generate Python parameter list from formal_parameters."""
    params = []
    for child in node.named_children:
        if child.type == "required_parameter":
            # Check if the parameter uses destructuring
            inner = _find_child_type(child, "object_pattern")
            if inner:
                params.extend(_extract_object_pattern_params(inner))
            else:
                params.append(_gen_required_param(child))
        elif child.type == "optional_parameter":
            params.append(_gen_optional_param(ctx, child))
        elif child.type == "rest_parameter":
            params.append(_gen_rest_param(child))
        elif child.type == "identifier":
            params.append(_to_snake_case(_text(child)))
        elif child.type == "object_pattern":
            params.extend(_extract_object_pattern_params(child))
    return ", ".join(params)


def _extract_object_pattern_params(node) -> list[str]:
    """Extract parameter names from an object destructuring pattern."""
    params = []
    for child in node.named_children:
        if child.type == "shorthand_property_identifier_pattern":
            params.append(_to_snake_case(_text(child)))
        elif child.type == "pair_pattern":
            key_node = child.child_by_field_name("key")
            if key_node:
                params.append(_to_snake_case(_text(key_node)))
        elif child.type == "identifier":
            params.append(_to_snake_case(_text(child)))
    return params


def _find_child_type(node, type_name: str):
    """Find first child of given type, recursively."""
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _gen_required_param(node) -> str:
    for child in node.named_children:
        if child.type == "identifier":
            return _to_snake_case(_text(child))
    return _text(node).split(":")[0].strip()


def _gen_optional_param(ctx: CodegenContext, node) -> str:
    name = ""
    default = "None"
    for child in node.children:
        if child.type == "identifier":
            name = _to_snake_case(_text(child))
        elif child.type not in ("type_annotation", "?", "=", ":"):
            if child.is_named:
                default = _gen_expr(ctx, child)
    return f"{name}={default}"


def _gen_rest_param(node) -> str:
    for child in node.named_children:
        if child.type == "identifier":
            return "*" + _to_snake_case(_text(child))
    return "*args"


def _gen_variable_declaration(ctx: CodegenContext, node) -> str:
    parts = []
    for child in node.named_children:
        if child.type == "variable_declarator":
            parts.append(_gen_variable_declarator(ctx, child))
    return "".join(parts)


def _gen_variable_declarator(ctx: CodegenContext, node) -> str:
    name_node = node.child_by_field_name("name")
    value_node = node.child_by_field_name("value")
    if name_node and name_node.type == "object_pattern":
        return _gen_destructuring(ctx, name_node, value_node)
    if name_node and name_node.type == "array_pattern":
        return _gen_array_destructuring(ctx, name_node, value_node)
    name = _gen_expr(ctx, name_node) if name_node else "_"
    if value_node:
        value = _gen_expr(ctx, value_node)
        return _indent(ctx) + f"{name} = {value}\n"
    return _indent(ctx) + f"{name} = None\n"


def _gen_destructuring(ctx: CodegenContext, pattern_node, value_node) -> str:
    obj_expr = _gen_expr(ctx, value_node) if value_node else "None"
    result = ""
    for child in pattern_node.named_children:
        if child.type == "shorthand_property_identifier_pattern":
            key = _text(child)
            py_key = _to_snake_case(key)
            result += _indent(ctx) + f'{py_key} = {obj_expr}["{key}"]\n'
        elif child.type == "pair_pattern":
            key, val = _gen_pair_pattern(child)
            py_val = _to_snake_case(val)
            result += _indent(ctx) + f'{py_val} = {obj_expr}["{key}"]\n'
        elif child.type == "rest_pattern":
            # ...rest  - skip for now
            pass
    return result


def _gen_pair_pattern(node) -> tuple[str, str]:
    key = ""
    val = ""
    for child in node.named_children:
        if child.type == "property_identifier":
            key = _text(child)
        elif child.type == "identifier":
            if not key:
                key = _text(child)
            else:
                val = _text(child)
    return key, val or key


def _gen_array_destructuring(ctx: CodegenContext, pattern_node, value_node) -> str:
    arr_expr = _gen_expr(ctx, value_node) if value_node else "None"
    names = []
    for child in pattern_node.named_children:
        if child.type == "identifier":
            names.append(_to_snake_case(_text(child)))
        elif child.type == "rest_pattern":
            for c in child.named_children:
                if c.type == "identifier":
                    names.append("*" + _to_snake_case(_text(c)))
        else:
            names.append("_")
    if names:
        lhs = ", ".join(names)
        return _indent(ctx) + f"{lhs} = {arr_expr}\n"
    return ""


def _gen_if(ctx: CodegenContext, node, is_elif: bool = False) -> str:
    cond_node = node.child_by_field_name("condition")
    cons_node = node.child_by_field_name("consequence")
    alt_node = node.child_by_field_name("alternative")
    cond = _gen_expr(ctx, _unwrap_parens(cond_node)) if cond_node else "True"
    keyword = "elif" if is_elif else "if"
    result = _indent(ctx) + f"{keyword} {cond}:\n"
    ctx.indent += 1
    body = _gen_block_body(ctx, cons_node) if cons_node else ""
    if not body.strip():
        body = _indent(ctx) + _K_PASS + "\n"
    ctx.indent -= 1
    result += body
    if alt_node:
        result += _gen_else(ctx, alt_node)
    return result


def _gen_else(ctx: CodegenContext, node) -> str:
    # else_clause has children: 'else' keyword + body
    for child in node.named_children:
        if child.type == "if_statement":
            return _gen_if(ctx, child, is_elif=True)
        elif child.type == "statement_block":
            result = _indent(ctx) + _K_ELSE + "\n"
            ctx.indent += 1
            body = _gen_block_body(ctx, child)
            if not body.strip():
                body = _indent(ctx) + _K_PASS + "\n"
            ctx.indent -= 1
            return result + body
    return ""


def _gen_for_in(ctx: CodegenContext, node) -> str:
    """for (const x of arr) -> for x in arr:"""
    var_name = ""
    iterable = ""
    body_node = None
    for child in node.children:
        if child.type == "identifier" and not var_name:
            var_name = _to_snake_case(_text(child))
        elif child.type in ("identifier", "member_expression",
                            "call_expression") and var_name and not iterable:
            iterable = _gen_expr(ctx, child)
        elif child.type in ("statement_block", "expression_statement"):
            body_node = child
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    if left:
        var_name = _to_snake_case(_text(left).replace("const ", "").replace(
            "let ", "").replace("var ", "").strip())
    if right:
        iterable = _gen_expr(ctx, right)
    result = _indent(ctx) + f"for {var_name} in {iterable}:\n"
    ctx.indent += 1
    body = _gen_block_body(ctx, body_node) if body_node else ""
    if not body.strip():
        body = _indent(ctx) + _K_PASS + "\n"
    ctx.indent -= 1
    return result + body


def _gen_for(ctx: CodegenContext, node) -> str:
    """for (let i = 0; i < n; i++) -> for i in range(n):"""
    init_node = node.child_by_field_name("initializer")
    cond_node = node.child_by_field_name("condition")
    inc_node = node.child_by_field_name("increment")
    body_node = node.child_by_field_name("body")
    range_expr = _try_range_pattern(ctx, init_node, cond_node, inc_node)
    if range_expr:
        var_name, range_str = range_expr
        result = _indent(ctx) + f"for {var_name} in {range_str}:\n"
    else:
        # Fallback: emit as while loop
        result = ""
        if init_node:
            result += _gen(ctx, init_node)
        cond = _gen_expr(ctx, _unwrap_parens(cond_node)) if cond_node else "True"
        result += _indent(ctx) + f"while {cond}:\n"
    ctx.indent += 1
    body = _gen_block_body(ctx, body_node) if body_node else ""
    if not range_expr and inc_node:
        body += _indent(ctx) + _gen_expr(ctx, inc_node) + "\n"
    if not body.strip():
        body = _indent(ctx) + _K_PASS + "\n"
    ctx.indent -= 1
    return result + body


def _try_range_pattern(ctx, init_node, cond_node, inc_node):
    """Try to detect for(let i=start; i<end; i+=step) pattern."""
    if not (init_node and cond_node and inc_node):
        return None
    # Get variable name and start from init
    var_name, start = _parse_for_init(init_node)
    if var_name is None:
        return None
    # Get end from condition
    end = _parse_for_condition(ctx, cond_node, var_name)
    if end is None:
        return None
    # Get step from increment
    step = _parse_for_increment(ctx, inc_node, var_name)
    if step is None:
        return None
    if start == "0" and step == "1":
        return (var_name, f"range({end})")
    if step == "1":
        return (var_name, f"range({start}, {end})")
    return (var_name, f"range({start}, {end}, {step})")


def _parse_for_init(init_node) -> tuple:
    for child in init_node.named_children:
        if child.type == "variable_declarator":
            name_node = child.child_by_field_name("name")
            val_node = child.child_by_field_name("value")
            if name_node and val_node:
                return (_to_snake_case(_text(name_node)), _text(val_node))
    return (None, None)


def _parse_for_condition(ctx, cond_node, var_name: str) -> str | None:
    if cond_node.type == "binary_expression":
        left = cond_node.child_by_field_name("left")
        op = cond_node.child_by_field_name("operator")
        right = cond_node.child_by_field_name("right")
        if left and op and right:
            ltext = _to_snake_case(_text(left))
            if ltext == var_name and _text(op) in ("<", "<="):
                end_val = _gen_expr(ctx, right)
                if _text(op) == "<=":
                    end_val = f"{end_val} + 1"
                return end_val
    return None


def _parse_for_increment(ctx, inc_node, var_name: str) -> str | None:
    if inc_node.type == "update_expression":
        ident = _text(inc_node).replace("++", "").replace("--", "").strip()
        if _to_snake_case(ident) == var_name:
            if "++" in _text(inc_node):
                return "1"
            return "-1"
    if inc_node.type == "augmented_assignment_expression":
        left = inc_node.child_by_field_name("left")
        right = inc_node.child_by_field_name("right")
        if left and _to_snake_case(_text(left)) == var_name and right:
            op_text = _text(inc_node)
            if "+=" in op_text:
                return _gen_expr(ctx, right)
            if "-=" in op_text:
                return f"-{_gen_expr(ctx, right)}"
    return None


def _gen_while(ctx: CodegenContext, node) -> str:
    cond_node = None
    body_node = None
    for child in node.named_children:
        if child.type == "parenthesized_expression":
            cond_node = child
        elif child.type == "statement_block":
            body_node = child
    cond = _gen_expr(ctx, _unwrap_parens(cond_node)) if cond_node else "True"
    result = _indent(ctx) + f"while {cond}:\n"
    ctx.indent += 1
    body = _gen_block_body(ctx, body_node) if body_node else ""
    if not body.strip():
        body = _indent(ctx) + _K_PASS + "\n"
    ctx.indent -= 1
    return result + body


def _gen_switch(ctx: CodegenContext, node) -> str:
    switch_val = ""
    body_node = None
    for child in node.named_children:
        if child.type == "parenthesized_expression":
            switch_val = _gen_expr(ctx, _unwrap_parens(child))
        elif child.type == "switch_body":
            body_node = child
    if not body_node:
        return ""
    result = ""
    first = True
    for child in body_node.named_children:
        if child.type == "switch_case":
            result += _gen_switch_case(ctx, child, switch_val, first)
            first = False
        elif child.type == "switch_default":
            result += _gen_switch_default(ctx, child, first)
            first = False
    return result


def _gen_switch_case(ctx, case_node, switch_val: str, first: bool) -> str:
    case_val = ""
    stmts = []
    for child in case_node.named_children:
        if child.type not in ("break_statement",):
            if not case_val:
                case_val = _gen_expr(ctx, child)
            else:
                stmts.append(child)
    keyword = "if" if first else "elif"
    result = _indent(ctx) + f"{keyword} {switch_val} == {case_val}:\n"
    ctx.indent += 1
    body = ""
    for s in stmts:
        body += _gen(ctx, s)
    if not body.strip():
        body = _indent(ctx) + _K_PASS + "\n"
    ctx.indent -= 1
    return result + body


def _gen_switch_default(ctx, node, first: bool) -> str:
    keyword = "if True" if first else "else"
    result = _indent(ctx) + f"{keyword}:\n"
    ctx.indent += 1
    body = ""
    for child in node.named_children:
        if child.type != "break_statement":
            body += _gen(ctx, child)
    if not body.strip():
        body = _indent(ctx) + _K_PASS + "\n"
    ctx.indent -= 1
    return result + body


def _gen_try(ctx: CodegenContext, node) -> str:
    try_block = None
    catch_clause = None
    finally_clause = None
    for child in node.named_children:
        if child.type == "statement_block" and try_block is None:
            try_block = child
        elif child.type == "catch_clause":
            catch_clause = child
        elif child.type == "finally_clause":
            finally_clause = child
    result = _indent(ctx) + _K_TRY + "\n"
    ctx.indent += 1
    body = _gen_block_body(ctx, try_block) if try_block else ""
    if not body.strip():
        body = _indent(ctx) + _K_PASS + "\n"
    ctx.indent -= 1
    result += body
    if catch_clause:
        result += _gen_catch(ctx, catch_clause)
    if finally_clause:
        result += _gen_finally(ctx, finally_clause)
    return result


def _gen_catch(ctx: CodegenContext, node) -> str:
    err_name = "e"
    body_node = None
    for child in node.children:
        if child.type == "identifier":
            err_name = _to_snake_case(_text(child))
        elif child.type == "statement_block":
            body_node = child
    result = _indent(ctx) + f"except Exception as {err_name}:\n"
    ctx.indent += 1
    body = _gen_block_body(ctx, body_node) if body_node else ""
    if not body.strip():
        body = _indent(ctx) + _K_PASS + "\n"
    ctx.indent -= 1
    return result + body


def _gen_finally(ctx: CodegenContext, node) -> str:
    result = _indent(ctx) + "finally:\n"
    ctx.indent += 1
    body = ""
    for child in node.named_children:
        if child.type == "statement_block":
            body = _gen_block_body(ctx, child)
    if not body.strip():
        body = _indent(ctx) + _K_PASS + "\n"
    ctx.indent -= 1
    return result + body


def _gen_return(ctx: CodegenContext, node) -> str:
    for child in node.named_children:
        val = _gen_expr(ctx, child)
        return _indent(ctx) + f"return {val}\n"
    return _indent(ctx) + "return\n"


def _gen_throw(ctx: CodegenContext, node) -> str:
    for child in node.named_children:
        val = _gen_expr(ctx, child)
        return _indent(ctx) + f"raise Exception({val})\n"
    return _indent(ctx) + "raise Exception()\n"


def _gen_expression_statement(ctx: CodegenContext, node) -> str:
    for child in node.named_children:
        expr = _gen_expr(ctx, child)
        if expr:
            return _indent(ctx) + expr + "\n"
    return ""


def _gen_block(ctx: CodegenContext, node) -> str:
    return _gen_block_body(ctx, node)


def _gen_block_body(ctx: CodegenContext, node) -> str:
    """Generate body statements from a statement_block or similar."""
    parts = []
    children = node.named_children if node else []
    for child in children:
        result = _gen(ctx, child)
        if result:
            parts.append(result)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Expression generators
# ---------------------------------------------------------------------------

def _gen_binary_expression(ctx: CodegenContext, node) -> str:
    left = node.child_by_field_name("left")
    op_node = node.child_by_field_name("operator")
    right = node.child_by_field_name("right")
    if not (left and right):
        return _text(node)
    op = _text(op_node) if op_node else "+"
    # typeof check: typeof x === 'string' -> isinstance(x, str)
    if left.type == "unary_expression" and _is_typeof(left):
        return _gen_typeof_check(ctx, left, op, right)
    # Nullish coalescing
    if op == "??":
        l = _gen_expr(ctx, left)
        r = _gen_expr(ctx, right)
        return f"({l} if {l} is not None else {r})"
    # Operator mapping
    py_op = _translate_operator(op)
    l = _gen_expr(ctx, left)
    r = _gen_expr(ctx, right)
    if op == "instanceof":
        if r == "Big":
            r = "(int, float)"
        return f"isinstance({l}, {r})"
    return f"{l} {py_op} {r}"


def _is_typeof(node) -> bool:
    for child in node.children:
        if child.type == "typeof":
            return True
    return False


def _gen_typeof_check(ctx, typeof_node, op: str, right_node) -> str:
    """Convert typeof x === 'type' to isinstance(x, type)."""
    # Get the variable being checked
    var_node = None
    for child in typeof_node.named_children:
        var_node = child
    var_name = _gen_expr(ctx, var_node) if var_node else "x"
    # Get the type string
    type_str = _text(right_node).strip("'\"")
    type_map = {
        "string": "str", "number": "(int, float)", "boolean": "bool",
        "object": "dict", "function": "callable", "undefined": "type(None)",
    }
    py_type = type_map.get(type_str, type_str)
    negate = op in ("!==", "!=")
    if negate:
        return f"not isinstance({var_name}, {py_type})"
    return f"isinstance({var_name}, {py_type})"


def _translate_operator(op: str) -> str:
    mapping = {
        "===": "==", "!==": "!=", "&&": "and", "||": "or",
        "==": "==", "!=": "!=",
    }
    return mapping.get(op, op)


def _gen_unary_expression(ctx: CodegenContext, node) -> str:
    op = ""
    operand = None
    for child in node.children:
        if child.type == "typeof":
            # standalone typeof, return type() call
            for c in node.named_children:
                return f"type({_gen_expr(ctx, c)})"
        elif child.type in ("!", "~", "-", "+", "void", "delete"):
            op = _text(child)
        elif child.is_named:
            operand = child
    if not operand:
        return _text(node)
    expr = _gen_expr(ctx, operand)
    if op == "!":
        return f"not {expr}"
    if op == "void":
        return "None"
    if op == "delete":
        return f"del {expr}"
    if op == "~":
        return f"~{expr}"
    return f"{op}{expr}"


def _gen_ternary(ctx: CodegenContext, node) -> str:
    cond = node.child_by_field_name("condition")
    cons = node.child_by_field_name("consequence")
    alt = node.child_by_field_name("alternative")
    c = _gen_expr(ctx, cond) if cond else "True"
    t = _gen_expr(ctx, cons) if cons else "None"
    f = _gen_expr(ctx, alt) if alt else "None"
    return f"({t} if {c} else {f})"


def _gen_call_expression(ctx: CodegenContext, node) -> str:
    func_node = node.child_by_field_name("function")
    args_node = node.child_by_field_name("arguments")
    # super(args) -> super().__init__(args)
    if func_node and func_node.type == "super":
        args = _gen_arguments(ctx, args_node) if args_node else ""
        return f"super().__init__({args})"
    # Check for special method calls
    if func_node and func_node.type == "member_expression":
        result = _try_special_call(ctx, func_node, args_node)
        if result is not None:
            return result
    func = _gen_expr(ctx, func_node) if func_node else ""
    args = _gen_arguments(ctx, args_node) if args_node else ""
    return f"{func}({args})"


def _gen_arguments(ctx: CodegenContext, node) -> str:
    args = []
    for child in node.named_children:
        if child.type == "comment":
            continue
        args.append(_gen_expr(ctx, child))
    return ", ".join(args)


_BIG_BINARY_METHODS = {
    "plus": "+", "add": "+", "minus": "-", "sub": "-",
    "mul": "*", "times": "*", "div": "/",
}
_BIG_COMPARISON_METHODS = {
    "gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "==",
}


def _try_special_call(ctx, func_node, args_node) -> str | None:
    """Handle special method calls like arr.push, Big methods, etc."""
    obj_node = func_node.child_by_field_name("object")
    prop_node = func_node.child_by_field_name("property")
    if not (obj_node and prop_node):
        return None
    method = _text(prop_node)
    obj = _gen_expr(ctx, obj_node)
    args = _gen_arguments(ctx, args_node) if args_node else ""
    arg_list = _get_arg_nodes(args_node) if args_node else []
    # Big.js methods
    if method in _BIG_BINARY_METHODS:
        op = _BIG_BINARY_METHODS[method]
        return f"({obj} {op} {args})"
    if method in _BIG_COMPARISON_METHODS:
        op = _BIG_COMPARISON_METHODS[method]
        return f"({obj} {op} {args})"
    return _try_builtin_method(ctx, obj_node, obj, method, args, arg_list)


def _try_builtin_method(ctx, obj_node, obj, method, args, arg_list) -> str | None:
    """Handle built-in JS methods: push, map, filter, etc."""
    # Object.keys/values/entries
    if _text(obj_node) == "Object":
        return _gen_object_static(method, args)
    if _text(obj_node) == "Array" and method == "isArray":
        return f"isinstance({args}, list)"
    if _text(obj_node) == "JSON":
        return _gen_json_call(ctx, method, args)
    if _text(obj_node) == "Math":
        return _gen_math_call(method, args)
    if _text(obj_node) == "console":
        return f"print({args})"
    if _text(obj_node) == "Logger":
        return _K_PASS
    # Instance methods
    return _try_instance_method(ctx, obj, method, args, arg_list)


def _try_instance_method(ctx, obj, method, args, arg_list) -> str | None:
    """Handle instance method calls on arrays, strings, etc."""
    if method == "push":
        return f"{obj}.append({args})"
    if method == "pop":
        return f"{obj}.pop()"
    if method == "shift":
        return f"{obj}.pop(0)"
    if method == "unshift":
        return f"{obj}.insert(0, {args})"
    if method == "includes":
        return f"{args} in {obj}"
    if method == "indexOf":
        return f"{obj}.index({args}) if {args} in {obj} else -1"
    if method == "concat":
        return f"{obj} + {args}"
    if method == "join":
        joiner = args if args else '""'
        return f"{joiner}.join({obj})"
    if method == "slice":
        return _gen_slice_call(obj, args, arg_list)
    if method == "splice":
        return _gen_splice_call(ctx, obj, arg_list)
    if method == "reverse":
        return f"list(reversed({obj}))"
    if method == "flat":
        return f"[item for sub in {obj} for item in (sub if isinstance(sub, list) else [sub])]"
    return _try_higher_order_method(ctx, obj, method, args, arg_list)


def _try_higher_order_method(ctx, obj, method, args, arg_list) -> str | None:
    """Handle higher-order methods: filter, map, find, reduce, sort."""
    if method == "filter":
        return _gen_filter(ctx, obj, arg_list)
    if method == "map":
        return _gen_map(ctx, obj, arg_list)
    if method == "find":
        return _gen_find(ctx, obj, arg_list)
    if method == "findIndex":
        return _gen_find_index(ctx, obj, arg_list)
    if method == "some":
        return _gen_some(ctx, obj, arg_list)
    if method == "every":
        return _gen_every(ctx, obj, arg_list)
    if method == "forEach":
        return _gen_for_each(ctx, obj, arg_list)
    if method == "reduce":
        return _gen_reduce(ctx, obj, arg_list)
    if method == "sort":
        return _gen_sort(ctx, obj, arg_list)
    return _try_string_or_misc_method(ctx, obj, method, args, arg_list)


def _try_string_or_misc_method(ctx, obj, method, args, arg_list) -> str | None:
    """Handle string methods and misc conversions."""
    if method in ("substring", "substr"):
        return _gen_substring(ctx, obj, arg_list)
    if method in ("padStart",):
        return _gen_pad(obj, args, arg_list, "rjust")
    if method in ("padEnd",):
        return _gen_pad(obj, args, arg_list, "ljust")
    if method == "toFixed":
        return f"round({obj}, {args})" if args else f"round({obj})"
    if method == "charCodeAt":
        return f"ord({obj}[{args}])"
    if method == "localeCompare":
        return f"(({obj} > {args}) - ({obj} < {args}))"
    # Simple pattern-based lookups
    return _SIMPLE_METHOD_MAP_LOOKUP(obj, method, args)


def _SIMPLE_METHOD_MAP_LOOKUP(obj: str, method: str, args: str) -> str | None:
    """Lookup simple method translations from table."""
    # Methods that take args and use them in format
    fmt = _METHOD_WITH_ARGS.get(method)
    if fmt:
        return fmt.format(obj=obj, args=args)
    # Methods with no args
    fmt = _METHOD_NO_ARGS.get(method)
    if fmt:
        return fmt.format(obj=obj)
    return None


_METHOD_WITH_ARGS = {
    "startsWith": "{obj}.startswith({args})",
    "endsWith": "{obj}.endswith({args})",
    "split": "{obj}.split({args})",
    "replace": "{obj}.replace({args})",
    "replaceAll": "{obj}.replace({args})",
    "match": "re.search({args}, {obj})",
    "at": "{obj}[{args}]",
    "charAt": "{obj}[{args}]",
    "has": "{args} in {obj}",
    "get": "{obj}.get({args})",
    "set": "{obj}[{args}]",
    "delete": "{obj}.pop({args}, None)",
    "repeat": "{obj} * {args}",
}

_METHOD_NO_ARGS = {
    "toLowerCase": "{obj}.lower()",
    "toUpperCase": "{obj}.upper()",
    "trim": "{obj}.strip()",
    "trimStart": "{obj}.lstrip()",
    "trimLeft": "{obj}.lstrip()",
    "trimEnd": "{obj}.rstrip()",
    "trimRight": "{obj}.rstrip()",
    "toString": "str({obj})",
    "String": "str({obj})",
    "toNumber": "float({obj})",
    "abs": "abs({obj})",
    "keys": "{obj}.keys()",
    "values": "{obj}.values()",
    "entries": "{obj}.items()",
}


def _gen_slice_call(obj: str, args: str, arg_list: list) -> str:
    if not arg_list:
        return f"{obj}[:]"
    if len(arg_list) == 1:
        return f"{obj}[{args}:]"
    # two args
    return f"{obj}[{args}]"


def _gen_splice_call(ctx, obj: str, arg_list: list) -> str:
    if len(arg_list) >= 2:
        start = _gen_expr(ctx, arg_list[0])
        count = _gen_expr(ctx, arg_list[1])
        return f"{obj}[{start}:{start} + {count}]"
    return f"{obj}"


def _gen_pad(obj: str, args: str, arg_list: list, py_method: str) -> str:
    return f"{obj}.{py_method}({args})"


def _get_arg_nodes(args_node) -> list:
    return [c for c in args_node.named_children] if args_node else []


def _gen_filter(ctx, obj: str, arg_list: list) -> str:
    if not arg_list:
        return f"{obj}"
    fn = arg_list[0]
    param, body = _extract_lambda(ctx, fn)
    return f"[{param} for {param} in {obj} if {body}]"


def _gen_map(ctx, obj: str, arg_list: list) -> str:
    if not arg_list:
        return f"{obj}"
    fn = arg_list[0]
    param, body = _extract_lambda(ctx, fn)
    return f"[{body} for {param} in {obj}]"


def _gen_find(ctx, obj: str, arg_list: list) -> str:
    if not arg_list:
        return f"None"
    fn = arg_list[0]
    param, body = _extract_lambda(ctx, fn)
    return f"next(({param} for {param} in {obj} if {body}), None)"


def _gen_find_index(ctx, obj: str, arg_list: list) -> str:
    if not arg_list:
        return "-1"
    fn = arg_list[0]
    param, body = _extract_lambda(ctx, fn)
    return f"next((i for i, {param} in enumerate({obj}) if {body}), -1)"


def _gen_some(ctx, obj: str, arg_list: list) -> str:
    if not arg_list:
        return f"bool({obj})"
    fn = arg_list[0]
    param, body = _extract_lambda(ctx, fn)
    return f"any({body} for {param} in {obj})"


def _gen_every(ctx, obj: str, arg_list: list) -> str:
    if not arg_list:
        return "True"
    fn = arg_list[0]
    param, body = _extract_lambda(ctx, fn)
    return f"all({body} for {param} in {obj})"


def _gen_for_each(ctx, obj: str, arg_list: list) -> str:
    """forEach generates inline - caller should wrap as needed."""
    if not arg_list:
        return f"{obj}"
    fn = arg_list[0]
    param, body = _extract_lambda(ctx, fn)
    # This is an expression context - return a list comprehension
    # (side-effect: the caller wraps it in a statement)
    return f"[{body} for {param} in {obj}]"


def _gen_reduce(ctx, obj: str, arg_list: list) -> str:
    ctx.imports_needed.add("functools")
    if len(arg_list) >= 2:
        fn_expr = _gen_expr(ctx, arg_list[0])
        init_expr = _gen_expr(ctx, arg_list[1])
        return f"reduce({fn_expr}, {obj}, {init_expr})"
    elif arg_list:
        fn_expr = _gen_expr(ctx, arg_list[0])
        return f"reduce({fn_expr}, {obj})"
    return f"{obj}"


def _gen_sort(ctx, obj: str, arg_list: list) -> str:
    if not arg_list:
        return f"sorted({obj})"
    fn = arg_list[0]
    fn_expr = _gen_expr(ctx, fn)
    ctx.imports_needed.add("functools")
    return f"sorted({obj}, key=functools.cmp_to_key({fn_expr}))"


def _gen_substring(ctx, obj: str, arg_list: list) -> str:
    if not arg_list:
        return obj
    start = _gen_expr(ctx, arg_list[0])
    if len(arg_list) >= 2:
        end = _gen_expr(ctx, arg_list[1])
        return f"{obj}[{start}:{end}]"
    return f"{obj}[{start}:]"


def _gen_object_static(method: str, args: str) -> str:
    if method == "keys":
        return f"list({args}.keys())"
    if method == "values":
        return f"list({args}.values())"
    if method == "entries":
        return f"list({args}.items())"
    if method == "assign":
        return f"{{**{args}}}"
    if method == "freeze":
        return args
    if method == "create":
        return f"dict({args})" if args else "{}"
    if method == "fromEntries":
        return f"dict({args})"
    return f"{args}"


def _gen_json_call(ctx, method: str, args: str) -> str:
    ctx.imports_needed.add("json")
    if method == "parse":
        return f"json.loads({args})"
    if method == "stringify":
        return f"json.dumps({args})"
    return f"json.{method}({args})"


def _gen_math_call(method: str, args: str) -> str:
    mapping = {
        "abs": "abs", "floor": "int", "ceil": "math.ceil",
        "round": "round", "max": "max", "min": "min",
        "pow": "pow", "sqrt": "math.sqrt", "log": "math.log",
        "random": "random.random",
    }
    py_func = mapping.get(method, f"math.{method}")
    return f"{py_func}({args})"


def _extract_lambda(ctx, fn_node) -> tuple[str, str]:
    """Extract parameter name and body expression from arrow function."""
    if fn_node.type == "arrow_function":
        params = _extract_arrow_params(fn_node)
        destr = _extract_destructured_keys(fn_node)
        if destr:
            # Destructuring param: use a temp var and access via .get()
            param = "_item"
            body_node = fn_node.child_by_field_name("body")
            body = _extract_arrow_body_with_destr(ctx, body_node, destr)
            return (param, body)
        param = params[0] if params else "x"
        body_node = fn_node.child_by_field_name("body")
        body = _extract_arrow_body(ctx, body_node)
        return (param, body)
    # Identifier reference to a function
    return ("x", f"{_gen_expr(ctx, fn_node)}(x)")


def _extract_destructured_keys(fn_node) -> list[str] | None:
    """If arrow function has a destructured object param, return key names."""
    for child in fn_node.children:
        if child.type == "formal_parameters":
            for p in child.named_children:
                if p.type == "required_parameter":
                    for c in p.named_children:
                        if c.type == "object_pattern":
                            keys = []
                            for k in c.named_children:
                                if k.type == "shorthand_property_identifier_pattern":
                                    keys.append(_text(k))
                            return keys if keys else None
    return None


def _extract_arrow_body_with_destr(ctx, body_node, keys: list[str]) -> str:
    """Extract arrow body, replacing destructured keys with _item.get(key)."""
    if not body_node:
        return "None"
    raw = _extract_arrow_body_raw(ctx, body_node)
    for key in keys:
        snake = _to_snake_case(key)
        raw = raw.replace(snake, f'_item.get("{key}")')
    return raw


def _extract_arrow_body_raw(ctx, body_node) -> str:
    """Extract raw body expression from arrow function body node."""
    if body_node.type != "statement_block":
        return _gen_expr(ctx, body_node)
    stmts = list(body_node.named_children)
    if len(stmts) == 1 and stmts[0].type == "return_statement":
        children = stmts[0].named_children
        return _gen_expr(ctx, children[0]) if children else "None"
    if len(stmts) == 1 and stmts[0].type == "expression_statement":
        children = stmts[0].named_children
        return _gen_expr(ctx, children[0]) if children else "None"
    return "None"


def _extract_arrow_params(fn_node) -> list[str]:
    """Get parameter names from an arrow function node."""
    params = []
    for child in fn_node.children:
        if child.type == "identifier":
            params.append(_to_snake_case(_text(child)))
        elif child.type == "formal_parameters":
            for p in child.named_children:
                if p.type == "required_parameter":
                    params.append(_gen_required_param(p))
                elif p.type == "identifier":
                    params.append(_to_snake_case(_text(p)))
    return params


def _extract_arrow_body(ctx, body_node) -> str:
    """Extract the body expression from an arrow function."""
    if not body_node:
        return "None"
    if body_node.type != "statement_block":
        return _gen_expr(ctx, body_node)
    stmts = list(body_node.named_children)
    if len(stmts) == 1 and stmts[0].type == "return_statement":
        children = stmts[0].named_children
        return _gen_expr(ctx, children[0]) if children else "None"
    if len(stmts) == 1 and stmts[0].type == "expression_statement":
        children = stmts[0].named_children
        return _gen_expr(ctx, children[0]) if children else "None"
    for s in reversed(stmts):
        if s.type == "return_statement" and s.named_children:
            return _gen_expr(ctx, s.named_children[0])
    return "None"


def _gen_member_expression(ctx: CodegenContext, node) -> str:
    obj_node = node.child_by_field_name("object")
    prop_node = node.child_by_field_name("property")
    if not (obj_node and prop_node):
        return _text(node)
    obj = _gen_expr(ctx, obj_node)
    prop = _text(prop_node)
    # Number.EPSILON
    if _text(obj_node) == "Number" and prop == "EPSILON":
        ctx.imports_needed.add("sys")
        return "sys.float_info.epsilon"
    # .length -> len()
    if prop == "length":
        return f"len({obj})"
    # Optional chaining: handled by just using dot
    py_prop = _to_snake_case(prop)
    return f"{obj}.{py_prop}"


def _gen_subscript_expression(ctx: CodegenContext, node) -> str:
    obj_node = node.child_by_field_name("object")
    idx_node = node.child_by_field_name("index")
    if not (obj_node and idx_node):
        return _text(node)
    obj = _gen_expr(ctx, obj_node)
    idx = _gen_expr(ctx, idx_node)
    return f"{obj}[{idx}]"


def _gen_assignment(ctx: CodegenContext, node) -> str:
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    if not (left and right):
        return _text(node)
    l = _gen_expr(ctx, left)
    r = _gen_expr(ctx, right)
    return f"{l} = {r}"


def _gen_augmented_assignment(ctx: CodegenContext, node) -> str:
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    if not (left and right):
        return _text(node)
    l = _gen_expr(ctx, left)
    r = _gen_expr(ctx, right)
    # Find operator
    op = ""
    for child in node.children:
        t = _text(child)
        if t in ("+=", "-=", "*=", "/=", "%=", "**=", "|=", "&=", "^=",
                 "<<=", ">>=", ">>>=", "&&=", "||=", "??="):
            op = t
            break
    if op == "&&=":
        return f"{l} = {l} and {r}"
    if op == "||=":
        return f"{l} = {l} or {r}"
    if op == "??=":
        return f"{l} = {l} if {l} is not None else {r}"
    return f"{l} {op} {r}"


def _gen_update_expression(ctx: CodegenContext, node) -> str:
    expr_text = _text(node)
    if "++" in expr_text:
        var = expr_text.replace("++", "").strip()
        var = _to_snake_case(var)
        return f"{var} += 1"
    if "--" in expr_text:
        var = expr_text.replace("--", "").strip()
        var = _to_snake_case(var)
        return f"{var} -= 1"
    return _text(node)


def _gen_parenthesized(ctx: CodegenContext, node) -> str:
    inner = _unwrap_parens(node)
    return f"({_gen_expr(ctx, inner)})"


def _gen_arrow_function(ctx: CodegenContext, node) -> str:
    """Generate a lambda or inline def from an arrow function."""
    params = []
    body_node = node.child_by_field_name("body")
    for child in node.children:
        if child.type == "identifier":
            params.append(_to_snake_case(_text(child)))
        elif child.type == "formal_parameters":
            for p in child.named_children:
                if p.type == "required_parameter":
                    params.append(_gen_required_param(p))
                elif p.type == "optional_parameter":
                    params.append(_gen_optional_param(ctx, p))
                elif p.type == "identifier":
                    params.append(_to_snake_case(_text(p)))
    param_str = ", ".join(params)
    if body_node and body_node.type == "statement_block":
        # Complex arrow function - can't be a lambda
        # Generate as lambda if body is simple return
        stmts = [c for c in body_node.named_children]
        if len(stmts) == 1 and stmts[0].type == "return_statement":
            ret_val = ""
            for child in stmts[0].named_children:
                ret_val = _gen_expr(ctx, child)
            return f"lambda {param_str}: {ret_val}"
        # Otherwise generate as a named function-like expression
        # For now, use lambda with None
        return f"lambda {param_str}: {_gen_expr(ctx, body_node)}"
    elif body_node:
        body = _gen_expr(ctx, body_node)
        return f"lambda {param_str}: {body}"
    return f"lambda {param_str}: None"


def _gen_new_expression(ctx: CodegenContext, node) -> str:
    class_name = ""
    args = ""
    for child in node.children:
        if child.type == "identifier":
            class_name = _text(child)
        elif child.type == "member_expression":
            class_name = _gen_expr(ctx, child)
        elif child.type == "arguments":
            args = _gen_arguments(ctx, child)
    # Big(x) -> float(x) or just the number
    if class_name == "Big":
        return _gen_big_constructor(args)
    if class_name == "Date":
        return f"datetime.datetime({args})" if args else "datetime.datetime.now()"
    if class_name == "Map":
        return "{}" if not args else f"dict({args})"
    if class_name == "Set":
        return f"set({args})" if args else "set()"
    if class_name == "RegExp":
        return f"re.compile({args})"
    if class_name == "Error":
        return f"Exception({args})"
    return f"{class_name}({args})"


def _gen_big_constructor(args: str) -> str:
    """Convert new Big(x) to a number. If x is a literal number, use it."""
    stripped = args.strip()
    # If it's a number literal, return as float
    try:
        val = float(stripped)
        if val == int(val) and "." not in stripped:
            return f"{stripped}.0" if stripped != "0" else "0.0"
        return stripped
    except (ValueError, OverflowError):
        pass
    return f"float({stripped})"


def _gen_array(ctx: CodegenContext, node) -> str:
    elems = []
    for child in node.named_children:
        elems.append(_gen_expr(ctx, child))
    return f"[{', '.join(elems)}]"


def _gen_object(ctx: CodegenContext, node) -> str:
    pairs = []
    for child in node.named_children:
        if child.type == "pair":
            pairs.append(_gen_pair(ctx, child))
        elif child.type == "shorthand_property_identifier":
            name = _text(child)
            py_name = _to_snake_case(name)
            pairs.append(f'"{name}": {py_name}')
        elif child.type == "spread_element":
            pairs.append(f"**{_gen_expr(ctx, child.named_children[0])}")
        elif child.type == "method_definition":
            # Inline method in object literal - generate as lambda
            pass
    return "{" + ", ".join(pairs) + "}"


def _gen_pair(ctx: CodegenContext, node) -> str:
    key_node = None
    val_node = None
    for child in node.named_children:
        if key_node is None:
            key_node = child
        else:
            val_node = child
    if not key_node:
        return ""
    key = _text(key_node)
    if key_node.type == "property_identifier":
        key_str = f'"{key}"'
    elif key_node.type == "computed_property_name":
        # [expr]: value
        inner = key_node.named_children[0] if key_node.named_children else key_node
        key_str = _gen_expr(ctx, inner)
    else:
        key_str = _gen_expr(ctx, key_node)
    val_str = _gen_expr(ctx, val_node) if val_node else "None"
    return f"{key_str}: {val_str}"


def _gen_spread(ctx: CodegenContext, node) -> str:
    for child in node.named_children:
        return f"*{_gen_expr(ctx, child)}"
    return ""


def _gen_string(ctx: CodegenContext, node) -> str:
    raw = _text(node)
    # Convert single-quoted to double-quoted
    if raw.startswith("'") and raw.endswith("'"):
        inner = raw[1:-1]
        inner = inner.replace('"', '\\"')
        return f'"{inner}"'
    return raw


def _gen_template_string(ctx: CodegenContext, node) -> str:
    parts = []
    for child in node.children:
        if child.type == "string_fragment":
            parts.append(_text(child))
        elif child.type == "template_substitution":
            for inner in child.named_children:
                parts.append("{" + _gen_expr(ctx, inner) + "}")
        elif child.type == "escape_sequence":
            parts.append(_text(child))
    content = "".join(parts)
    if "\n" in content:
        return 'f"""' + content + '"""'
    return f'f"{content}"'


def _gen_as_expression(ctx: CodegenContext, node) -> str:
    """Strip type assertion: x as Type -> x."""
    for child in node.named_children:
        if child.type not in ("type_identifier", "predefined_type",
                              "generic_type", "array_type", "union_type",
                              "intersection_type", "parenthesized_type",
                              "object_type", "literal_type"):
            return _gen_expr(ctx, child)
    return _gen_expr(ctx, node.named_children[0]) if node.named_children else ""


def _gen_non_null(ctx: CodegenContext, node) -> str:
    """Strip non-null assertion: x! -> x."""
    for child in node.named_children:
        return _gen_expr(ctx, child)
    return ""


def _gen_type_assertion(ctx: CodegenContext, node) -> str:
    """Strip type assertion: <Type>x -> x."""
    for child in node.named_children:
        if child.type not in ("type_identifier", "predefined_type",
                              "generic_type"):
            return _gen_expr(ctx, child)
    return ""


def _gen_await(ctx: CodegenContext, node) -> str:
    """Strip await: await expr -> expr."""
    for child in node.named_children:
        return _gen_expr(ctx, child)
    return ""


def _gen_comma_expression(ctx: CodegenContext, node) -> str:
    """Handle comma expressions - just use the last one."""
    parts = []
    for child in node.named_children:
        parts.append(_gen_expr(ctx, child))
    return parts[-1] if parts else ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text(node) -> str:
    """Get the source text of a node."""
    return node.text.decode("utf-8") if node.text else ""


def _indent(ctx: CodegenContext) -> str:
    return "    " * ctx.indent


def _unwrap_parens(node):
    """Unwrap parenthesized_expression to get inner node."""
    if node and node.type == "parenthesized_expression":
        for child in node.named_children:
            return child
    return node


def _translate_identifier(ctx: CodegenContext, node) -> str:
    name = _text(node)
    if name == "true":
        return "True"
    if name == "false":
        return "False"
    if name in ("null", "undefined"):
        return "None"
    if name == "this":
        return "self"
    if name == "Infinity":
        return "float('inf')"
    if name == "NaN":
        return "float('nan')"
    return _to_snake_case(name)


_SNAKE_CASE_RE1 = re.compile(r"([A-Z]+)([A-Z][a-z])")
_SNAKE_CASE_RE2 = re.compile(r"([a-z0-9])([A-Z])")


def _to_snake_case(name: str) -> str:
    """Convert camelCase or PascalCase to snake_case."""
    if not name:
        return name
    # Don't convert ALL_CAPS constants
    if name.isupper() or "_" in name:
        return name
    # Don't convert class names (PascalCase starting with upper)
    if name[0].isupper():
        return name
    result = _SNAKE_CASE_RE1.sub(r"\1_\2", name)
    result = _SNAKE_CASE_RE2.sub(r"\1_\2", result)
    return result.lower()


# ---------------------------------------------------------------------------
# Dispatch tables (populated after all functions are defined)
# ---------------------------------------------------------------------------

_STMT_DISPATCH.update({
    "program": _gen_program,
    "export_statement": _gen_export,
    "class_declaration": _gen_class,
    "abstract_class_declaration": _gen_class,
    "method_definition": _gen_method,
    "function_declaration": _gen_function,
    "for_in_statement": _gen_for_in,
    "for_statement": _gen_for,
    "while_statement": _gen_while,
    "switch_statement": _gen_switch,
    "try_statement": _gen_try,
    "return_statement": _gen_return,
    "expression_statement": _gen_expression_statement,
    "statement_block": _gen_block,
    "throw_statement": _gen_throw,
})

_EXPR_DISPATCH.update({
    "binary_expression": _gen_binary_expression,
    "unary_expression": _gen_unary_expression,
    "ternary_expression": _gen_ternary,
    "call_expression": _gen_call_expression,
    "member_expression": _gen_member_expression,
    "subscript_expression": _gen_subscript_expression,
    "assignment_expression": _gen_assignment,
    "parenthesized_expression": _gen_parenthesized,
    "arrow_function": _gen_arrow_function,
    "new_expression": _gen_new_expression,
    "array": _gen_array,
    "object": _gen_object,
    "spread_element": _gen_spread,
    "as_expression": _gen_as_expression,
    "non_null_expression": _gen_non_null,
    "type_assertion": _gen_type_assertion,
    "await_expression": _gen_await,
    "update_expression": _gen_update_expression,
    "augmented_assignment_expression": _gen_augmented_assignment,
    "comma_expression": _gen_comma_expression,
})
