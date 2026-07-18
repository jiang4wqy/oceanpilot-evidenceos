# Gate 1 Independent Domain Review

## Verdict

**PASS** — no Critical or Important findings remain.

- Review timestamp: `2026-07-18T22:58:26+08:00`
- Reviewed Task 5 commit: `94192a0a548d4e568c9a08b70312397230036930`
- Task 5 parent: `fcf21d6aeb9385e30ff48108fa0e91bca22c778a`
- Task 5 subject: `feat: freeze application and store contracts`
- Gate-contract HEAD: `2ab3efb40c1574b434811630afc800d8eb74d6bf`
- Design blob: `2adcf725911cf5f78e4c4b5181682a6839748912`
- Implementation-plan blob: `b8d26afbab330126c358a3cabf17be8b213a626f`

The Task 5 commit has the exact five-file scope defined by the approved plan. It is an ancestor of the Gate-contract HEAD, and `94192a0..2ab3efb` contains no changes under `src`, `tests`, `pyproject.toml`, `.gitignore`, `.github`, or `examples`.

## Command evidence

All results below are actual results from the clean Gate-contract HEAD, not copied expectations.

| Command or probe | Exit | Actual result |
|---|---:|---|
| `git status --short` before review | 0 | no output |
| `git rev-parse 94192a0^` | 0 | `fcf21d6aeb9385e30ff48108fa0e91bca22c778a` |
| `git show -s --format=%s 94192a0` | 0 | exact required subject |
| `git diff-tree --no-commit-id --name-status -r 94192a0` | 0 | exactly five authorized `A` paths |
| `git show --check --oneline 94192a0` | 0 | clean patch |
| `git merge-base --is-ancestor 94192a0 HEAD` | 0 | Task 5 is an ancestor |
| `git diff --quiet 94192a0..HEAD -- src tests pyproject.toml .gitignore .github examples` | 0 | no technical drift |
| two `git rev-parse HEAD:<document>` probes | 0 | both non-empty blob IDs recorded above |
| `.\.venv\Scripts\python.exe -m pytest tests/domain/test_application_contracts.py tests/domain/test_import_boundaries.py -q` | 0 | `54 passed in 0.29s` |
| `.\.venv\Scripts\python.exe -m pytest tests/domain -q` | 0 | `461 passed in 0.94s` |
| `.\.venv\Scripts\python.exe -m pytest -q` | 0 | `461 passed in 0.95s` |
| `.\.venv\Scripts\python.exe -m ruff check src tests/domain` | 0 | `All checks passed!` |
| `.\.venv\Scripts\python.exe -m compileall -q src tests/domain` | 0 | no output |
| deterministic replay with `PYTHONHASHSEED=1` | 0 | `208 passed in 0.40s` |
| deterministic replay with `PYTHONHASHSEED=777` | 0 | `208 passed in 0.39s` |
| domain outward-dependency `Assert-NoMatch` | 1 (observed; expected no-match) | no matches |
| application outward-dependency `Assert-NoMatch` | 1 (observed; expected no-match) | no matches |
| rule-adapter outward-dependency probe | 1 (observed; expected no-match) | no FastAPI, SQLite, API, application, or adapter imports |
| rule sensitive-reference probe | 1 (observed; expected no-match) | no `source_ref` or `merchant_ref` reads |
| Task 5 outer-protocol alias `Assert-NoMatch` | 1 (observed; expected no-match) | no matches |
| deterministic-path side-effect `Assert-NoMatch` | 1 (observed; expected no-match) | no matches |
| `rg -n '^class DiagnosisEngine\b' src/oceanpilot` | 0 | exactly one definition: `src/oceanpilot/domain/diagnosis.py:78` |
| `git diff --check 78e7064..HEAD` | 0 | no whitespace errors |
| `git status --short` after evidence collection | 0 | no output |

The first auxiliary static-probe wrapper attempt failed before executing any probe because an added PowerShell status label used invalid `$Label:` interpolation. The corrected wrapper used `${Label}:`; every planned probe then executed and passed as recorded above. The reviewed plan's `Assert-NoMatch` function did not contain the faulty status-label line.

## Gate 1 invariant review

### 1. Evidence-view-only decisions

`assess_readiness()` accepts only `ActiveEvidenceView`. Rule matching, decisive evidence, and confidence read from that view. Case ID, status, summary, merchant reference, case revision, and evidence revision do not affect the result; the only tested case-field propagation is `synthetic=true` into `TicketDraft`.

Direct evidence:

- `test_assess_readiness_has_the_locked_single_parameter_interface`
- `test_case_metadata_is_ignored_and_inputs_are_not_mutated`
- `test_unrelated_low_quality_evidence_does_not_change_confidence`
- `test_each_rule_emits_the_complete_fixed_output`
- independent static inspection: the only `case.` read in `rules.py` is `case.synthetic`

### 2. Frozen, append-only evidence

`EvidenceItem` is frozen. The application store contract exposes atomic creation and append operations, not Evidence UPDATE/DELETE, generic save, or raw SQLite connection access.

Direct evidence:

- `test_evidence_item_is_frozen`
- `test_store_session_has_only_the_exact_atomic_contracts`
- `test_store_session_parameter_order_and_kinds_are_exact`
- `test_store_factory_signature_is_exact`

### 3. Confidence math and input safety

All five source-quality values and full-coverage results are independently locked. `USER_REPORTED` produces raw `0.865`, display `0.87`, and exactly `LOW_CONFIDENCE` plus `INSUFFICIENT_SOURCE_QUALITY`; `SYNTHETIC_TEST` produces raw/display `0.940/0.94`. Threshold decisions use the unrounded score. Invalid, non-finite, wrongly typed, empty, and out-of-range Decimal inputs use one safe error.

Direct evidence:

- `test_source_quality_map_is_exact_and_externally_immutable`
- `test_all_five_full_coverage_scores_are_exact`
- `test_mixed_sources_use_the_minimum_independent_of_order`
- `test_invalid_coverage_uses_one_safe_error`
- `test_invalid_consistency_uses_one_safe_error`
- `test_empty_decisive_evidence_uses_the_same_safe_error`
- `test_unrounded_score_controls_low_confidence_gate`
- `test_source_quality_point_75_is_not_insufficient`

### 4. Four-rule decision contract

The immutable table contains exactly four rule IDs. Accepted, excluded, missing, and `CONFIRMED_UNAVAILABLE` predicate paths are independently parameterized. A single rule emits all-and-only decisive references; conflicting evidence, zero matches, and multiple matches emit no hypothesis.

Direct evidence:

- `test_rules_are_exact_and_deeply_immutable`
- `test_every_accepted_predicate_value_matches`
- `test_every_excluded_predicate_value_does_not_match`
- `test_missing_or_unavailable_required_predicate_never_emits_target_rule`
- `test_each_rule_emits_the_complete_fixed_output`
- `test_decisive_refs_are_deduplicated_and_lexical`
- `test_conflicting_view_short_circuits_an_otherwise_matching_rule`
- `test_zero_matches_returns_policy_gap_only`
- `test_multiple_matches_return_conflict_only_without_risk_or_confidence_reasons`

### 5. Draft semantics and sensitive-value exclusion

Fixed explanations state that evidence matches a rule and requires checking; they do not present an unverified cause as fact. Output remains `HypothesisDraft`/`TicketDraft`, preserves `synthetic=true`, and limits its free-form textual content to fixed text and safe `evidence_code=value` summaries while referencing evidence by ID. Neither `source_ref` nor `merchant_ref` is read by the rule implementation or included in output.

Direct evidence:

- `test_each_rule_emits_the_complete_fixed_output`
- `test_case_metadata_is_ignored_and_inputs_are_not_mutated`
- independent static inspection of `rules.py` for `source_ref` and `merchant_ref`

### 6. Commands and stable application errors

The three commands have the exact required fields, ordering, annotations, keyword-only/no-default construction, frozen nested values, strict string validation, hidden validation inputs, and `extra="forbid"`. The eight application errors have exact safe messages. Seven ordinary errors reject arbitrary payloads and resist `args` or instance-message shadowing; `CaseNotReady` is the sole structured error and has three required keyword-only, read-only values.

Direct evidence:

- `test_command_field_sets_and_order_are_exact`
- `test_command_fields_are_required_and_constructor_is_keyword_only`
- `test_commands_inherit_the_safe_frozen_model_contract`
- `test_add_evidence_copies_nested_dicts_and_freezes_nested_values`
- `test_application_error_subclass_set_and_messages_are_exact`
- `test_ordinary_errors_reject_all_payloads`
- `test_ordinary_error_strings_ignore_args_and_instance_message`
- `test_case_not_ready_signature_and_type_hints_are_exact`
- `test_case_not_ready_is_keyword_only_and_always_uses_safe_string`

### 7. Exact ports and protocol ownership

`CaseStoreSession` has exactly seven public contract methods, including three atomic write methods, and `CaseStoreFactory` has only `__call__`, with exact annotations and no defaults. Task 5 application modules do not define, import, alias, or re-export `DiagnosisEngine`, `EvidenceSource`, or `SyntheticScenario`. A future `application/case_service.py` may legally import the single domain `DiagnosisEngine`.

Direct evidence:

- `test_store_session_has_only_the_exact_atomic_contracts`
- `test_store_session_parameter_order_and_kinds_are_exact`
- `test_store_session_annotations_and_returns_are_exact`
- `test_store_factory_signature_is_exact`
- `test_task_five_modules_do_not_define_or_reexport_outer_ports`
- `test_task_five_modules_do_not_import_outer_protocols_under_aliases`
- `test_future_case_service_may_import_the_domain_diagnosis_engine`
- `test_engine_and_source_protocol_ownership_is_unique_across_src`

### 8. Dependency direction and deterministic execution

Absolute, relative, aliased, and aggregate imports are checked. Domain/application code has no forbidden outward framework or persistence dependency. The deterministic evidence/state/diagnosis/rule path has no UUID or current-time generation and no runtime randomness, environment, network, FastAPI, or SQLite access. Evidence timestamp parsing and normalization remains allowed.

Direct and independent evidence:

- `test_ast_import_resolution_covers_absolute_and_relative_forms`
- `test_combined_absolute_imports_reach_the_boundary_predicate`
- `test_imported_symbol_scan_uses_original_name_not_alias`
- `test_domain_import_boundary_has_no_forbidden_dependencies`
- `test_application_import_boundary_has_no_forbidden_dependencies`
- four planned `Assert-NoMatch` probes plus the rule-adapter outward-dependency probe
- two `PYTHONHASHSEED` deterministic replays
- the single-definition `DiagnosisEngine` probe

### 9. Independent test oracles

Behavior expectations are frozen in test-local tables such as `RULE_CASES`, `PREDICATE_VALUES`, and `EXPECTED_SOURCE_QUALITY`. Tests do not derive expected rule output from `RULES`, expected scores from `SOURCE_QUALITY`, or expected references from the result being asserted. Production tables are imported only for exact table-content and immutability review.

Independent behavior review re-ran the relevant model/evidence/readiness/confidence/rule/application tests: `355 passed in 0.69s`. Independent contract/dependency review re-ran the focused `54` and complete domain `461` tests. Both reviewers returned `PASS` with no Critical or Important findings.

## Residual limitations

- All current examples and validations use synthetic data; no real merchant record is claimed.
- Rule values and confidence thresholds have not been calibrated against Oceanpayment historical incidents.
- `CaseService`, SQLite persistence, FastAPI endpoints, and production concurrency controls are not implemented yet.
- There is no real Feishu or Oceanpayment integration, MCP connection, credential flow, or external data ingestion yet.

## Authorization

Gate 2 SQLite work is now allowed.
