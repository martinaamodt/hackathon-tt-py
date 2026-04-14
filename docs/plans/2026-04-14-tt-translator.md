# TypeScript-to-Python Translation Tool Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a tree-sitter-based TypeScript-to-Python translator that converts Ghostfolio's portfolio calculator into working Python, passing 85+ API tests.

**Architecture:** Parse TS with tree-sitter into AST, walk AST recursively to generate Python code. Handle Big.js→float, date-fns→datetime, class/method syntax, control flow. The translator is generic (no Ghostfolio-specific logic in tt/ core); project config lives in `tt_import_map.json`.

**Tech Stack:** tree-sitter, tree-sitter-typescript, Python 3.11+

---

## Key Files to Translate

The TypeScript source files that must be translated:

| TS Source | Python Output |
|-----------|---------------|
| `apps/api/src/app/portfolio/calculator/portfolio-calculator.ts` | Base class with `compute_transaction_points()`, `compute_snapshot()`, chart/investment methods |
| `apps/api/src/app/portfolio/calculator/roai/portfolio-calculator.ts` | `RoaiPortfolioCalculator` with `get_symbol_metrics()`, `calculate_overall_performance()` |
| `apps/api/src/helper/portfolio.helper.ts` | `get_factor()` helper |
| `libs/common/src/lib/calculation-helper.ts` | `get_interval_from_date_range()` |

All output goes to: `translations/ghostfolio_pytx/app/implementation/`

## Key Translation Mappings

| TypeScript | Python |
|------------|--------|
| `new Big(x)` / `Big(x)` | `float(x)` |
| `.plus()` / `.add()` | `+` |
| `.minus()` | `-` |
| `.mul()` / `.times()` | `*` |
| `.div()` | `/` |
| `.gt()` / `.gte()` / `.lt()` / `.eq()` | `>` / `>=` / `<` / `==` |
| `.toNumber()` | (identity — already float) |
| `.abs()` | `abs()` |
| `.toFixed(n)` | `round(x, n)` |
| `const/let/var x = ...` | `x = ...` |
| `class X extends Y` | `class X(Y):` |
| `public/private/protected method()` | `def method(self):` |
| `for (const x of arr)` | `for x in arr:` |
| `x === y` / `x !== y` | `x == y` / `x != y` |
| `null` / `undefined` | `None` |
| `true` / `false` | `True` / `False` |
| `x?.y` | `(x.y if x else None)` or `getattr(x, 'y', None)` |
| `x ?? y` | `x if x is not None else y` |
| `a ? b : c` | `b if a else c` |
| `x.length` | `len(x)` |
| `arr.push(x)` | `arr.append(x)` |
| `arr.filter(fn)` | `[x for x in arr if fn(x)]` |
| `arr.map(fn)` | `[fn(x) for x in arr]` |
| `arr.find(fn)` | `next((x for x in arr if fn(x)), None)` |
| `arr.findIndex(fn)` | `next((i for i, x in enumerate(arr) if fn(x)), -1)` |
| `arr.reduce(fn, init)` | `functools.reduce(fn, arr, init)` |
| `Object.keys(x)` | `list(x.keys())` |
| `Object.entries(x)` | `list(x.items())` |
| `arr.includes(x)` | `x in arr` |
| `format(date, 'yyyy-MM-dd')` | `date.strftime('%Y-%m-%d')` or `date.isoformat()` |
| `differenceInDays(a, b)` | `(a - b).days` |
| `isBefore(a, b)` | `a < b` |
| `isAfter(a, b)` | `a > b` |
| `switch/case` | `if/elif/else` |
| `Number.EPSILON` | `sys.float_info.epsilon` |
| `interface X {}` | skip (or dataclass) |
| Type annotations | strip |

---

### Task 1: Add tree-sitter dependencies to tt

**Files:**
- Modify: `tt/pyproject.toml`

**Steps:**
1. Add `tree-sitter>=0.24` and `tree-sitter-typescript>=0.23` to dependencies
2. Run `cd tt && uv sync` to install

---

### Task 2: Build AST parser module

**Files:**
- Create: `tt/tt/parser.py`

**Steps:**
1. Create `parse_typescript(source: str) -> tree_sitter.Tree` function using tree-sitter
2. Create `walk_tree(node) -> generator` utility for AST traversal
3. Test with a simple TS snippet to verify parsing works

---

### Task 3: Build core code generator — expressions

**Files:**
- Create: `tt/tt/codegen.py`

**Steps:**
1. Build `generate(node: Node) -> str` recursive function
2. Handle expression nodes:
   - `identifier` → snake_case conversion
   - `number` / `string` → literals
   - `binary_expression` → Python operators (`===`→`==`, `!==`→`!=`)
   - `unary_expression` → Python unary ops
   - `parenthesized_expression` → `(expr)`
   - `ternary_expression` → `b if a else c`
   - `template_string` → f-string
   - `true`/`false`/`null`/`undefined` → Python equivalents
   - `array` → `[...]`
   - `object` → `{...}`
3. Handle Big.js method calls:
   - `x.plus(y)` → `(x + y)`
   - `x.minus(y)` → `(x - y)`
   - `x.mul(y)` / `x.times(y)` → `(x * y)`
   - `x.div(y)` → `(x / y)`
   - `x.gt(y)` → `(x > y)`
   - `x.gte(y)` → `(x >= y)`
   - `x.lt(y)` → `(x < y)`
   - `x.eq(y)` → `(x == y)`
   - `x.toNumber()` → `x`
   - `x.abs()` → `abs(x)`
   - `new Big(x)` → `float(x)`
4. Handle member expressions and subscript access
5. Handle call expressions with argument translation
6. Handle property access patterns (`.length` → `len()`, etc.)

---

### Task 4: Build code generator — statements and control flow

**Files:**
- Modify: `tt/tt/codegen.py`

**Steps:**
1. Handle statement nodes:
   - `variable_declaration` (const/let/var) → assignment
   - `expression_statement` → expression
   - `return_statement` → `return expr`
   - `if_statement` → `if/elif/else`
   - `for_statement` → `for` loop
   - `for_in_statement` → `for x in y:`
   - `while_statement` → `while`
   - `switch_statement` → `if/elif/else` chain
   - `break_statement` → `break`
   - `continue_statement` → `continue`
2. Handle destructuring:
   - Object destructuring `const { a, b } = x` → multiple assignments
   - Array destructuring → tuple unpacking
3. Handle type annotations — strip them
4. Handle `async/await` — strip async, remove await

---

### Task 5: Build code generator — classes and functions

**Files:**
- Modify: `tt/tt/codegen.py`

**Steps:**
1. Handle `class_declaration`:
   - `class X extends Y { ... }` → `class X(Y):`
   - Track class context for `self` insertion
2. Handle `method_definition`:
   - Strip access modifiers (public/private/protected)
   - Add `self` as first parameter
   - Convert method name to snake_case
   - Handle constructor → `__init__`
3. Handle `function_declaration` and `arrow_function`:
   - Convert to `def` or `lambda`
   - Strip type annotations from parameters and return type
4. Handle property declarations → instance variables in `__init__`

---

### Task 6: Build import mapper and project config

**Files:**
- Create: `tt/tt/import_mapper.py`
- Create: `tt/tt/scaffold/ghostfolio_pytx/tt_import_map.json`

**Steps:**
1. Create import mapping system that reads `tt_import_map.json`
2. Map TS imports to Python imports:
   - `@ghostfolio/api/app/portfolio/calculator/portfolio-calculator` → `app.wrapper.portfolio.calculator.portfolio_calculator`
   - `@ghostfolio/api/helper/portfolio.helper` → skip (inline `get_factor`)
   - `@ghostfolio/common/...` → skip (inline helpers)
   - `big.js` → skip (use float)
   - `date-fns` → `from datetime import ...`
   - `lodash` → skip (use Python builtins)
3. Handle `import { X } from 'Y'` → Python `from Y import X` via mapping
4. Skip imports that have no mapping (framework imports like NestJS)

---

### Task 7: Build the translation pipeline (runner.py)

**Files:**
- Modify: `tt/tt/translator.py` (or create `tt/tt/runner.py`)

**Steps:**
1. Create `translate_file(ts_path: Path, import_map: dict) -> str`:
   - Read TS source
   - Parse with tree-sitter
   - Generate Python with codegen
   - Apply import mapping
   - Format output
2. Create `run_translation(repo_root: Path, output_dir: Path)`:
   - Read import map from scaffold
   - Identify TS files to translate (from project config)
   - Translate each file
   - Write to output directory
   - Handle the output structure: all translated code goes into `app/implementation/`
3. The translated `RoaiPortfolioCalculator` must:
   - Extend the wrapper's `PortfolioCalculator` base class
   - Implement the 6 required methods: `get_performance()`, `get_investments()`, `get_holdings()`, `get_details()`, `get_dividends()`, `evaluate_report()`
   - Use the wrapper's `CurrentRateService` for market data

---

### Task 8: Bridge the TS calculator interface to Python wrapper interface

**Files:**
- Part of the translation output

The TS calculator and Python wrapper have different interfaces. The translated code needs bridge logic:

| Python Interface Method | TS Logic Needed |
|------------------------|-----------------|
| `get_performance()` | `computeSnapshot()` → chart + performance metrics |
| `get_investments(group_by)` | `getInvestments()` + `getInvestmentsByGroup()` |
| `get_holdings()` | `computeSnapshot()` → positions |
| `get_details(base_currency)` | `computeSnapshot()` → accounts + holdings + summary |
| `get_dividends(group_by)` | Filter DIVIDEND activities + group |
| `evaluate_report()` | Portfolio report rules evaluation |

The translator should generate a `RoaiPortfolioCalculator` that:
1. In `__init__`, calls `compute_transaction_points()` and `compute_snapshot()`
2. Each method formats the snapshot data into the expected response shape

---

### Task 9: Run `make evaluate_tt_ghostfolio` and iterate

**Steps:**
1. Run `uv run --project tt tt translate` to generate translation
2. Run `make spinup-and-test-ghostfolio_pytx` to test
3. Analyze failures — fix translator for common patterns
4. Repeat until test count plateaus

---

### Task 10: Code quality pass

**Steps:**
1. Run `make scoring_codequality` to check pyscn scores
2. Clean up translated output if needed (via post-processing in translator)
3. Ensure tt/ code itself is clean
4. Fill in SOLUTION.md

---

## Execution Priority

For maximum test passes in minimum time:
1. Tasks 1-2: Infrastructure (10 min)
2. Tasks 3-5: Core codegen (45 min) — this is the bulk
3. Tasks 6-7: Wiring (15 min)
4. Task 8: Interface bridge (20 min)
5. Task 9: Test & iterate (remaining time)
6. Task 10: Polish

## Key Risk: Interface Bridge

The biggest challenge is Task 8. The TS code uses async services (exchange rates, market data from external providers) while the Python wrapper provides a simpler synchronous `CurrentRateService`. The translated code needs to:
- Use `self.current_rate_service` instead of fetching from external services
- Skip caching/Redis logic
- Build `marketSymbolMap` and `exchangeRates` from the `CurrentRateService`
- Since all tests use same-currency (no FX), exchange rates can default to 1.0
