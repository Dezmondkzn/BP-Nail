Scope: BP-Nail staging source commit a3f7469. Code, tests, migrations and two documentation files; includes private secretary archive and structured tasks. Catalogs, photos and temporary imports excluded. No live infrastructure scan. Existing semantic documentation links retained; archive concept added from updated README. Host-model token usage is unavailable; zero values below are placeholders.

# Graph Report - BP-Nail  (2026-11-25)

## Corpus Check
- Corpus is ~16,579 words - fits in a single context window. You may not need a graph.

## Summary
- 477 nodes · 1621 edges · 13 communities (11 shown, 2 thin omitted)
- Extraction: 84% EXTRACTED · 16% INFERRED · 0% AMBIGUOUS · INFERRED: 257 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
-  / storage
- service / test_username_access
-  / test_document_photos
-  / catalog
- test_ai_recovery / test_user_management
- test_quotes / service
- README / validation
- test_secretary / secretary
- tests
- bot / test_file_delivery
- 20261106_optional_catalog_price / 20261110_telegram_identities
- pyproject

## God Nodes (most connected - your core abstractions)
1. `BusinessError` - 105 edges
2. `Quotes` - 49 edges
3. `UI` - 42 edges
4. `ProposalPatch` - 42 edges
5. `patch()` - 32 edges
6. `authorize()` - 27 edges
7. `LocalStorage` - 26 edges
8. `Secretary` - 25 edges
9. `AI` - 24 edges
10. `Settings` - 24 edges

## Surprising Connections (you probably didn't know these)
- `Условия и скидки доступны всем ролям; ставка НДС сохранена` --configures--> `ProposalPatch`  [INFERRED]
  README.md → bp_bot/domain.py
- `Условия и скидки доступны всем ролям; ставка НДС сохранена` --configures--> `build_proposal()`  [INFERRED]
  README.md → bp_bot/proposal_document.py
- `Личный архив протоколов и структурированные задачи` --implemented_by--> `MeetingProtocol`  [INFERRED]
  README.md → bp_bot/models.py
- `Личный архив протоколов и структурированные задачи` --implemented_by--> `ProtocolTask`  [INFERRED]
  README.md → bp_bot/models.py
- `Личный архив протоколов и структурированные задачи` --implemented_by--> `ProtocolDraft`  [INFERRED]
  README.md → bp_bot/secretary.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **КП от ввода до файлов** — readme_voice_confirmation, readme_proposal_flow, readme_catalog, readme_document_queue, readme_docx_pdf [EXTRACTED 1.00]

## Communities (13 total, 2 thin omitted)

### Community 0 - " / storage"
Cohesion: 0.05
Nodes (35): AI, buttons(), match_product(), ProductChoice, search_products(), Settings, main(), LocalStorage (+27 more)

### Community 1 - "service / test_username_access"
Cohesion: 0.07
Nodes (33): BusinessError, Base, database(), Product, Quote, RequestReceipt, TelegramIdentity, User (+25 more)

### Community 2 - " / test_document_photos"
Cohesion: 0.09
Nodes (20): build_template(), generate(), rub(), validate_letterhead(), Worker, Job, now(), build_proposal() (+12 more)

### Community 3 - " / catalog"
Cohesion: 0.08
Nodes (17): parse_fields(), CatalogRow, normalized(), parse_catalog(), word_similarity(), missing(), money(), Role (+9 more)

### Community 4 - "test_ai_recovery / test_user_management"
Cohesion: 0.09
Nodes (36): proposal_format(), strict(), configured_ai(), invalid_response(), response(), test_final_json_ignores_non_json_commentary(), test_invalid_or_truncated_ai_response_recovers(), test_money_schema_avoids_decimal_decoding_constraints() (+28 more)

### Community 5 - "test_quotes / service"
Cohesion: 0.17
Nodes (28): format_view(), ItemInput, ProposalPatch, Audit, Version, test_all_roles_edit_terms_and_discount_preserving_vat_and_history(), test_discount_applies_to_replaced_items_and_missing_prices(), test_discount_revisions_do_not_compound_and_can_be_removed() (+20 more)

### Community 6 - "README / validation"
Cohesion: 0.08
Nodes (37): Проверка восстановления резервной копии, Документированный сценарий валютной позиции, Проверка живых интеграций, Мок-тесты не подтверждают живые интеграции, Проверка перед пилотом, Восстановление задачи после аренды, Отдельная тестовая PostgreSQL, Миграции Alembic (+29 more)

### Community 7 - "test_secretary / secretary"
Cohesion: 0.17
Nodes (23): AppValue, MeetingProtocol, ProtocolTask, protocol_schema(), strict(), ProtocolDraft, Secretary, TaskDraft (+15 more)

### Community 8 - "tests"
Cohesion: 0.07
Nodes (26): DATABASE_URL, POSTGRES_DB, POSTGRES_PASSWORD, POSTGRES_USER, TEST_DATABASE_URL, jobs, tests, name (+18 more)

### Community 9 - "bot / test_file_delivery"
Cohesion: 0.22
Nodes (7): UI, callback(), handle(), start(), authorize(), format_protocol(), flow()

### Community 10 - "20261106_optional_catalog_price / 20261110_telegram_identities"
Cohesion: 0.22
Nodes (4): upgrade(), upgrade(), upgrade(), upgrade()

## Ambiguous Edges - Review These
- `Документированный сценарий валютной позиции` → `Цена менеджера с НДС`  [AMBIGUOUS]
  docs/validation.md · relation: conceptually_related_to

## Knowledge Gaps
- **26 isolated node(s):** `name`, `push`, `pull_request`, `contents`, `runs-on` (+21 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 101 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `UI` connect `bot / test_file_delivery` to ` / storage`, `service / test_username_access`, `test_ai_recovery / test_user_management`, `test_quotes / service`, `test_secretary / secretary`?**
  _High betweenness centrality (0.004) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `Quotes` (e.g. with `BusinessError` and `Role`) actually correct?**
  _`Quotes` has 11 INFERRED edges - model-reasoned connections that need verification._
- **What connects `name`, `push`, `pull_request` to the rest of the system?**
  _26 weakly-connected nodes found - possible missing edges._
- **Should ` / storage` be split into smaller, more focused modules?**
  _Cohesion score 0.05322947095098994 - nodes in this community are weakly interconnected._
- **Why does `AI` connect ` / storage` to `service / test_username_access`, `test_quotes / service`, `test_secretary / secretary`?**
  _High betweenness centrality (0.002) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `UI` (e.g. with `ProductChoice` and `BusinessError`) actually correct?**
  _`UI` has 5 INFERRED edges - model-reasoned connections that need verification._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `Документированный сценарий валютной позиции` and `Цена менеджера с НДС`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._