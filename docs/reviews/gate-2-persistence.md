# Gate 2 Independent Persistence Review

## Verdict

**PASS** — no Critical or Important persistence findings remain.

- Review timestamp: `2026-08-05T11:36:00+08:00`
- Reviewed Task 9 commit: `2085633d3732a5b282fd1e2ea4bfb89d0ec74c0e`
- Task 9 parent: `9652be6e52a393b48f427be0c0cb908338449494`
- Task 9 subject: `feat: add diagnosis snapshot CAS persistence`
- Reviewed scope: the SQLite session plus the three frozen diagnosis repository test files

The reviewed commit has the exact Task 9 technical scope: one persistence implementation
change and three new repository test files. The worktree was clean before the review.

## Command evidence

All results below are actual results from the clean reviewed commit.

| Command or probe | Exit | Actual result |
|---|---:|---|
| `git status --short` | 0 | no output |
| `git log -1 --oneline` | 0 | `2085633 feat: add diagnosis snapshot CAS persistence` |
| frozen three-file diagnosis suite | 0 | `40 passed` |
| `py -3.12 -B -m pytest -p no:cacheprovider -q tests/repository` with a unique real-file `--basetemp` | 0 | `220 passed in 12.90s` |
| full project pytest suite, independently rerun | 0 | `757 passed` |
| Ruff version probe | 0 | `ruff 0.15.22` |
| `py -3.12 -m ruff check src tests/repository` | 0 | `All checks passed!` |
| `py -3.12 -B -m compileall -q src tests/repository` | 0 | no output |
| `git diff --check` | 0 | no output |
| repository `.db-wal` / `.db-shm` scan | 0 | `wal_shm_count=0` |
| diagnosis-test `:memory:` scan | 0 | `memory_match_count=0` |
| Evidence UPDATE/DELETE and generic-save scan | 0 | `unsafe_write_match_count=0` |

The first formal Ruff invocation could not access a tool directory created by the previous
Windows sandbox identity after the execution account changed. Ruff `0.15.22` was installed
into a directory owned by the current account and the exact lint command was rerun
successfully. This was an environment ACL failure, not a lint finding.

## Transaction and invariant review

### Connection and transaction boundaries

- `connect_sqlite()` configures foreign keys and the busy timeout before any business
  transaction, verifies `journal_mode=delete`, and returns one connection owned by the
  session context.
- Public reads use one short deferred transaction and reuse an existing transaction without
  nesting `BEGIN`. `find_diagnosis()` hydrates and scans the snapshot before `COMMIT`; decode
  failures execute `ROLLBACK`, leave the connection reusable, and expose only the safe
  persistence error.
- Diagnosis writes use `BEGIN IMMEDIATE`. No rule evaluation, network request, clock read, or
  external adapter call occurs inside the transaction.

### CAS, stale input, and replay

- Current evidence revision is checked before the unique diagnosis key. Advanced evidence
  raises `DiagnosisInputStale`; an old unique row cannot be replayed.
- A matching unique key is replayed before the case-revision CAS, which permits the loser of
  an identical two-connection race to return the original snapshot.
- Replay is accepted only when the hydrated snapshot is `CURRENT`, matches the case pointer,
  and equals the current diagnosis in the case graph.
- Three repeated identical races each produced exactly one `CREATED` and one `REPLAY`, with
  one snapshot, one hypothesis, two references, and one three-event diagnosis audit set.
  Different-policy competitors produced one created result and one `ConcurrentCaseWrite`.

### Foreign keys and atomic rollback

- Composite foreign keys bind hypotheses and evidence references to the same case. The public
  commit path rejects evidence owned by a second case and leaves the first case unchanged.
- Snapshot, hypotheses, references, case pointer/status/revision/time, and audits share one
  transaction. Direct tests force failures at hypothesis insertion, reference insertion,
  the first and last audit insertions, and final in-transaction hydration; every path rolls
  back the aggregate.
- `updated_at` is `max(current.updated_at, snapshot.created_at)`. Replay, stale, validation,
  foreign-key, audit, and hydration failures preserve the prior value.

### Deterministic and safe hydration

- Hypothesis, route, and ticket evidence references are canonicalized lexically. Snapshot and
  route review-reason arrays are persisted in deterministic lexical order.
- SQLite boolean values are decoded strictly before model reconstruction. Routed diagnoses,
  RISK/HIGH human-review diagnoses, and POLICY_GAP/CONFLICTING_EVIDENCE human-only diagnoses
  survive database close and reopen.
- Caller snapshot, hypothesis, route, ticket, target, and audit payloads are scanned for
  sensitive values before replay lookup or mutation. Persisted corruption is scanned inside
  the read transaction and maps to `PersistenceInvariantViolation` without returning content.

## Residual limitations

- The persistence layer remains a synthetic, local SQLite implementation; it is not a claim
  of distributed or production Oceanpayment concurrency behavior.
- SQLite stores confidence in a `REAL` column. Current rules emit bounded two-decimal display
  scores; arbitrary higher-precision Decimal scale is not promised to round-trip unchanged.
- Service orchestration, the real diagnosis HTTP endpoint, synthetic end-to-end demos, Feishu
  integration, production data adapters, and release gates remain downstream work.
- Journal mode is deliberately `DELETE`; this gate does not claim WAL deployment behavior.

## Authorization

Gate 3 application/API work is now allowed.
