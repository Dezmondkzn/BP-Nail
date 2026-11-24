Scope: BP-Nail staging source commit 6003ee9. Code, tests and two documentation files; includes commercial terms and discount changes. Catalogs, photos and temporary imports excluded. No live infrastructure scan. Existing semantic documentation links retained; commercial-terms concept added from updated README. Host-model token usage is unavailable; zero values below are placeholders.

# Graph Report - BP-Nail  (2026-11-24)

## Corpus Check
- Corpus is ~16,579 words - fits in a single context window. You may not need a graph.

## Summary
- 436 nodes · 1424 edges · 12 communities (10 shown, 2 thin omitted)
- Extraction: 85% EXTRACTED · 15% INFERRED · 0% AMBIGUOUS · INFERRED: 215 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- test_user_management / test_ai_recovery
- service / test_username_access
-  / models
- test_quotes / service
-  / catalog
-  / test_document_photos
- README / validation
- storage / test_file_delivery
- tests
- bot / test_file_delivery
- pyproject

## God Nodes (most connected - your core abstractions)
1. `BusinessError` - 95 edges
2. `Quotes` - 49 edges
3. `ProposalPatch` - 42 edges
4. `UI` - 39 edges
5. `patch()` - 32 edges
6. `LocalStorage` - 26 edges
7. `Settings` - 24 edges
8. `AI` - 23 edges
9. `authorize()` - 23 edges
10. `Worker` - 16 edges

## Surprising Connections (you probably didn't know these)
- `Условия и скидки доступны всем ролям; ставка НДС сохранена` --configures--> `ProposalPatch`  [INFERRED]
  README.md → bp_bot/domain.py
- `Условия и скидки доступны всем ролям; ставка НДС сохранена` --configures--> `build_proposal()`  [INFERRED]
  README.md → bp_bot/proposal_document.py
- `test_repeated_invalid_response_is_bounded_and_actionable()` --uses--> `BusinessError`  [INFERRED]
  tests/test_ai_recovery.py → bp_bot/domain.py
- `test_retry_does_not_bypass_business_rules()` --uses--> `BusinessError`  [INFERRED]
  tests/test_ai_recovery.py → bp_bot/domain.py
- `test_refusal_is_not_retried()` --uses--> `BusinessError`  [INFERRED]
  tests/test_ai_recovery.py → bp_bot/domain.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **КП от ввода до файлов** — readme_voice_confirmation, readme_proposal_flow, readme_catalog, readme_document_queue, readme_docx_pdf [EXTRACTED 1.00]

## Communities (12 total, 2 thin omitted)

### Community 0 - "test_user_management / test_ai_recovery"
Cohesion: 0.05
Nodes (53): AI, proposal_format(), strict(), Settings, configured_ai(), invalid_response(), response(), test_final_json_ignores_non_json_commentary() (+45 more)

### Community 1 - "service / test_username_access"
Cohesion: 0.08
Nodes (29): match_product(), ProductChoice, search_products(), word_similarity(), BusinessError, Quote, User, Quotes (+21 more)

### Community 2 - " / models"
Cohesion: 0.07
Nodes (17): buttons(), main(), AppValue, Base, database(), now(), Product, RequestReceipt (+9 more)

### Community 3 - "test_quotes / service"
Cohesion: 0.15
Nodes (31): format_view(), ItemInput, missing(), money(), ProposalPatch, totals(), Audit, Version (+23 more)

### Community 4 - " / catalog"
Cohesion: 0.09
Nodes (13): parse_fields(), CatalogRow, normalized(), parse_catalog(), Role, parse_price(), CBR, test_cbr_failure_does_not_use_fake_rate() (+5 more)

### Community 5 - " / test_document_photos"
Cohesion: 0.11
Nodes (14): build_template(), generate(), rub(), validate_letterhead(), build_proposal(), table(), word_photo(), letterhead() (+6 more)

### Community 6 - "README / validation"
Cohesion: 0.08
Nodes (37): Проверка восстановления резервной копии, Документированный сценарий валютной позиции, Проверка живых интеграций, Мок-тесты не подтверждают живые интеграции, Проверка перед пилотом, Восстановление задачи после аренды, Отдельная тестовая PostgreSQL, Миграции Alembic (+29 more)

### Community 7 - "storage / test_file_delivery"
Cohesion: 0.12
Nodes (14): Worker, Job, LocalStorage, S3Storage, valid_key(), test_failure_logs_do_not_expose_exception_data(), setup_ui(), test_delivery_survives_restart_and_retries_only_unsent_file() (+6 more)

### Community 8 - "tests"
Cohesion: 0.07
Nodes (26): DATABASE_URL, POSTGRES_DB, POSTGRES_PASSWORD, POSTGRES_USER, TEST_DATABASE_URL, jobs, tests, name (+18 more)

### Community 9 - "bot / test_file_delivery"
Cohesion: 0.25
Nodes (6): UI, callback(), handle(), start(), authorize(), flow()

## Ambiguous Edges - Review These
- `Документированный сценарий валютной позиции` → `Цена менеджера с НДС`  [AMBIGUOUS]
  docs/validation.md · relation: conceptually_related_to

## Knowledge Gaps
- **26 isolated node(s):** `name`, `push`, `pull_request`, `contents`, `runs-on` (+21 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 99 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `UI` connect `bot / test_file_delivery` to `service / test_username_access`, ` / models`, `test_quotes / service`?**
  _High betweenness centrality (0.003) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `Quotes` (e.g. with `BusinessError` and `Role`) actually correct?**
  _`Quotes` has 11 INFERRED edges - model-reasoned connections that need verification._
- **What connects `name`, `push`, `pull_request` to the rest of the system?**
  _26 weakly-connected nodes found - possible missing edges._
- **Should `test_user_management / test_ai_recovery` be split into smaller, more focused modules?**
  _Cohesion score 0.05368382080710848 - nodes in this community are weakly interconnected._
- **Why does `Quotes` connect `service / test_username_access` to `test_user_management / test_ai_recovery`, ` / models`, `test_quotes / service`, ` / catalog`, `storage / test_file_delivery`?**
  _High betweenness centrality (0.002) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `UI` (e.g. with `ProductChoice` and `BusinessError`) actually correct?**
  _`UI` has 4 INFERRED edges - model-reasoned connections that need verification._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `Документированный сценарий валютной позиции` and `Цена менеджера с НДС`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._