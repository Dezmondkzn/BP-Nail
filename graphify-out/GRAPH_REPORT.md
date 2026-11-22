Scope: BP-Nail staging commit fa8c549. Code, tests, migrations, configuration and 2 documentation files. Catalog datasets, photographs and temporary import scripts excluded. No live infrastructure scan. Semantic extraction used the host assistant; token usage is unavailable, zero values below are placeholders, not actual usage.

# Graph Report - BP-Nail  (2026-11-21)

## Corpus Check
- Corpus is ~16,579 words - fits in a single context window. You may not need a graph.

## Summary
- 423 nodes · 1321 edges · 14 communities (11 shown, 3 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 190 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- service / models
- test_user_management / test_ai_recovery
- docs / ai
- storage / test_file_delivery
- docs / test_document_photos
- README / validation
- test_bot / catalog
- test_quotes / service
- tests
- bot / test_file_delivery
- 20261106_optional_catalog_price / 20261110_telegram_identities
- catalog / docs
- pyproject

## God Nodes (most connected - your core abstractions)
1. `BusinessError` - 93 edges
2. `Quotes` - 49 edges
3. `UI` - 37 edges
4. `ProposalPatch` - 32 edges
5. `patch()` - 25 edges
6. `LocalStorage` - 24 edges
7. `AI` - 23 edges
8. `authorize()` - 23 edges
9. `Settings` - 22 edges
10. `Worker` - 16 edges

## Surprising Connections (you probably didn't know these)
- `test_repeated_invalid_response_is_bounded_and_actionable()` --uses--> `BusinessError`  [INFERRED]
  tests/test_ai_recovery.py → bp_bot/domain.py
- `test_retry_does_not_bypass_business_rules()` --uses--> `BusinessError`  [INFERRED]
  tests/test_ai_recovery.py → bp_bot/domain.py
- `test_refusal_is_not_retried()` --uses--> `BusinessError`  [INFERRED]
  tests/test_ai_recovery.py → bp_bot/domain.py
- `test_simple_money_schema_keeps_domain_limits()` --uses--> `BusinessError`  [INFERRED]
  tests/test_ai_recovery.py → bp_bot/domain.py
- `test_initial_roles_and_revocation_survive_restart()` --uses--> `BusinessError`  [INFERRED]
  tests/test_bootstrap.py → bp_bot/domain.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **КП от ввода до файлов** — readme_voice_confirmation, readme_proposal_flow, readme_catalog, readme_document_queue, readme_docx_pdf [EXTRACTED 1.00]

## Communities (14 total, 3 thin omitted)

### Community 0 - "service / models"
Cohesion: 0.07
Nodes (24): money(), Role, totals(), AppValue, Audit, Base, database(), Job (+16 more)

### Community 1 - "test_user_management / test_ai_recovery"
Cohesion: 0.08
Nodes (45): configured_ai(), invalid_response(), response(), test_final_json_ignores_non_json_commentary(), test_invalid_or_truncated_ai_response_recovers(), test_money_string_keeps_exact_price_and_safe_delivery_terms(), test_real_sdk_incomplete_json_is_checked_before_validation(), flow() (+37 more)

### Community 2 - "docs / ai"
Cohesion: 0.08
Nodes (20): AI, parse_fields(), proposal_format(), strict(), normalized(), parse_catalog(), BusinessError, missing() (+12 more)

### Community 3 - "storage / test_file_delivery"
Cohesion: 0.09
Nodes (17): buttons(), format_view(), Worker, main(), LocalStorage, S3Storage, storage(), valid_key() (+9 more)

### Community 4 - "docs / test_document_photos"
Cohesion: 0.11
Nodes (14): build_template(), generate(), rub(), validate_letterhead(), build_proposal(), table(), word_photo(), letterhead() (+6 more)

### Community 5 - "README / validation"
Cohesion: 0.08
Nodes (36): Проверка восстановления резервной копии, Документированный сценарий валютной позиции, Проверка живых интеграций, Мок-тесты не подтверждают живые интеграции, Проверка перед пилотом, Восстановление задачи после аренды, Отдельная тестовая PostgreSQL, Миграции Alembic (+28 more)

### Community 6 - "test_bot / catalog"
Cohesion: 0.11
Nodes (18): match_product(), ProductChoice, search_products(), word_similarity(), Settings, test_missing_prices_are_requested_sequentially_without_losing_quote(), test_product_choice_preserves_request_and_rejects_stale_buttons(), click() (+10 more)

### Community 7 - "test_quotes / service"
Cohesion: 0.25
Nodes (20): ItemInput, ProposalPatch, Version, patch(), test_ambiguous_product_fails_closed(), test_calculations_and_locked_prices(), test_chief_vat_override_preserves_gross_and_records_reason(), test_concurrent_revisions_have_only_one_winner() (+12 more)

### Community 8 - "tests"
Cohesion: 0.07
Nodes (26): DATABASE_URL, POSTGRES_DB, POSTGRES_PASSWORD, POSTGRES_USER, TEST_DATABASE_URL, jobs, tests, name (+18 more)

### Community 9 - "bot / test_file_delivery"
Cohesion: 0.23
Nodes (6): UI, callback(), handle(), start(), authorize(), flow()

### Community 10 - "20261106_optional_catalog_price / 20261110_telegram_identities"
Cohesion: 0.27
Nodes (3): upgrade(), upgrade(), upgrade()

## Ambiguous Edges - Review These
- `Документированный сценарий валютной позиции` → `Цена менеджера с НДС`  [AMBIGUOUS]
  docs/validation.md · relation: conceptually_related_to

## Knowledge Gaps
- **26 isolated node(s):** `name`, `push`, `pull_request`, `contents`, `runs-on` (+21 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 99 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `UI` connect `bot / test_file_delivery` to `service / models`, `test_user_management / test_ai_recovery`, `docs / ai`, `test_bot / catalog`, `test_quotes / service`?**
  _High betweenness centrality (0.003) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `Quotes` (e.g. with `BusinessError` and `Role`) actually correct?**
  _`Quotes` has 11 INFERRED edges - model-reasoned connections that need verification._
- **What connects `name`, `push`, `pull_request` to the rest of the system?**
  _26 weakly-connected nodes found - possible missing edges._
- **Should `service / models` be split into smaller, more focused modules?**
  _Cohesion score 0.07355769230769231 - nodes in this community are weakly interconnected._
- **Why does `Quotes` connect `service / models` to `test_user_management / test_ai_recovery`, `docs / ai`, `test_bot / catalog`, `test_quotes / service`, `bot / test_file_delivery`?**
  _High betweenness centrality (0.002) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `UI` (e.g. with `ProductChoice` and `BusinessError`) actually correct?**
  _`UI` has 4 INFERRED edges - model-reasoned connections that need verification._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `Документированный сценарий валютной позиции` and `Цена менеджера с НДС`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._