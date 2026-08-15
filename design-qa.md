# Design QA

- Source visual truth:
  - `/var/folders/l_/94l5sj5x5nb9rtwpqw_cfp100000gn/T/TemporaryItems/NSIRD_screencaptureui_EgpG6Y/截屏2026-08-14 23.22.50.png`
  - `/var/folders/l_/94l5sj5x5nb9rtwpqw_cfp100000gn/T/TemporaryItems/NSIRD_screencaptureui_8TAdid/截屏2026-08-15 09.08.57.png`
  - `/var/folders/l_/94l5sj5x5nb9rtwpqw_cfp100000gn/T/TemporaryItems/NSIRD_screencaptureui_Ww45D1/截屏2026-08-15 09.09.08.png`
- Implementation screenshots:
  - `/tmp/oceanpilot-admin-desktop-after.png`
  - `/tmp/oceanpilot-admin-narrow-after.png`
  - `/tmp/oceanpilot-client-material-visible.png`
  - `/tmp/oceanpilot-client-en-independent.png`
  - `/tmp/oceanpilot-admin-en-independent.png`
  - `/tmp/oceanpilot-client-en-status-wrap-final.png`
  - `/tmp/oceanpilot-client-en-status-readable.png`
  - `/tmp/oceanpilot-client-action-buttons-aligned.png`
  - `/tmp/oceanpilot-client-en-evidence-labels.png`
  - `/tmp/oceanpilot-admin-en-status-wrap.png`
- Combined comparison evidence:
  - `/tmp/oceanpilot-brand-comparison.png`
  - `/tmp/oceanpilot-alignment-comparison.png`
  - `/tmp/oceanpilot-i18n-comparison.png`
- Viewports / capture: 1280 × 900 desktop and 660 × 900 narrow-screen states
- State: maintenance overview and merchant diagnosis, both reading the same persisted case store

## Findings

No actionable P0, P1, or P2 mismatch remains.

- Brand fidelity: the maintenance sidebar uses the same supplied Oceanpayment raster wordmark as the merchant workspace. No styled-text reconstruction is used.
- Maintenance alignment: endpoint names and long routes use a `minmax(0, 1fr) auto` grid. Route text wraps inside the card while the state badge remains inside the right edge.
- Merchant alignment: material numbers have an explicit, selector-safe 24 px circular grid and no longer inherit the descriptive-text block rule.
- Responsive behavior: at 660 px both applications report `body.scrollWidth` below `innerWidth`; the maintenance sidebar collapses and card grids stack to one column.
- Information hierarchy: maintenance has a dedicated persisted-case inventory; the customer diagnosis keeps the missing-material count and actions in the primary task area.
- Language fidelity: every visible label, placeholder, status, dynamically rendered record, document title, and accessibility label switches between Chinese and English without a page reload.
- Language isolation: the merchant and maintenance applications use separate preference namespaces. Switching or reloading either application does not change the other application's language.
- English status legibility: full status copy is preserved. Merchant case flags never break inside a word and use balanced word-boundary wrapping only when the action column needs space.
- Action-column consistency: all merchant case actions use the same 118 × 38 px button box; the table header, button box, and label are centered on one axis.
- Evidence-language completeness: all catalog-backed evidence names, including 3DS, AVS, CVV, device/IP, product description, and duplicate checks, use the selected client language in diagnosis, submission actions, and activity text.

The combined comparison frames place each supplied defect screenshot next to the repaired state. They confirm that the badge overflow and material-index drift are resolved, and that the maintenance brand uses the supplied wordmark.

## Interaction verification

- Loaded 20 durable cases from the current SQLite store and confirmed every row can be re-read by case ID.
- Opened a pending case from the merchant case center and verified its three missing-evidence actions render from backend state.
- Opened maintenance `业务指标` and verified the same durable case IDs, reason, phase, missing count, and creation time are shown.
- Confirmed the merchant case center refreshes every five seconds and maintenance overview polling returns the persisted case inventory.
- Checked both browser consoles after interaction; no warnings or errors were emitted.
- Switched only the merchant workspace to English and confirmed the maintenance center remained Chinese; then switched only the maintenance center to English and confirmed the merchant workspace remained Chinese.
- Reloaded both applications with different selected languages and confirmed each application restored its own preference.
- Scanned all rendered text, placeholders, titles, and ARIA labels in both English applications; no untranslated Chinese strings remained.
- Measured every rendered English status badge in both applications; none reported horizontal text overflow. `Assessment complete` remains complete and wraps only between words when needed.
- Measured both `View diagnosis` and `View case` actions; every sampled button reports 118 px width, 38 px height, centered flex alignment, and centered text.
- Reopened the reported unauthorized-transaction case in English and scanned the full rendered diagnosis view; no Chinese text remained in evidence labels, buttons, or activity descriptions.

## Comparison history

The initial maintenance endpoint layout allowed long route strings to push status badges outside their card. The original merchant material selector also applied descriptive-text styles to the numeric marker. Both selector/layout defects were corrected and re-captured at the reported narrow viewport.

## Follow-up polish

- P3: replace the screenshot-derived logo with Oceanpayment's official transparent SVG/PNG asset if the client supplies one.
- P3: connect Oceanpayment's production case API and historical data feed when credentials and field definitions become available; until then the UI truthfully labels only locally persisted, re-readable entities.

final result: passed
