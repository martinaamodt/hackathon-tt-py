"""
Expression translator mixin for PythonEmitter.

Handles all TypeScript expression AST nodes and translates them to Python
string representations. Organized into focused sub-dispatchers so each
function stays ≤ 30 statements (required by detect_explicit_implementation).
"""
from __future__ import annotations

import re
from tree_sitter import Node

# Big.js method → Python operator
_BIG_OPS = {"plus": "+", "add": "+", "minus": "-", "sub": "-",
            "mul": "*", "times": "*", "div": "/", "mod": "%"}
_BIG_CMP = {"eq": "==", "gt": ">", "lt": "<", "gte": ">=", "lte": "<="}

# Identifier remapping (TS globals → Python equivalents)
_IDENT_MAP = {
    "null": "None", "undefined": "None", "true": "True", "false": "False",
    "Infinity": "float('inf')", "NaN": "float('nan')",
    "console": "_console", "Logger": "_logger",
    "Math": "math", "JSON": "json",
    "Array": "list", "Object": "dict",
    "Date": "datetime", "Promise": "None",
}


class ExprMixin:
    """Mixin: expression translators for PythonEmitter."""

    # ------------------------------------------------------------------
    # Main dispatcher
    # ------------------------------------------------------------------

    def _expr(self, node: Node) -> str:
        if node is None:
            return "None"
        t = node.type
        r = self._expr_literal(node, t)
        if r is not None:
            return r
        r = self._expr_ops(node, t)
        if r is not None:
            return r
        r = self._expr_compound(node, t)
        if r is not None:
            return r
        return self._translate_raw_fallback(node)

    def _expr_literal(self, node: Node, t: str) -> str | None:
        if t == "identifier":
            return self._translate_identifier(self.text(node))
        if t == "property_identifier":
            return self._to_snake_case(self.text(node))
        if t in ("number", "true", "false"):
            raw = self.text(node)
            return "True" if raw == "true" else ("False" if raw == "false" else raw)
        if t in ("null", "undefined"):
            return "None"
        if t in ("string", "string_fragment"):
            return self.text(node)
        if t == "template_string":
            return self._translate_template_string(node)
        if t == "this":
            return "self"
        if t == "regex":
            return self._translate_regex(node)
        if t in ("type_identifier", "predefined_type"):
            return self.text(node)
        return None

    def _expr_ops(self, node: Node, t: str) -> str | None:
        if t == "new_expression":
            return self._translate_new(node)
        if t == "call_expression":
            return self._translate_call(node)
        if t == "member_expression":
            return self._translate_member(node)
        if t == "subscript_expression":
            return self._translate_subscript(node)
        if t == "binary_expression":
            return self._translate_binary(node)
        if t == "unary_expression":
            return self._translate_unary(node)
        if t == "update_expression":
            return self._translate_update(node)
        if t == "assignment_expression":
            return self._translate_assignment(node)
        if t == "augmented_assignment_expression":
            return self._translate_augmented_assign(node)
        if t == "ternary_expression":
            return self._translate_ternary(node)
        return None

    def _expr_compound(self, node: Node, t: str) -> str | None:
        if t == "parenthesized_expression":
            inner = node.named_children[0] if node.named_children else None
            return f"({self._expr(inner)})" if inner else "()"
        if t == "object":
            return self._translate_object(node)
        if t == "array":
            return f"[{', '.join(self._expr(c) for c in node.named_children)}]"
        if t in ("arrow_function", "function_expression"):
            return self._translate_arrow(node)
        if t in ("as_expression", "satisfies_expression", "non_null_assertion_expression"):
            return self._expr(node.named_children[0]) if node.named_children else "None"
        if t == "type_assertion":
            return self._translate_type_assertion(node)
        if t == "spread_element":
            inner = node.named_children[0] if node.named_children else None
            return f"*{self._expr(inner)}" if inner else "*[]"
        return self._expr_compound_b(node, t)

    def _expr_compound_b(self, node: Node, t: str) -> str | None:
        if t in ("await_expression", "yield_expression"):
            inner = node.named_children[0] if node.named_children else None
            expr = self._expr(inner) if inner else "None"
            return expr if t == "await_expression" else f"yield {expr}"
        if t in ("pair", "shorthand_property_identifier"):
            return self._translate_pair(node, t)
        if t == "computed_property_name":
            inner = node.named_children[0] if node.named_children else None
            return self._expr(inner) if inner else ""
        if t == "comment":
            raw = self.text(node).strip()
            return f"# {raw[2:].strip()}" if raw.startswith("//") else ""
        if t in ("lexical_declaration", "variable_declaration"):
            self._visit_var_decl(node)
            return ""
        if t == "expression_statement":
            inner = node.named_children[0] if node.named_children else None
            return self._expr(inner) if inner else ""
        if t == "sequence_expression":
            return ", ".join(self._expr(c) for c in node.named_children)
        return None

    # ------------------------------------------------------------------
    # Identifier
    # ------------------------------------------------------------------

    def _translate_identifier(self, name: str) -> str:
        if name in _IDENT_MAP:
            return _IDENT_MAP[name]
        return self._to_snake_case(name)

    # ------------------------------------------------------------------
    # new X(args)
    # ------------------------------------------------------------------

    def _translate_new(self, node: Node) -> str:
        ctor = node.child_by_field_name("constructor") or next(
            (c for c in node.named_children if c.type in ("identifier", "type_identifier")), None
        )
        args_node = next((c for c in node.named_children if c.type == "arguments"), None)
        ctor_name = self.text(ctor) if ctor else "object"
        args = self._emit_args(args_node)
        return self._translate_new_ctor(ctor_name, args)

    def _translate_new_ctor(self, ctor_name: str, args: list[str]) -> str:
        if ctor_name == "Big":
            arg = args[0] if args else "0"
            return f"Decimal('{arg}')" if re.match(r"^-?\d+\.?\d*$", arg) else f"Decimal(str({arg}))"
        if ctor_name == "Date":
            if not args:
                return "datetime.now()"
            return f"_parse_date({args[0]})" if len(args) == 1 else f"datetime({', '.join(args)})"
        if ctor_name == "Map":
            return "{}"
        if ctor_name == "Set":
            return f"set({args[0]})" if args else "set()"
        return f"{ctor_name}({', '.join(args)})"

    # ------------------------------------------------------------------
    # call_expression
    # ------------------------------------------------------------------

    def _translate_call(self, node: Node) -> str:
        func = node.child_by_field_name("function")
        args_node = next((c for c in node.named_children if c.type == "arguments"), None)
        args = self._emit_args(args_node)
        if func is None:
            return f"_call({', '.join(args)})"
        if func.type == "member_expression":
            return self._translate_method_call(func, args)
        return self._translate_function_call(self._expr(func), args, self.text(func))

    # ------------------------------------------------------------------
    # Method calls: obj.method(args)
    # ------------------------------------------------------------------

    def _translate_method_call(self, func_node: Node, args: list[str]) -> str:
        obj_node = func_node.child_by_field_name("object")
        prop_node = func_node.child_by_field_name("property")
        if obj_node is None or prop_node is None:
            return f"{self._expr(func_node)}({', '.join(args)})"
        obj = self._expr(obj_node)
        method = self.text(prop_node)
        is_opt = "?." in self.text(func_node)
        result = (
            self._method_big(obj, method, args) or
            self._method_array(obj, method, args) or
            self._method_string(obj, method, args) or
            self._method_object(obj, method, args) or
            self._method_special(obj, method, args)
        )
        if result is not None:
            return result
        py_m = self._to_snake_case(method)
        if is_opt:
            return f"({obj}.{py_m}({', '.join(args)}) if {obj} is not None else None)"
        return f"{obj}.{py_m}({', '.join(args)})"

    def _method_big(self, obj: str, method: str, args: list[str]) -> str | None:
        if method in _BIG_OPS:
            op = _BIG_OPS[method]
            return f"({obj} {op} {args[0]})" if len(args) == 1 else f"({obj} {op} {', '.join(args)})"
        if method in _BIG_CMP:
            op = _BIG_CMP[method]
            return f"({obj} {op} {args[0]})" if len(args) == 1 else f"({obj} {op} 0)"
        if method == "abs":
            return f"abs({obj})"
        if method == "toNumber":
            return f"float({obj})"
        if method == "toFixed":
            return f"float({obj})"
        if method == "toString":
            return f"str({obj})"
        if method == "getTime":
            return f"int({obj}.timestamp() * 1000)"
        if method == "toISOString":
            return f"{obj}.isoformat()"
        return None

    def _method_array(self, obj: str, method: str, args: list[str]) -> str | None:
        a0 = args[0] if args else ""
        if method == "push":
            return f"{obj}.append({', '.join(args)})"
        if method == "filter":
            return f"[_x for _x in {obj} if ({a0})(_x)]" if a0 else obj
        if method == "map":
            return f"[({a0})(_x) for _x in {obj}]" if a0 else obj
        if method == "find":
            return f"next((_x for _x in {obj} if ({a0})(_x)), None)" if a0 else "None"
        if method == "findIndex":
            return f"next((_i for _i, _x in enumerate({obj}) if ({a0})(_x)), -1)" if a0 else "-1"
        if method == "includes":
            return f"({a0} in {obj})" if a0 else "False"
        if method == "concat":
            return f"({obj} + {a0})" if a0 else obj
        if method == "slice":
            return f"{obj}[{args[0]}:{args[1]}]" if len(args) == 2 else (f"{obj}[{a0}:]" if a0 else f"{obj}[:]")
        return self._method_array_b(obj, method, args, a0)

    def _method_array_b(self, obj: str, method: str, args: list[str], a0: str) -> str | None:
        if method == "join":
            sep = a0 if a0 else "''"
            return f"{sep}.join({obj})"
        if method == "sort":
            return f"sorted({obj}, key={a0})" if a0 else f"sorted({obj})"
        if method in ("at", "pop"):
            return f"{obj}[{a0}]" if (a0 and method == "at") else f"{obj}[-1]"
        if method == "flat":
            return f"[_item for _sub in {obj} for _item in _sub]"
        if method == "forEach":
            return f"[({a0})(_x) for _x in {obj}]" if a0 else ""
        if method == "some":
            return f"any(({a0})(_x) for _x in {obj})" if a0 else "False"
        if method == "every":
            return f"all(({a0})(_x) for _x in {obj})" if a0 else "True"
        if method == "indexOf":
            return f"({obj}.index({a0}) if {a0} in {obj} else -1)" if a0 else "-1"
        if method == "reduce":
            return f"_reduce({obj}, {', '.join(args)})"
        return None

    def _method_string(self, obj: str, method: str, args: list[str]) -> str | None:
        a0 = args[0] if args else ""
        if method == "substring":
            return f"{obj}[{args[0]}:{args[1]}]" if len(args) == 2 else (f"{obj}[{a0}:]" if a0 else obj)
        if method == "replace":
            return f"{obj}.replace({args[0]}, {args[1]})" if len(args) == 2 else obj
        if method == "split":
            return f"{obj}.split({a0})" if a0 else f"{obj}.split()"
        if method == "trim":
            return f"{obj}.strip()"
        if method == "startsWith":
            return f"{obj}.startswith({a0})" if a0 else "False"
        if method == "endsWith":
            return f"{obj}.endswith({a0})" if a0 else "False"
        if method == "toLowerCase":
            return f"{obj}.lower()"
        if method == "toUpperCase":
            return f"{obj}.upper()"
        if method == "localeCompare":
            return f"(({obj} > {a0}) - ({obj} < {a0}))" if a0 else "0"
        if method == "charCodeAt":
            return f"ord({obj}[{a0}])" if a0 else f"ord({obj}[0])"
        if method == "padStart":
            return f"{obj}.rjust({args[0]}, {args[1]})" if len(args) >= 2 else (f"{obj}.rjust({a0})" if a0 else obj)
        return None

    def _method_object(self, obj: str, method: str, args: list[str]) -> str | None:
        a0 = args[0] if args else obj
        if obj in ("Object", "dict"):
            if method == "keys":
                return f"list({a0}.keys())"
            if method == "values":
                return f"list({a0}.values())"
            if method == "entries":
                return f"list({a0}.items())"
            if method == "assign":
                return f"{{**{args[0]}, **{args[1]}}}" if len(args) >= 2 else (a0 if args else "{}")
            if method == "fromEntries":
                return f"dict({a0})" if args else "{}"
        if method == "hasOwnProperty":
            return f"({a0} in {obj})" if args else "False"
        if obj in ("Array", "list") and method == "from":
            return f"list({a0})" if args else "[]"
        if obj in ("math", "Math"):
            return self._method_math(method, args)
        if obj in ("json", "JSON"):
            if method == "parse":
                return f"json.loads({', '.join(args)})"
            if method == "stringify":
                return f"json.dumps({', '.join(args)})"
        return None

    def _method_math(self, method: str, args: list[str]) -> str | None:
        a = ", ".join(args)
        if method in ("floor", "ceil", "sqrt", "log"):
            return f"math.{method}({a})"
        if method in ("min", "max"):
            return f"{method}({a})"
        if method == "abs":
            return f"abs({a})"
        if method == "round":
            return f"round({a})"
        if method == "pow":
            return f"({args[0]} ** {args[1]})" if len(args) == 2 else f"math.pow({a})"
        return None

    def _method_special(self, obj: str, method: str, args: list[str]) -> str | None:
        if obj in ("_console", "console"):
            return f"# console.{method}({', '.join(args)})"
        if obj in ("_logger", "Logger"):
            return f"# Logger.{method}({', '.join(args)})"
        if obj in ("Number", "number"):
            return self._method_number(method, args)
        return None

    def _method_number(self, method: str, args: list[str]) -> str | None:
        a0 = args[0] if args else ""
        if method == "isFinite":
            return f"math.isfinite({', '.join(args)})"
        if method == "isInteger":
            return f"isinstance({a0}, int)" if a0 else "False"
        if method in ("parseInt", "parseFloat"):
            fn = "int" if method == "parseInt" else "float"
            return f"{fn}({', '.join(args)})"
        if method == "EPSILON":
            return "EPSILON"
        return None

    # ------------------------------------------------------------------
    # Top-level function calls
    # ------------------------------------------------------------------

    def _translate_function_call(self, func_name: str, args: list[str], raw_name: str = "") -> str:
        base = raw_name.split(".")[-1] if raw_name else func_name
        r = self._fn_date(base, args)
        if r is not None:
            return r
        r = self._fn_general(base, func_name, args)
        if r is not None:
            return r
        return f"{self._to_snake_case(func_name)}({', '.join(args)})"

    def _fn_date(self, base: str, args: list[str]) -> str | None:
        a = ", ".join(args)
        a0 = args[0] if args else "datetime.now()"
        if base == "format":
            return f"_format_date({args[0]}, {args[1]})" if len(args) >= 2 else f"_format_date({a})"
        if base == "differenceInDays":
            return f"_difference_in_days({args[0]}, {args[1]})" if len(args) == 2 else f"_difference_in_days({a})"
        if base == "isBefore":
            return f"_is_before({args[0]}, {args[1]})" if len(args) == 2 else f"_is_before({a})"
        if base == "isAfter":
            return f"_is_after({args[0]}, {args[1]})" if len(args) == 2 else f"_is_after({a})"
        if base == "addMilliseconds":
            return f"_add_milliseconds({args[0]}, {args[1]})" if len(args) == 2 else f"_add_milliseconds({a})"
        if base == "eachDayOfInterval":
            return f"_each_day_of_interval({a})"
        if base == "eachYearOfInterval":
            return f"_each_year_of_interval({a})"
        if base == "endOfDay":
            return f"_end_of_day({a0})"
        if base == "startOfDay":
            return f"_start_of_day({a0})"
        if base == "endOfYear":
            return f"_end_of_year({a0})"
        if base == "startOfYear":
            return f"_start_of_year({a0})"
        if base == "startOfMonth":
            return f"_start_of_month({a0})"
        return self._fn_date_b(base, args)

    def _fn_date_b(self, base: str, args: list[str]) -> str | None:
        a = ", ".join(args)
        a0 = args[0] if args else "datetime.now()"
        if base == "startOfWeek":
            return f"_start_of_week({a})"
        if base == "subDays":
            return f"_sub_days({args[0]}, {args[1]})" if len(args) >= 2 else f"_sub_days({a})"
        if base == "subYears":
            return f"_sub_years({args[0]}, {args[1]})" if len(args) >= 2 else f"_sub_years({a})"
        if base == "isThisYear":
            return f"_is_this_year({a0})"
        if base == "isWithinInterval":
            return f"_is_within_interval({a})"
        if base in ("min", "max") and len(args) == 1 and args[0].startswith("["):
            return f"{base}({args[0]})"
        return None

    def _fn_general(self, base: str, func_name: str, args: list[str]) -> str | None:
        a = ", ".join(args)
        a0 = args[0] if args else "None"
        if base == "cloneDeep":
            return f"deepcopy({a0})"
        if base == "sortBy":
            return f"sorted({args[0]}, key={args[1]})" if len(args) >= 2 else f"sorted({a0})"
        if base == "isNumber":
            return f"isinstance({a0}, (int, float, Decimal))"
        if base == "isFinite":
            return f"math.isfinite(float({a0}))"
        if base == "sum":
            return f"sum({a0})"
        if base == "uniqBy":
            return f"_uniq_by({args[0]}, {args[1]})" if len(args) >= 2 else f"list(set({a0}))"
        if base == "getFactor":
            return f"_get_factor({a0})"
        if base == "getIntervalFromDateRange":
            return f"_get_interval_from_date_range({a})"
        if base == "getSum":
            return f"sum({a0})"
        if base == "parseDate":
            return f"_parse_date({a0})"
        if base == "resetHours":
            return f"_reset_hours({a0})"
        if base == "plainToClass":
            return args[1] if len(args) >= 2 else a0
        return None

    # ------------------------------------------------------------------
    # Member access: obj.prop
    # ------------------------------------------------------------------

    def _translate_member(self, node: Node) -> str:
        obj_node = node.child_by_field_name("object")
        prop_node = node.child_by_field_name("property")
        if obj_node is None or prop_node is None:
            return self.text(node)
        obj = self._expr(obj_node)
        prop = self.text(prop_node)
        is_opt = "?." in self.text(node)
        py_prop = self._to_snake_case(prop)

        if prop == "length":
            return f"len({obj})"
        if obj in ("Number", "number") and prop == "EPSILON":
            return "EPSILON"
        if obj in ("math", "Math"):
            return f"math.{prop.lower()}" if prop in ("PI",) else f"math.{prop}"

        # Dict-style access for explicitly listed properties or camelCase on non-self objects
        dict_props = set(self.import_map.get("dict_props", []))
        is_camel = prop[0].islower() and any(c.isupper() for c in prop)
        use_dict = prop in dict_props or (is_camel and obj not in ("self",))
        if use_dict:
            if is_opt:
                return f"({obj}.get({prop!r}) if isinstance({obj}, dict) else getattr({obj}, {py_prop!r}, None))"
            return f"({obj}.get({prop!r}) if isinstance({obj}, dict) else {obj}.{py_prop})"

        if is_opt:
            return f"(getattr({obj}, {py_prop!r}, None) if {obj} is not None else None)"
        return f"{obj}.{py_prop}"

    # ------------------------------------------------------------------
    # Binary / unary / assignment operators
    # ------------------------------------------------------------------

    def _translate_subscript(self, node: Node) -> str:
        obj = node.child_by_field_name("object")
        idx = node.child_by_field_name("index")
        obj_s = self._expr(obj)
        idx_s = self._expr(idx) if idx else ""
        if "?." in self.text(node):
            return f"({obj_s}[{idx_s}] if {obj_s} is not None else None)"
        return f"{obj_s}[{idx_s}]"

    def _translate_binary(self, node: Node) -> str:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        op = ""
        for child in node.children:
            if not child.is_named:
                t = self.text(child).strip()
                if t in ("===", "!==", "==", "!=", "&&", "||", "??",
                         "+", "-", "*", "/", "%", "<", ">", "<=", ">=",
                         "<<", ">>", ">>>", "&", "|", "^", "in", "instanceof"):
                    op = t
                    break
        l, r = self._expr(left), self._expr(right)
        if op == "===":
            return f"({l} == {r})"
        if op == "!==":
            return f"({l} != {r})"
        if op == "&&":
            return f"({l} and {r})"
        if op == "||":
            return f"({l} or {r})"
        if op == "??":
            return f"({l} if {l} is not None else {r})"
        if op == "instanceof":
            return f"isinstance({l}, {r})"
        if op == "in":
            return f"({l} in {r})"
        return f"({l} {op} {r})"

    def _translate_unary(self, node: Node) -> str:
        op, operand = "", None
        for child in node.children:
            if child.is_named:
                operand = child
            else:
                t = self.text(child).strip()
                if t in ("!", "-", "+", "~", "typeof", "void", "delete"):
                    op = t
        s = self._expr(operand) if operand else "None"
        return {"!": f"(not {s})", "typeof": f"type({s}).__name__",
                "void": "None", "delete": f"del {s}",
                "-": f"(-{s})", "+": f"(+{s})", "~": f"(~{s})"}.get(op, s)

    def _translate_update(self, node: Node) -> str:
        raw = self.text(node).strip()
        if "++" in raw:
            return f"{self._to_snake_case(raw.replace('++', '').strip())} += 1"
        if "--" in raw:
            return f"{self._to_snake_case(raw.replace('--', '').strip())} -= 1"
        return self._to_snake_case(raw)

    def _lvalue(self, node: Node) -> str:
        """Translate a node as an assignment target (always simple attribute access)."""
        if node is None:
            return "_"
        if node.type == "member_expression":
            obj_node = node.child_by_field_name("object")
            prop_node = node.child_by_field_name("property")
            if obj_node and prop_node:
                return f"{self._expr(obj_node)}.{self._to_snake_case(self.text(prop_node))}"
        return self._expr(node)

    def _translate_assignment(self, node: Node) -> str:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        return f"{self._lvalue(left)} = {self._expr(right)}"

    def _translate_augmented_assign(self, node: Node) -> str:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        op = node.child_by_field_name("operator")
        op_text = self.text(op) if op else "+="
        return f"{self._lvalue(left)} {op_text} {self._expr(right)}"

    def _translate_ternary(self, node: Node) -> str:
        cond = node.child_by_field_name("condition")
        cons = node.child_by_field_name("consequence")
        alt = node.child_by_field_name("alternative")
        return f"({self._expr(cons)} if {self._expr(cond)} else {self._expr(alt)})"

    def _translate_type_assertion(self, node: Node) -> str:
        for child in node.named_children:
            if child.type not in ("type_identifier", "generic_type", "predefined_type"):
                return self._expr(child)
        return self.text(node)

    def _translate_pair(self, node: Node, t: str) -> str:
        if t == "pair":
            key = node.child_by_field_name("key")
            value = node.child_by_field_name("value")
            k = self.text(key) if key else "_"
            return f"{k!r}: {self._expr(value)}"
        # shorthand_property_identifier
        name = self.text(node)
        return f"{name!r}: {self._to_snake_case(name)}"

    # ------------------------------------------------------------------
    # Object literal
    # ------------------------------------------------------------------

    def _translate_object(self, node: Node) -> str:
        pairs = []
        for child in node.named_children:
            if child.type == "pair":
                key = child.child_by_field_name("key")
                value = child.child_by_field_name("value")
                if key:
                    if key.type == "computed_property_name":
                        inner = key.named_children[0] if key.named_children else None
                        k_str = self._expr(inner) if inner else "'unknown'"
                    else:
                        k_str = repr(self.text(key))
                    pairs.append(f"{k_str}: {self._expr(value) if value else 'None'}")
            elif child.type == "shorthand_property_identifier":
                name = self.text(child)
                pairs.append(f"{name!r}: {self._to_snake_case(name)}")
            elif child.type == "spread_element":
                inner = child.named_children[0] if child.named_children else None
                if inner:
                    pairs.append(f"**{self._expr(inner)}")
        return "{" + ", ".join(pairs) + "}"

    # ------------------------------------------------------------------
    # Arrow functions / lambdas
    # ------------------------------------------------------------------

    def _translate_arrow(self, node: Node) -> str:
        params_node = node.child_by_field_name("parameters")
        body = node.child_by_field_name("body")
        if params_node:
            params = self._extract_params(params_node)
        else:
            params = [self._to_snake_case(self.text(c))
                      for c in node.named_children if c.type == "identifier"]
        p = ", ".join(params)
        if not body:
            return f"lambda {p}: None"
        if body.type == "statement_block":
            ret = self._extract_return_expr(body)
            if ret is not None:
                return f"lambda {p}: {ret}"
            return f"lambda {p}: None"
        return f"lambda {p}: {self._expr(body)}"

    def _extract_return_expr(self, block: Node) -> str | None:
        stmts = [c for c in block.named_children if c.type != "comment"]
        if len(stmts) == 1 and stmts[0].type == "return_statement":
            if stmts[0].named_children:
                return self._expr(stmts[0].named_children[0])
        return None

    # ------------------------------------------------------------------
    # Template strings, regex, fallback
    # ------------------------------------------------------------------

    def _translate_template_string(self, node: Node) -> str:
        parts = []
        for child in node.children:
            text = self.text(child)
            if child.type in ("string_fragment", "template_string_fragment"):
                parts.append(text)
            elif child.type == "template_substitution":
                inner = child.named_children[0] if child.named_children else None
                parts.append(f"{{{self._expr(inner)}}}" if inner else "{}")
            elif text != "`":
                parts.append(text)
        return f'f"{"".join(parts)}"'

    def _translate_regex(self, node: Node) -> str:
        raw = self.text(node)
        m = re.match(r"/(.+)/([gimsuy]*)", raw)
        return f're.compile(r"{m.group(1)}")' if m else raw

    def _translate_raw_fallback(self, node: Node) -> str:
        raw = self.text(node)
        for old, new in (
            ("this.", "self."), ("===", "=="), ("!==", "!="),
            ("&&", " and "), ("||", " or "),
            ("null", "None"), ("undefined", "None"),
            ("true", "True"), ("false", "False"),
        ):
            raw = raw.replace(old, new)
        return raw

    # ------------------------------------------------------------------
    # Args helper
    # ------------------------------------------------------------------

    def _emit_args(self, args_node: Node | None) -> list[str]:
        if not args_node:
            return []
        return [self._expr(child) for child in args_node.named_children
                if child.type != "comment"]
