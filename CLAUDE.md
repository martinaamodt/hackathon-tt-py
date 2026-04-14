# Hackathon TT Project

## Task
Build a TypeScript-to-Python translation tool (`tt`) that translates Ghostfolio's portfolio calculator.

## Competition Rules — MUST FOLLOW
1. **No LLMs for translation.** LLMs may help build `tt` itself.
2. **No pre-written domain logic in tt/** — translated code must come from actual translation, not pregenerated logic.
3. **No project-specific mappings in tt/ core** (no hard-coded `@ghostfolio/...` paths). Project config goes in `tt_import_map.json` in the scaffold directory.
4. **Wrapper files are immutable** — `app/main.py` + `app/wrapper/` must be byte-for-byte identical to the example.
5. **tt only generates code in `app/implementation/`** — nothing outside that directory may be generated or modified.
6. **No node/js-tools** — translation must happen purely in Python.
7. **May use AST libraries** (tree-sitter, etc.).
8. **Frequent commits** — git log must reflect gradual development.
9. **Run `make detect_rule_breaches`** before submitting to verify compliance.
10. **Do not modify `translations/ghostfolio_pytx_example/`** before running tt.

## Automated Rule Checks
- `detect_llm_usage` — no LLM API imports/calls in tt/
- `detect_direct_mappings` — no project-specific import paths in tt/ core
- `detect_explicit_implementation` — no domain logic in tt/ (function size >30 stmts, domain identifiers like totalInvestment/netPerformance)
- `detect_explicit_financial_logic` — no financial arithmetic in scaffold
- `detect_scaffold_bloat` — scaffold main.py must stay minimal
- `detect_code_block_copying` — no 10+ line blocks from tt/ appearing verbatim in output
- `detect_interface_violation` — calculator must implement required interface
- `detect_wrapper_modification` — wrapper files must be identical to example

## Stack
- Python 3.11+
- tree-sitter + tree-sitter-typescript for parsing
- pytest for testing
- FastAPI + uvicorn for the translated project

## Commands
- `uv run --project tt tt translate` — run the translator
- `make evaluate_tt_ghostfolio` — full evaluation (tests 85% + code quality 15%)
- `make translate-and-test-ghostfolio_pytx` — translate + spinup + test
- `make spinup-and-test-ghostfolio_pytx` — test pre-translated output
- `make detect_rule_breaches` — check rule compliance
- `make scoring_codequality` — run code quality scoring
- `make publish_results` — publish to leaderboard

## Architecture
```
projects/ghostfolio/           (TS source to translate)
        |  tt translate
translations/ghostfolio_pytx/app/
  |- main.py + wrapper/        (immutable, copied from example)
  |- implementation/           (tt generates ONLY here)
      |- portfolio/calculator/roai/portfolio_calculator.py
```

## Translated Calculator Interface
Must implement abstract base from `app.wrapper.portfolio.calculator.portfolio_calculator`:
- `get_performance()` -> `{chart, firstOrderDate, performance: {...}}`
- `get_investments(group_by)` -> `{investments: [{date, investment}]}`
- `get_holdings()` -> `{holdings: {symbol: {...}}}`
- `get_details(base_currency)` -> `{accounts, holdings, summary, ...}`
- `get_dividends(group_by)` -> `{dividends: [{date, investment}]}`
- `evaluate_report()` -> `{xRay: {categories, statistics}}`

## Scoring
- **85%** test pass rate (complexity-weighted, ~113 tests, 346 max points)
- **15%** code quality (pyscn: complexity, duplication, coupling, architecture)

## Workflow
1. Read task description — understand requirements
2. Plan briefly (2-3 min max)
3. Execute fast with TDD
4. `make detect_rule_breaches` frequently
5. `make evaluate_tt_ghostfolio` to check progress
6. Commit often with clear messages
7. Fill in SOLUTION.md before submission
