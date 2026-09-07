# Self-contained dual case workspaces

`api/demo.py` serves `/demo` (merchant materials) and `/business` (business
review). Both pages use one shell and read the same server case snapshot. The
separate `admin.py` application continues to serve the read-only `/admin`
operations console. Its configured origin is a secondary link, not a business
API proxy.

`rendering.py` composes package resources into one HTML response, including
styles, scripts, translations and logo. No frontend build, CDN dependency or
static-asset route is required. The optional Figma capture hook activates only
when the URL contains the explicit capture hash.

| Resource | Responsibility |
| --- | --- |
| `merchant/shell.html`, `styles.css` | Shared shell, role-specific controls, existing visual system |
| `merchant/case-state.js`, `state.js` | Canonical case snapshot, revision and UI-only state |
| `merchant/api.js` | Demo role headers, persisted command ID, receipt recovery, retry boundaries |
| `merchant/cases.js` | Lists, selection, new copies, URL case/section/filter restoration |
| `merchant/materials.js` | Explicit metadata registration and selected-item withdrawal |
| `merchant/agent-review.js` | Read-only Agent explanation, source labels, queue and stale-response guards |
| `merchant/assessment.js` | Revision-bound review preview/confirmation and frozen summary download |
| `merchant/concerns.js` | Human concern registration and business resolution |
| `merchant/rules.js` | Exact case rules, catalog provenance, return to original case |
| `merchant/bootstrap.js` | Event wiring, language preferences, pending receipt recovery |
| `operations/` | Existing read-only operations console |
| `shared/request.js` | Bounded JSON/text requests, single flight and request scopes |
| `assets/logo.data-uri` | Shared embedded logo |

The explicit order in `rendering.py` composes a classic script. Inline event
handlers still call named functions; do not convert one resource to an ES module
without updating that contract.

A selected case has one server-owned snapshot. The compatibility properties
`selectedCase`, `last` and `agentCase` are read-only views of it. Revisions cannot
move backward, and changing a revision or rule fingerprint invalidates the pending
review preview and old Agent conclusion. Switching cases clears case-specific form text. Request
scopes and selection generations reject late A → B → A responses.

All new business writes use `/api/v1/workspace/commands` with a command ID,
explicit confirmation and (except creation/copy) the selected revision. Review
also submits `expected_rule_fingerprint`, which the backend checks before writing
the decision. A timeout
does not imply failure: the page persists the original command in sessionStorage,
queries its receipt and retries only that same payload/ID. Unknown operations
block new writes. Definitive rejection can be dismissed only after receipt lookup
returns UNKNOWN. The server, not this browser state, provides durable idempotency.

`X-Demo-Role` and fixed ASCII `X-Demo-Actor` are visible demonstration identities,
not production authentication. Business review and concern resolution remain
server-gated. Summary generation reads a deterministic snapshot without a model
call; both roles can download saved immutable summaries. Final appeal is absent
from these pages and is controlled independently by the backend feature gate.

`tests/web/test_page_runtime.py` executes the actual packaged JavaScript in Node,
including command recovery, explicit review/material confirmation, case/revision
races, role navigation and output provenance. API page tests cover route,
accessibility, packaging and visible scope contracts. Built wheels must include
all package resources through the `pyproject.toml` package-data globs.
