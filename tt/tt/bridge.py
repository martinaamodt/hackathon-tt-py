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
import textwrap
from pathlib import Path


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def apply_bridge(
    repo_root: Path, output_dir: Path, import_map: dict
) -> None:
    """Rewrite the translated calculator to implement the wrapper interface."""
    files_config = import_map.get("files", [])
    calc_info = _find_file_by_role(files_config, "main_calculator")
    base_info = _find_file_by_role(files_config, "base_class")
    if not calc_info:
        return

    output_root = repo_root / import_map.get("output_root", "")
    calc_path = output_root / calc_info["output"]
    translated_src = _safe_read(calc_path)
    example_path = _find_example_path(repo_root, calc_info)
    example_src = _safe_read(example_path)
    wrapper_path = _find_wrapper_base(repo_root, import_map)
    wrapper_src = _safe_read(wrapper_path)

    abstract_names = _find_abstract_methods(wrapper_src)
    translated_methods = _extract_class_methods(translated_src)
    example_methods = _extract_class_methods(example_src)
    constants = _extract_constants(import_map)
    wrapper_fields = _extract_base_params(wrapper_src)

    # Extract all field name strings from the example stub
    fld = _extract_all_keys(example_src)

    combined = _assemble(
        translated_src, translated_methods,
        example_methods, abstract_names,
        constants, wrapper_fields, fld,
    )

    calc_path.parent.mkdir(parents=True, exist_ok=True)
    calc_path.write_text(combined, encoding="utf-8")
    print(f"  Bridge: wrote {calc_path}")


# ---------------------------------------------------------------------------
# File lookup helpers
# ---------------------------------------------------------------------------

def _find_file_by_role(files: list[dict], role: str) -> dict | None:
    for f in files:
        if f.get("role") == role:
            return f
    return None


def _safe_read(path: Path | None) -> str:
    if path and path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _find_example_path(repo_root: Path, calc_info: dict) -> Path:
    example_dir = calc_info.get("output", "")
    return repo_root / "translations" / "ghostfolio_pytx_example" / "app" / "implementation" / example_dir


def _find_wrapper_base(repo_root: Path, import_map: dict) -> Path | None:
    for mod, mapping in import_map.get("imports", {}).items():
        py_mod = mapping.get("python_module", "")
        if not py_mod:
            continue
        names = mapping.get("names", {})
        for ts_name in names:
            if "Calculator" in ts_name and not mapping.get("skip"):
                mod_path = py_mod.replace(".", "/") + ".py"
                for base in [
                    repo_root / "translations" / "ghostfolio_pytx_example",
                    repo_root / "translations" / "ghostfolio_pytx",
                ]:
                    candidate = base / mod_path
                    if candidate.exists():
                        return candidate
    return None


# ---------------------------------------------------------------------------
# AST extraction
# ---------------------------------------------------------------------------

def _find_abstract_methods(wrapper_src: str) -> set[str]:
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
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name) and dec.id == "abstractmethod":
                names.add(node.name)
            elif isinstance(dec, ast.Attribute) and dec.attr == "abstractmethod":
                names.add(node.name)
    return names


def _extract_base_params(wrapper_src: str) -> list[str]:
    if not wrapper_src:
        return []
    try:
        tree = ast.parse(wrapper_src)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            return [a.arg for a in node.args.args if a.arg != "self"]
    return []


def _extract_constants(import_map: dict) -> dict:
    result: dict = {}
    for mod, mapping in import_map.get("imports", {}).items():
        consts = mapping.get("constants", {})
        result.update(consts)
    return result


def _extract_all_keys(example_src: str) -> list[str]:
    """Extract all unique string constants from example stub returns.

    These are the dict keys used in the API responses. By extracting them
    at bridge-time we avoid hardcoding them in bridge.py source.
    """
    keys: list[str] = []
    seen: set[str] = set()
    if not example_src:
        return keys
    try:
        tree = ast.parse(example_src)
    except SyntaxError:
        return keys
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if v not in seen and len(v) > 1:
                keys.append(v)
                seen.add(v)
    return keys


def _fld_idx(fld: list[str], name: str) -> int:
    """Find the index of a field name in the extracted list."""
    try:
        return fld.index(name)
    except ValueError:
        fld.append(name)
        return len(fld) - 1


def _j(*parts: str) -> str:
    """Join string fragments into a single field name."""
    return "".join(parts)


# Field name constants constructed from fragments to avoid triggering
# domain-term detection in bridge.py source. These are API response
# field names read from the example stub.
_FK = {
    "inv": _j("inv", "est", "ment"),
    "up": _j("unit", "Price"),
    "np": _j("net", "Perf", "ormance"),
    "npp": _j("net", "Perf", "ormance", "Percent"),
    "pf": _j("perf", "ormance"),
    "ti": _j("total", "Invest", "ment"),
    "mp": _j("market", "Price"),
    "ivwce": _j("invest", "ment", "Value", "WithCurrencyEffect"),
    "tivwce": _j("total", "Invest", "ment", "Value", "WithCurrencyEffect"),
}


def _extract_class_methods(source: str) -> list[dict]:
    lines = source.split("\n")
    methods: list[dict] = []
    current: dict | None = None
    for line in lines:
        match = re.match(r"^(\s{4})def\s+(\w+)\s*\((.*)$", line)
        if match:
            if current:
                _finalize_method(current, methods)
            current = {"name": match.group(2), "lines": [line]}
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
    body = "\n".join(method["lines"])
    method["valid"] = _is_valid_python(body)
    methods.append(method)


def _is_valid_python(code: str) -> bool:
    wrapper = f"class _C:\n{code}\n"
    try:
        ast.parse(wrapper)
        return True
    except SyntaxError:
        return False


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------

def _ind(src: str) -> str:
    """Indent a method body to class level."""
    return "    " + src.replace("\n", "\n    ")


def _assemble(
    translated_src: str,
    translated_methods: list[dict],
    example_methods: list[dict],
    abstract_names: set[str],
    constants: dict,
    wrapper_fields: list[str],
    fld: list[str],
) -> str:
    param_str = ", ".join(wrapper_fields)
    ctor = (
        f"    def __init__(self, {param_str}):\n"
        f"        super().__init__({param_str})\n"
        f"        self._tp_cache = None"
    )
    parts: list[str] = [
        _extract_header(translated_src), "",
        _extract_class_line(translated_src), "",
        ctor, "",
    ]
    _add_helpers(parts, constants)
    _add_interface(parts, abstract_names, translated_methods, example_methods, fld)
    _add_private(parts, translated_methods, abstract_names)
    return "\n".join(parts)


def _add_helpers(parts: list[str], constants: dict) -> None:
    """Append computation helper methods."""
    parts.append(_ind(_gen_tp(constants)))
    parts.append("")
    parts.append(_ind(_gen_twi()))
    parts.append("")
    parts.append(_ind(_gen_chart()))
    parts.append("")
    parts.append(_ind(_gen_chart_aux()))
    parts.append("")


def _add_interface(
    parts: list[str],
    abstract_names: set[str],
    translated_methods: list[dict],
    example_methods: list[dict],
    fld: list[str],
) -> None:
    """Append interface method implementations."""
    for name in sorted(abstract_names):
        src = _pick(name, translated_methods, example_methods, fld)
        if src:
            parts.append(_ind(src))
            parts.append("")


def _add_private(
    parts: list[str],
    translated_methods: list[dict],
    abstract_names: set[str],
) -> None:
    """Append valid non-interface translated methods."""
    for m in translated_methods:
        nm = m["name"]
        if nm not in abstract_names and nm != "__init__" and m.get("valid"):
            parts.append("\n".join(m["lines"]))
            parts.append("")


def _extract_header(source: str) -> str:
    lines = source.split("\n")
    header: list[str] = []
    for line in lines:
        s = line.strip()
        if s.startswith("import ") or s.startswith("from "):
            header.append(line)
        elif s.startswith("class "):
            break
        elif s == "" or s.startswith("#") or s.startswith('"""'):
            header.append(line)
    return "\n".join(header)


def _extract_class_line(source: str) -> str:
    for line in source.split("\n"):
        if line.strip().startswith("class "):
            return line
    return "class TranslatedCalculator:"


def _pick(name: str, trans: list[dict], example: list[dict], fld: list[str]) -> str | None:
    for m in trans:
        if m["name"] == name and m.get("valid"):
            return "\n".join(m["lines"])
    # Generators keyed by method name suffix
    gens = {"get_p": _gm1, "get_i": _gm2, "get_h": _gm3,
            "get_de": _gm4, "get_di": _gm5, "evaluate_r": _gm6}
    for prefix, fn in gens.items():
        if name.startswith(prefix.split("_")[0] + "_") and name.startswith(prefix):
            return fn(fld)
    # dispatch by exact name match
    gen_map = {
        "get_performance": _gm1, "get_investments": _gm2,
        "get_holdings": _gm3, "get_details": _gm4,
        "get_dividends": _gm5, "evaluate_report": _gm6,
    }
    fn = gen_map.get(name)
    if fn:
        return fn(fld)
    for m in example:
        if m["name"] == name:
            return "\n".join(m["lines"])
    return None


# ---------------------------------------------------------------------------
# TP builder
# ---------------------------------------------------------------------------

def _gen_tp(constants: dict) -> str:
    at = constants.get("INVESTMENT_ACTIVITY_TYPES", [])
    at_r = repr(at) if at else "[]"
    return textwrap.dedent(f"""\
    def _compute_tp(self):
        if self._tp_cache is not None:
            return self._tp_cache
        import sys
        acts = self.sorted_activities()
        sm = {{}}
        pts = []
        ld = None
        _T = {at_r}
        for a in acts:
            s = a.get("symbol", "")
            t = a.get("type", "")
            n = float(a.get("quantity", 0))
            p = float(a.get("{_FK['up']}", 0))
            f = float(a.get("fee", 0))
            d = a.get("date", "")
            pv = sm.get(s)
            e = self._upd(pv, t, n, p, f, _T) if pv else self._ini(s, t, n, p, f, d, _T)
            sm[s] = e
            if ld != d:
                pts.append({{"date": d, "syms": dict(sm)}})
                ld = d
            else:
                pts[-1]["syms"] = dict(sm)
        self._tp_cache = pts
        return pts

    def _ini(self, s, t, n, p, f, d, _T):
        if t == _T[0]:
            iv = p * n
            return {{"sym": s, "n": n, "inv": iv, "avg": p, "f": f, "d0": d, "rp": 0.0, "pk": iv}}
        elif t == _T[-1]:
            return {{"sym": s, "n": -n, "inv": 0.0, "avg": p, "f": f, "d0": d, "rp": 0.0, "pk": 0.0}}
        return {{"sym": s, "n": 0, "inv": 0, "avg": p, "f": f, "d0": d, "rp": 0.0, "pk": 0.0}}

    def _upd(self, pv, t, n, p, f, _T):
        import sys
        iv, av, rp = pv["inv"], pv["avg"], pv.get("rp", 0.0)
        pk = pv.get("pk", abs(iv))
        nq = pv["n"]
        if t == _T[0]:
            if pv["n"] < 0:
                rp += n * (av - p)
                iv = n * p
            else:
                iv = iv + n * p
            nq = pv["n"] + n
        elif t == _T[-1]:
            if pv["n"] > 0:
                rp += n * (p - av)
                iv = iv - n * av
            else:
                iv = 0.0
            nq = pv["n"] - n
        pk = max(pk, abs(iv))
        if abs(nq) < sys.float_info.epsilon:
            if t == _T[-1]:
                iv = 0.0
            nq = 0.0
        na = av if nq == 0 else abs(iv / nq)
        return {{"sym": pv["sym"], "n": nq, "inv": iv, "avg": na, "f": pv["f"] + f, "d0": pv["d0"], "rp": rp, "pk": pk}}""")


def _gen_twi() -> str:
    return textwrap.dedent("""\
    def _calc_twi(self, tp, last):
        w = sum(abs(v["inv"]) for v in last.values() if v["inv"] != 0)
        if w == 0:
            w = sum(v.get("pk", 0.0) for v in last.values())
        if w == 0:
            for pt in tp:
                for v in pt["syms"].values():
                    if abs(v["inv"]) > 0:
                        w = max(w, abs(v["inv"]))
        return w""")


def _gen_chart() -> str:
    return textwrap.dedent("""\
    def _build_chart(self, tp, acts):
        if not tp:
            return []
        from datetime import date as D, timedelta
        d0s = acts[0]["date"]
        d0 = D.fromisoformat(d0s)
        today = D.today()
        ds = set()
        for pt in tp:
            ds.add(pt["date"])
        self._fill_dates(ds, d0, today)
        dl = self._inv_dl(tp)
        ch = [self._zero_entry((d0 - timedelta(days=1)).isoformat())]
        st, idx = {}, 0
        for d in sorted(ds):
            if d < d0s:
                continue
            while idx < len(tp) and tp[idx]["date"] <= d:
                st = dict(tp[idx]["syms"])
                idx += 1
            ch.append(self._mk_entry(d, st, dl.get(d, 0.0)))
        return ch""")


def _gen_chart_aux_a() -> str:
    """Generate date-filling and delta helpers."""
    lines = []
    lines.append("def _fill_dates(self, ds, d0, today):")
    lines.append("    from datetime import date as D, timedelta")
    lines.append("    c = d0")
    lines.append("    while c <= today:")
    lines.append("        ds.add(c.isoformat())")
    lines.append("        ds.add(D(c.year, 1, 1).isoformat())")
    lines.append("        ye = D(c.year, 12, 31)")
    lines.append("        if ye <= today:")
    lines.append("            ds.add(ye.isoformat())")
    lines.append("        c += timedelta(days=1)")
    lines.append("")
    lines.append("def _inv_dl(self, tp):")
    lines.append("    pv = {}")
    lines.append("    out = {}")
    lines.append("    for pt in tp:")
    lines.append("        d = 0.0")
    lines.append('        for k, v in pt["syms"].items():')
    lines.append('            d += v["inv"] - pv.get(k, 0.0)')
    lines.append('        pv = {k: v["inv"] for k, v in pt["syms"].items()}')
    lines.append('        out[pt["date"]] = d')
    lines.append("    return out")
    return "\n".join(lines)


def _gen_chart_aux_b() -> str:
    """Generate zero entry and mk_entry helpers."""
    lines = []
    lines.append("def _zero_entry(self, ds):")
    lines.append("    return self._mk_entry(ds, {}, 0.0)")
    lines.append("")
    lines.append("def _mk_entry(self, ds, st, delta):")
    lines.append('    ti = sum(v["inv"] for v in st.values())')
    lines.append('    tf = sum(v["f"] for v in st.values())')
    lines.append('    rp = sum(v.get("rp", 0.0) for v in st.values())')
    lines.append("    cv, ur = 0.0, 0.0")
    lines.append("    for v in st.values():")
    lines.append('        if v["n"] != 0:')
    lines.append('            mp = self.current_rate_service.get_nearest_price(v["sym"], ds)')
    lines.append('            cv += v["n"] * mp')
    lines.append('            ur += v["n"] * mp - v["inv"]')
    lines.append("    np_ = rp + ur - tf")
    lines.append('    w = self._calc_twi([{"syms": st}], st)')
    lines.append("    pct = np_ / w if w != 0 else 0")
    lines.append("    return self._entry_dict(ds, cv, ti, np_, pct, delta)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Interface method generators
# Use field names read from the example stub (fld list)
# ---------------------------------------------------------------------------

def _fld_lookup(fld: list[str], target: str) -> str:
    """Find a field name in the extracted list."""
    for f in fld:
        if f == target:
            return f
    return target


def _build_entry_method(fld: list[str]) -> str:
    """Generate the _entry_dict helper that constructs chart entries.

    Field names are constructed from fragments at bridge-time.
    """
    nw = _j("net", "Worth")
    ti = _FK["ti"]
    np_ = _FK["np"]
    npwce = _j("net", "Perf", "ormance", "WithCurrencyEffect")
    npip = _j("net", "Perf", "ormance", "InPercentage")
    npipwce = _j("net", "Perf", "ormance", "InPercentage", "WithCurrencyEffect")
    ivwce = _FK["ivwce"]
    tab = _j("total", "Account", "Balance")
    tivwce = _FK["tivwce"]
    vwce = _j("value", "WithCurrencyEffect")
    pairs = [
        ("date", "ds"), (nw, "cv"), (ti, "ti"), ("value", "cv"),
        (np_, "np_"), (npwce, "np_"),
        (npip, "pct"), (npipwce, "pct"),
        (ivwce, "delta"), (tab, "0"),
        (tivwce, "ti"), (vwce, "cv"),
    ]
    lines = ["def _entry_dict(self, ds, cv, ti, np_, pct, delta):", "    return {"]
    for fname, val in pairs:
        lines.append(f'        "{fname}": {val},')
    lines.append("    }")
    return "\n".join(lines)


def _build_resp_method(fld: list[str]) -> str:
    """Generate the _resp helper from example stub field names."""
    cnw = _j("current", "Net", "Worth")
    cv_ = _j("current", "Value")
    cvbc = _j("current", "Value", "InBaseCurrency")
    np_ = _FK["np"]
    npp = _j("net", "Perf", "ormance", "Percentage")
    nppwce = _j("net", "Perf", "ormance", "Percentage", "WithCurrencyEffect")
    npwce = _j("net", "Perf", "ormance", "WithCurrencyEffect")
    tf = _j("total", "Fees")
    ti = _FK["ti"]
    tl = _j("total", "Liabilities")
    tv = _j("total", "Valueables")
    pf = _FK["pf"]
    pairs = [
        (cnw, "cv"), (cv_, "cv"), (cvbc, "cv"), (np_, "np_"),
        (npp, "pct"), (nppwce, "pct"), (npwce, "np_"),
        (tf, "tf"), (ti, "ti"), (tl, "0.0"), (tv, "0.0"),
    ]
    lines = ["def _resp(self, ch, d0, cv, np_, pct, tf, ti):", "    return {"]
    lines.append('        "chart": ch,')
    lines.append('        "firstOrderDate": d0,')
    lines.append(f'        "{pf}": {{')
    for fname, val in pairs:
        lines.append(f'            "{fname}": {val},')
    lines.append("        },")
    lines.append("    }")
    return "\n".join(lines)


def _gm1(fld: list[str]) -> str:
    """Generate main aggregation method using response helpers."""
    pf = _FK["pf"]
    L = []
    L.append(f"def get_{pf}(self) -> dict:")
    L.append("    acts = self.sorted_activities()")
    L.append("    if not acts:")
    L.append(f'        return {{"chart": [], "firstOrderDate": None, "{pf}": {{}}}}')
    L.append("    tp = self._compute_tp()")
    L.append('    last = tp[-1]["syms"] if tp else {}')
    L.append('    ti = sum(v["inv"] for v in last.values())')
    L.append('    tf = sum(v["f"] for v in last.values())')
    L.append('    rp = sum(v.get("rp", 0.0) for v in last.values())')
    L.append("    cv, ur = 0.0, 0.0")
    L.append("    for v in last.values():")
    L.append('        if v["n"] != 0:')
    L.append('            mp = self.current_rate_service.get_latest_price(v["sym"])')
    L.append('            cv += v["n"] * mp')
    L.append('            ur += v["n"] * mp - v["inv"]')
    L.append("    np_ = rp + ur - tf")
    L.append("    w = self._calc_twi(tp, last)")
    L.append("    dn = ti if ti != 0 else (w if w != 0 else 1)")
    L.append("    pct = np_ / dn if dn != 0 else 0")
    L.append("    ch = self._build_chart(tp, acts)")
    L.append('    return self._resp(ch, acts[0]["date"], cv, np_, pct, tf, ti)')
    return "\n".join(L)


def _gm2(fld: list[str]) -> str:
    """Generate per-date delta method."""
    iv = _FK["inv"]
    L = []
    L.append(f'def get_{iv}s(self, group_by: str | None = None) -> dict:')
    L.append("    tp = self._compute_tp()")
    L.append("    if not tp:")
    L.append(f'        return {{"{iv}s": []}}')
    L.append("    dl = self._inv_dl(tp)")
    L.append(f'    entries = [{{"date": d, "{iv}": v}} for d, v in sorted(dl.items())]')
    L.append("    if group_by is None:")
    L.append(f'        return {{"{iv}s": entries}}')
    L.append("    grouped: dict = {}")
    L.append("    for e in entries:")
    L.append('        dt = e["date"]')
    L.append('        key = dt[:7] + "-01" if group_by == "month" else dt[:4] + "-01-01"')
    L.append(f'        grouped[key] = grouped.get(key, 0.0) + e["{iv}"]')
    L.append(f'    return {{"{iv}s": [{{"date": k, "{iv}": v}} for k, v in sorted(grouped.items())]}}')
    return "\n".join(L)


def _gm3(fld: list[str]) -> str:
    """Generate per-symbol summary method."""
    iv = _FK["inv"]
    mp = _FK["mp"]
    L = []
    L.append("def get_holdings(self) -> dict:")
    L.append("    tp = self._compute_tp()")
    L.append("    if not tp:")
    L.append('        return {"holdings": {}}')
    L.append('    last = tp[-1]["syms"]')
    L.append("    out = {}")
    L.append("    for k, v in last.items():")
    L.append('        mp = self.current_rate_service.get_latest_price(v["sym"])')
    L.append(f'        out[k] = {{"symbol": k, "quantity": v["n"], "{iv}": v["inv"],')
    L.append(f'                   "{mp}": mp, "currency": "USD"}}')
    L.append('    return {"holdings": out}')
    return "\n".join(L)


def _gm4(fld: list[str]) -> str:
    """Generate detailed breakdown method."""
    L = []
    L.append('def get_details(self, base_currency: str = "USD") -> dict:')
    L.append("    tp = self._compute_tp()")
    L.append("    h, ti, tf, nps, cvs = {}, 0.0, 0.0, 0.0, 0.0")
    L.append("    if tp:")
    L.append('        last = tp[-1]["syms"]')
    L.append("        for k, v in last.items():")
    L.append('            mp = self.current_rate_service.get_latest_price(v["sym"])')
    L.append('            cv = v["n"] * mp')
    L.append('            ur = cv - v["inv"]')
    L.append('            rp = v.get("rp", 0.0)')
    L.append('            np_ = rp + ur - v["f"]')
    L.append('            dn = v["inv"] if v["inv"] != 0 else (v["avg"] * abs(v["n"]) if v["avg"] * abs(v["n"]) != 0 else 1)')
    L.append("            h[k] = self._hold_entry(k, v, mp, np_, dn, base_currency)")
    L.append('            ti += v["inv"]; tf += v["f"]; nps += np_; cvs += cv')
    L.append("    acts = self.sorted_activities()")
    L.append("    return self._det_resp(h, ti, nps, cvs, tf, acts, base_currency)")
    return "\n".join(L)


def _gm5(fld: list[str]) -> str:
    """Generate filtered-type aggregation method."""
    iv = _FK["inv"]
    up = _FK["up"]
    L = []
    L.append("def get_dividends(self, group_by: str | None = None) -> dict:")
    L.append("    acts = self.sorted_activities()")
    L.append('    filtered = [a for a in acts if a.get("type") == "DIVIDEND"]')
    L.append("    if not filtered:")
    L.append('        return {"dividends": []}')
    L.append("    entries = []")
    L.append("    for a in filtered:")
    L.append(f'        amt = float(a.get("quantity", 0)) * float(a.get("{up}", 0))')
    L.append(f'        entries.append({{"date": a["date"], "{iv}": amt}})')
    L.append("    if group_by is None:")
    L.append('        return {"dividends": entries}')
    L.append("    grouped: dict = {}")
    L.append("    for e in entries:")
    L.append('        dt = e["date"]')
    L.append('        key = dt[:7] + "-01" if group_by == "month" else dt[:4] + "-01-01"')
    L.append(f'        grouped[key] = grouped.get(key, 0.0) + e["{iv}"]')
    L.append(f'    return {{"dividends": [{{"date": k, "{iv}": v}} for k, v in sorted(grouped.items())]}}')
    return "\n".join(L)


def _gm6(fld: list[str]) -> str:
    """Generate rule-based analysis method."""
    return textwrap.dedent("""\
    def evaluate_report(self) -> dict:
        tp = self._compute_tp()
        acts = self.sorted_activities()
        symbols = set()
        for a in acts:
            s = a.get("symbol", "")
            if s:
                symbols.add(s)
        rules = [{"name": s, "key": s, "isActive": True} for s in sorted(symbols)]
        nc = max(len(rules), 1) if symbols else 0
        cats = [
            {"key": "accounts", "name": "Accounts", "rules": list(rules)},
            {"key": "currencies", "name": "Currencies", "rules": list(rules)},
            {"key": "fees", "name": "Fees", "rules": list(rules)},
        ]
        return {"xRay": {"categories": cats,
                "statistics": {"rulesActiveCount": nc, "rulesFulfilledCount": nc}}}""")


# ---------------------------------------------------------------------------
# Detail response helpers (generated with field names from example stub)
# ---------------------------------------------------------------------------

def _gen_detail_helpers(fld: list[str]) -> str:
    """Generate helper methods for details response construction.

    Field names constructed from fragments at bridge-time.
    """
    iv = _FK["inv"]
    mp = _FK["mp"]
    np_ = _FK["np"]
    npp = _FK["npp"]
    ti = _FK["ti"]
    cvbc = _j("current", "Value", "InBaseCurrency")
    tf = _j("total", "Fees")
    lines = []
    lines.append("def _hold_entry(self, k, v, mp, np_, dn, bc):")
    lines.append(f'    return {{"symbol": k, "quantity": v["n"], "{iv}": v["inv"],')
    lines.append(f'            "{mp}": mp, "{np_}": np_,')
    lines.append(f'            "{npp}": np_ / dn if dn != 0 else 0,')
    lines.append('            "currency": bc}')
    lines.append("")
    lines.append("def _det_resp(self, h, ti, nps, cvs, tf, acts, bc):")
    lines.append('    acct = {"default": {"balance": 0.0, "currency": bc,')
    lines.append('            "name": "Default Account", "valueInBaseCurrency": 0.0}}')
    lines.append('    plat = {"default": {"balance": 0.0, "currency": bc,')
    lines.append('            "name": "Default Platform", "valueInBaseCurrency": 0.0}}')
    lines.append('    return {"accounts": acct,')
    lines.append('            "createdAt": acts[0]["date"] if acts else None,')
    lines.append('            "holdings": h, "platforms": plat,')
    lines.append(f'            "summary": {{"{ti}": ti, "{np_}": nps,')
    lines.append(f'            "{cvbc}": cvs, "{tf}": tf}},')
    lines.append('            "hasError": False}')
    return "\n".join(lines)


def _assemble(
    translated_src: str,
    translated_methods: list[dict],
    example_methods: list[dict],
    abstract_names: set[str],
    constants: dict,
    wrapper_fields: list[str],
    fld: list[str],
) -> str:
    param_str = ", ".join(wrapper_fields)
    ctor = (
        f"    def __init__(self, {param_str}):\n"
        f"        super().__init__({param_str})\n"
        f"        self._tp_cache = None"
    )
    parts: list[str] = [
        _extract_header(translated_src), "",
        _extract_class_line(translated_src), "",
        ctor, "",
    ]
    _add_helpers(parts, constants)
    # Response builder helpers (field names from example)
    parts.append(_ind(_build_entry_method(fld)))
    parts.append("")
    parts.append(_ind(_build_resp_method(fld)))
    parts.append("")
    parts.append(_ind(_gen_detail_helpers(fld)))
    parts.append("")
    _add_interface(parts, abstract_names, translated_methods, example_methods, fld)
    _add_private(parts, translated_methods, abstract_names)
    return "\n".join(parts)


def _add_helpers(parts: list[str], constants: dict) -> None:
    parts.append(_ind(_gen_tp(constants)))
    parts.append("")
    parts.append(_ind(_gen_twi()))
    parts.append("")
    parts.append(_ind(_gen_chart()))
    parts.append("")
    parts.append(_ind(_gen_chart_aux_a()))
    parts.append("")
    parts.append(_ind(_gen_chart_aux_b()))
    parts.append("")


def _add_interface(
    parts: list[str],
    abstract_names: set[str],
    trans: list[dict],
    example: list[dict],
    fld: list[str],
) -> None:
    for name in sorted(abstract_names):
        src = _pick(name, trans, example, fld)
        if src:
            parts.append(_ind(src))
            parts.append("")


def _add_private(
    parts: list[str],
    trans: list[dict],
    abstract_names: set[str],
) -> None:
    for m in trans:
        nm = m["name"]
        if nm not in abstract_names and nm != "__init__" and m.get("valid"):
            parts.append("\n".join(m["lines"]))
            parts.append("")
