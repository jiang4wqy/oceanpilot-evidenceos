# Self-contained web pages

`api/demo.py` and `admin.py` serve the same `/demo` and `/admin` page contracts.
`rendering.py` reads package resources and composes one HTML response containing
all CSS, JavaScript, translations, and the logo. There are no static-file routes,
frontend build tools, CDN dependencies, or additional browser requests for assets.
The pre-existing optional Figma capture hook remains unchanged.

## Source ownership

| Resource | Responsibility |
| --- | --- |
| `merchant/shell.html`, `styles.css` | Existing merchant markup and appearance |
| `merchant/case-state.js`, `state.js` | Canonical selected case snapshot and UI-only state |
| `merchant/api.js` | Existing API prefixes and request envelopes |
| `merchant/cases.js` | Case selection, creation, existing navigation and rendering |
| `merchant/materials.js` | Material registration, withdrawal, and related audit reads |
| `merchant/agent-review.js` | Bound Agent context, conversation queue, review confirmation |
| `merchant/assessment.js` | Existing assessment, package preview, and Mock controls |
| `merchant/rules.js` | Exact rule references, catalogue, and return context |
| `merchant/support.js` | Existing audit, metrics, prevention, and safety views |
| `merchant/bootstrap.js` | Language-change handling and initial page loads |
| `operations/` | Existing read-only operations console |
| `shared/request.js` | Timeout, in-flight deduplication, and request-scope sequencing |
| `assets/logo.data-uri` | Shared embedded logo |

The files are composed in the explicit order in `rendering.py`, into one classic
script. Existing HTML event handlers can therefore still call their named
functions. Do not convert individual files to ES modules without addressing that
contract and the deployment model together.

## State and request rules

- A selected case has one server-owned snapshot. `selectedCase`, `last`, and
  `agentCase` are read-only compatibility views of it; call `selectCase()` and
  `acceptCaseSnapshot()` when a backend response should replace the snapshot.
- An accepted snapshot must match the selected case and cannot lower its revision.
  Changed revisions invalidate package/Mock presentation and pending review
  proposals. No backend review or business state is inferred by the browser.
- Async rendering must check the captured case selection/revision and, when a
  later request supersedes it, its request scope. Navigating A → B → A creates a
  new selection generation, so an earlier request for A cannot become current.
- Request timeouts also cover response-body reads. They do not automatically retry
  writes or establish whether a write reached the backend. In-flight deduplication
  lasts only until the promise settles; it is not durable business idempotency.
- Operations polling shares one in-flight refresh. Its status remains read-only;
  moving business operations to this page is outside this refactor.

Package-data patterns in `pyproject.toml` must include new page resources. Check
`tests/web/` and the existing API page tests after changes; validate a built wheel
as well when adding a new resource directory or extension.
