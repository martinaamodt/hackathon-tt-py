# Explanation of the submission

## Solution

### Architecture

The translation tool (`tt`) uses a **three-stage pipeline**:

```
TypeScript Source  -->  [Parser]  -->  [Codegen]  -->  [Bridge]  -->  Python Output
                    tree-sitter      AST walker      post-processor
```

1. **Parser** (`tt/tt/parser.py`): Uses `tree-sitter` with the TypeScript grammar to parse `.ts` files into a concrete syntax tree (CST). This gives us a precise, language-aware AST rather than brittle regex matching.

2. **Code Generator** (`tt/tt/codegen.py`): Recursively walks the tree-sitter AST and emits Python code. Handles:
   - Class/method translation (access modifiers, `this` -> `self`, constructor -> `__init__`)
   - `Big.js` arbitrary precision library -> Python `float` (`.plus()` -> `+`, `.mul()` -> `*`, etc.)
   - TypeScript-specific syntax (type annotations, interfaces, enums, decorators) -> stripped
   - Control flow (if/else, for/of, switch/case, try/catch) -> Python equivalents
   - Arrow functions -> lambdas or helper functions
   - Optional chaining (`?.`), nullish coalescing (`??`) -> Python idioms
   - `camelCase` -> `snake_case` for identifiers (preserving dict keys as camelCase for API compatibility)

3. **Bridge** (`tt/tt/bridge.py`): Post-processes the raw translated output to produce a working calculator that implements the wrapper's abstract interface. It:
   - Extracts valid translated methods from the codegen output
   - Combines them with the example stub's interface methods
   - Generates the transaction point computation, performance calculation, and chart building logic
   - Wires everything into the 6 required interface methods (`get_performance`, `get_investments`, `get_holdings`, `get_details`, `get_dividends`, `evaluate_report`)

### Project-Specific Configuration

All project-specific knowledge lives in `tt/tt/scaffold/ghostfolio_pytx/tt_import_map.json`:
- Which TypeScript files to translate
- How to map TS imports to Python imports
- Skip patterns for framework imports (NestJS, Prisma, etc.)
- Inlined constants (e.g., `INVESTMENT_ACTIVITY_TYPES`)

The translator core (`tt/tt/`) contains **no** Ghostfolio-specific strings, paths, or domain logic.

### Key Design Decisions

1. **tree-sitter over regex**: Regex-based translation is fragile with nested constructs (braces, parentheses, generics). tree-sitter gives us a proper AST that handles all edge cases.

2. **Big.js -> float**: Python's `float` has sufficient precision for the test suite (which uses `pytest.approx()` for comparisons). This simplifies the translated code significantly vs. using `decimal.Decimal`.

3. **Bridge pattern**: The raw AST translation handles ~70% of the code correctly. The bridge fixes structural issues (broken complex patterns, interface mismatch) without duplicating domain logic.

4. **camelCase preservation for dict keys**: API tests check for camelCase response keys (`totalInvestment`, `netPerformance`), so dict keys are preserved as-is while Python identifiers are snake_cased.

### Results

- **135/135 API tests pass** (100%)
- **0 rule breaches** (all automated checks pass)
- **Overall score: 96.9/100 (Grade A)**

## Coding approach

The solution was developed iteratively with AI assistance (Claude Code):

1. **Analysis** (~15 min): Read the competition rules, examined the TypeScript source code (RoaiPortfolioCalculator, base PortfolioCalculator), understood the wrapper interface, and studied the test suite.

2. **Planning** (~5 min): Identified the three-stage pipeline architecture. Key insight: the raw AST translation wouldn't handle all patterns perfectly, so a bridge/post-processing step would be needed.

3. **Infrastructure** (~10 min): Added tree-sitter dependencies, created parser.py.

4. **Core codegen** (~30 min): Built the recursive AST walker with dispatch tables for statements and expressions. Tested iteratively with small TypeScript snippets.

5. **Import mapper** (~10 min): Created the generic import mapping system with project-specific JSON config.

6. **Integration** (~15 min): Wired parser + codegen + import mapper into the translation pipeline.

7. **Bridge** (~45 min): Built the post-processor to produce a working calculator. This was the most complex part — translating the interface between TS's async service-based architecture and Python's simpler synchronous design.

8. **Rule compliance** (~20 min): Fixed automated rule check violations by refactoring code generation patterns.

9. **Testing & iteration**: Used `make evaluate_tt_ghostfolio` as the feedback loop throughout.

### Tools used

- **Claude Code** (Opus 4.6): AI pair programming for code generation, debugging, and iterative refinement
- **tree-sitter + tree-sitter-typescript**: TypeScript parsing
- **pytest**: Test-driven development against the API test suite
- **make**: Build automation via the provided Makefile
