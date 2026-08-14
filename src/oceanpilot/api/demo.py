"""Self-contained single-page console for the chargeback cluster.

Served by FastAPI at ``GET /demo`` (kept out of the OpenAPI schema). Pure inline
HTML + vanilla JS driving the existing JSON API — no build step, no external
assets, works offline. The shell follows Oceanpayment's merchant-console visual
language: white surfaces, operational green, compact navigation, and prominent
case readiness. Deterministic decisions, human confirmation, and synthetic-only
boundaries remain visible without exposing implementation jargon to merchants.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()

_DEMO_HTML = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<script>if(location.hash.includes("figmacapture=")){const s=document.createElement("script");s.src="https://mcp.figma.com/mcp/html-to-design/capture.js";s.async=true;document.head.appendChild(s)}</script>
<title>Oceanpayment · 商户工作台</title>
<style>
  :root{
    --canvas:#f5f6f8; --surface:#ffffff; --sunken:#eef1f5; --border:#e4e8ef; --border-2:#d7dce5;
    --ink:#121722; --body:#39424f; --muted:#6a7280; --faint:#9aa2ae;
    --side:#10151f; --side-2:#0b0f17; --side-ink:#e8ebf1; --side-muted:#8892a2; --side-active:#1a2434; --side-border:#20293a;
    --accent:#1f5fe0; --accent-soft:#e8f0ff;
    --good:#0e9c6b; --good-bg:#e6f5ee; --warn:#b4791c; --warn-bg:#faf1df; --crit:#d14343; --crit-bg:#fbecec;
    --sh:0 1px 2px rgba(18,23,34,.05),0 12px 28px -18px rgba(18,23,34,.18);
    --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
  }
  @media (prefers-color-scheme:dark){:root{
    --canvas:#0b0f16; --surface:#121821; --sunken:#0e141c; --border:#232c39; --border-2:#2c3745;
    --ink:#eef1f6; --body:#b9c2cf; --muted:#8b95a4; --faint:#6b7686; --accent:#5b8bff; --accent-soft:#16233c;
    --good:#34d39e; --good-bg:#0f2a22; --warn:#e0a94a; --warn-bg:#2c2312; --crit:#f0868a; --crit-bg:#2e1719;
  }}
  :root[data-theme="light"]{
    --canvas:#f5f6f8; --surface:#ffffff; --sunken:#eef1f5; --border:#e4e8ef; --border-2:#d7dce5;
    --ink:#121722; --body:#39424f; --muted:#6a7280; --faint:#9aa2ae; --accent:#1f5fe0; --accent-soft:#e8f0ff;
    --good:#0e9c6b; --good-bg:#e6f5ee; --warn:#b4791c; --warn-bg:#faf1df; --crit:#d14343; --crit-bg:#fbecec;
  }
  :root[data-theme="dark"]{
    --canvas:#0b0f16; --surface:#121821; --sunken:#0e141c; --border:#232c39; --border-2:#2c3745;
    --ink:#eef1f6; --body:#b9c2cf; --muted:#8b95a4; --faint:#6b7686; --accent:#5b8bff; --accent-soft:#16233c;
    --good:#34d39e; --good-bg:#0f2a22; --warn:#e0a94a; --warn-bg:#2c2312; --crit:#f0868a; --crit-bg:#2e1719;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--canvas);color:var(--body);font-family:var(--sans);font-size:14px;line-height:1.55;
    -webkit-font-smoothing:antialiased}
  .app{display:grid;grid-template-columns:236px 1fr;min-height:100vh}
  @media(max-width:840px){.app{grid-template-columns:1fr}.side{display:none}}
  a{color:var(--accent)}

  .side{background:var(--side);color:var(--side-ink);display:flex;flex-direction:column;
    border-right:1px solid var(--side-border);position:sticky;top:0;height:100vh}
  .sbrand{display:flex;align-items:center;gap:10px;padding:18px 18px 14px}
  .mark{width:30px;height:30px;border-radius:8px;background:var(--accent);display:grid;place-items:center;color:#fff;font-weight:800;font-size:13px}
  .sbrand .nm{font-weight:700;font-size:14px;color:#fff}
  .sbrand .rl{font-size:11px;color:var(--side-muted)}
  .navlbl{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:#5c6577;padding:12px 15px 6px}
  .nav{padding:6px 8px}
  .nav a{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:8px;color:var(--side-muted);
    text-decoration:none;font-size:13px;cursor:pointer;user-select:none}
  .nav a .ic{width:15px;height:15px;border:1.6px solid currentColor;border-radius:4px;opacity:.7}
  .nav a:hover{color:var(--side-ink);background:var(--side-active)}
  .nav a.on{color:#fff;background:var(--side-active)}
  .nav a.on .ic{background:var(--accent);border-color:var(--accent);opacity:1}
  .main{display:flex;flex-direction:column;min-width:0}
  .top{display:flex;align-items:center;gap:10px;padding:12px 24px;border-bottom:1px solid var(--border);
    background:var(--surface);position:sticky;top:0;z-index:5;flex-wrap:wrap}
  .crumb{font-size:13px;color:var(--muted)} .crumb b{color:var(--ink);font-weight:600}
  .crumb .id{font-family:var(--mono);font-size:12.5px;color:var(--ink)}
  .grow{flex:1}
  .tbtn{border:1px solid var(--border);background:var(--surface);color:var(--body);border-radius:8px;padding:7px 12px;
    font-size:12.5px;cursor:pointer;font-family:var(--sans)}
  .tbtn:hover{border-color:var(--border-2)}
  .tbtn.primary{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
  .tbtn.primary:hover{filter:brightness(1.05)}
  .tbtn.danger{color:var(--crit);border-color:var(--border)}
  .tbtn:disabled{opacity:.45;cursor:not-allowed}

  .howto{margin:16px 24px 0;font-size:12.5px;color:var(--muted);background:var(--accent-soft);
    border:1px solid var(--border);border-radius:10px;padding:10px 14px}
  .howto b{color:var(--accent)}

  .content{padding:18px 24px 30px;display:grid;grid-template-columns:1fr 328px;gap:22px;align-items:start}
  @media(max-width:1080px){.content{grid-template-columns:1fr}}
  .stack{display:flex;flex-direction:column;gap:18px;min-width:0}
  .view{display:none} .view.on{display:grid}

  .summary{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 18px;box-shadow:var(--sh)}
  .srow{display:flex;flex-wrap:wrap;gap:24px}
  .field .k{font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--faint);margin-bottom:3px}
  .field .v{font-size:14px;color:var(--ink);font-weight:600}
  .field .v.mono{font-family:var(--mono);font-weight:500;font-size:13px}
  .num{font-variant-numeric:tabular-nums}
  .pill{display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:6px;font-size:12px;font-weight:600}
  .p-good{background:var(--good-bg);color:var(--good)} .p-warn{background:var(--warn-bg);color:var(--warn)}
  .p-crit{background:var(--crit-bg);color:var(--crit)} .p-mut{background:var(--sunken);color:var(--muted)}
  .p-acc{background:var(--accent-soft);color:var(--accent)}

  .steps{display:flex;align-items:center;flex-wrap:wrap;gap:6px 0;margin-top:16px}
  .step{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--faint)}
  .step .b{width:20px;height:20px;border-radius:50%;border:1.6px solid var(--border-2);display:grid;place-items:center;
    font-size:11px;color:var(--faint);background:var(--surface);font-variant-numeric:tabular-nums}
  .step.done .b{background:var(--accent);border-color:var(--accent);color:#fff}
  .step.now .b{border-color:var(--accent);color:var(--accent)}
  .step.done,.step.now{color:var(--ink);font-weight:600}
  .sep{width:22px;height:1.6px;background:var(--border);margin:0 8px} .sep.done{background:var(--accent)}

  .card{background:var(--surface);border:1px solid var(--border);border-radius:12px;box-shadow:var(--sh)}
  .card .hd{padding:13px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
  .card .hd h3{margin:0;font-size:14px;color:var(--ink);font-weight:700}
  .eyebrow{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint);font-weight:700}
  .bd{padding:16px 18px}

  .verdict{display:flex;gap:24px;align-items:center;flex-wrap:wrap}
  .vnum{font-family:var(--mono);font-size:46px;font-weight:700;line-height:1;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
  .vcap{font-size:12px;color:var(--muted);margin-top:6px}
  .vmeta{flex:1;display:flex;flex-direction:column;gap:10px;min-width:210px}
  .cov{display:flex;align-items:center;gap:10px}
  .track{flex:1;height:7px;border-radius:5px;background:var(--sunken);overflow:hidden}
  .track > i{display:block;height:100%;background:var(--accent)}
  .cov .n{font-family:var(--mono);font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
  .ev{display:grid;grid-template-columns:1fr 1fr;gap:8px 22px;margin-top:16px;border-top:1px solid var(--border);padding-top:14px}
  @media(max-width:560px){.ev{grid-template-columns:1fr}}
  .ei{display:flex;align-items:center;gap:9px;font-size:13px;color:var(--body)}
  .tick{width:18px;height:18px;border-radius:50%;display:grid;place-items:center;font-size:11px;flex:0 0 auto}
  .tick.y{background:var(--good-bg);color:var(--good)} .tick.n{background:var(--sunken);color:var(--faint)}
  .crit-tag{font-size:11px;color:var(--warn);background:var(--warn-bg);padding:0 6px;border-radius:5px}
  .note{margin-top:14px;font-size:13px;color:var(--body);background:var(--sunken);border-radius:8px;padding:11px 13px}
  .note b{color:var(--ink)}
  .actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:16px}

  .rail{display:flex;flex-direction:column;gap:18px;position:sticky;top:74px}
  @media(max-width:1080px){.rail{position:static}}
  .tl{list-style:none;margin:0;padding:0;position:relative}
  .tl:before{content:"";position:absolute;left:5px;top:5px;bottom:6px;width:1.6px;background:var(--border)}
  .tl li{position:relative;padding:0 0 15px 20px}
  .tl li:before{content:"";position:absolute;left:0;top:4px;width:11px;height:11px;border-radius:50%;background:var(--surface);border:2px solid var(--accent)}
  .tl .e{font-size:12.5px;color:var(--ink);font-weight:600}
  .tl .m{font-size:11.5px;color:var(--muted);font-family:var(--mono)}
  .agent{display:flex;gap:9px;padding:9px 0;border-bottom:1px solid var(--border);font-size:12.5px}
  .agent:last-child{border-bottom:0}
  .atag{font-family:var(--mono);font-size:10.5px;color:#fff;background:var(--accent);padding:2px 6px;border-radius:5px;height:fit-content;white-space:nowrap}
  .src{font-size:10.5px;color:var(--faint);font-family:var(--mono)}
  .metrics{display:grid;grid-template-columns:1fr auto;gap:6px 12px;font-family:var(--mono);font-size:12px}
  .metrics .k{color:var(--muted)} .metrics .v{color:var(--ink);font-weight:700;text-align:right;font-variant-numeric:tabular-nums}

  .kv{display:flex;gap:10px;font-size:13px;margin:6px 0} .kv .k{color:var(--muted);min-width:64px}
  .kv code{font-family:var(--mono);font-size:12px;background:var(--sunken);padding:1px 6px;border-radius:5px;word-break:break-all;color:var(--ink)}
  .muted{color:var(--muted);font-size:12.5px} .faint{color:var(--faint)}
  .row{display:flex;gap:9px;flex-wrap:wrap;align-items:center} .mt{margin-top:12px}
  textarea,select,input{width:100%;background:var(--surface);color:var(--ink);border:1px solid var(--border);border-radius:9px;
    padding:10px;font-size:13.5px;font-family:var(--sans)}
  textarea:focus,select:focus,input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
  label.chk{display:inline-flex;align-items:center;gap:7px;color:var(--muted);font-size:12.5px;border:1px solid var(--border);border-radius:8px;padding:8px 11px;cursor:pointer;background:var(--surface)}
  .empty{color:var(--faint);font-size:12.5px}
  .missing-box{margin:12px 0 4px;padding:13px 14px;border:1px solid var(--warn);border-left-width:4px;
    border-radius:9px;background:var(--sunken)}
  .missing-head{display:flex;align-items:center;justify-content:space-between;gap:12px;color:var(--ink);font-weight:700}
  .missing-count{font-family:var(--mono);font-size:12px;color:var(--warn);white-space:nowrap}
  .missing-list{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}
  .missing-item{font-size:12px;color:var(--body);background:var(--surface);border:1px solid var(--border);
    border-radius:999px;padding:4px 9px}
  .missing-item.next{color:var(--warn);border-color:var(--warn);font-weight:700}
  :focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  @media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
  .schips{display:flex;flex-wrap:wrap;gap:8px;margin:2px 0 12px}
  .schip{border:1px solid var(--border);background:var(--surface);color:var(--body);border-radius:999px;
    padding:6px 13px;font-size:12.5px;cursor:pointer;font-family:var(--sans)}
  .schip:hover{border-color:var(--border-2)}
  .schip.on{border-color:var(--accent);color:var(--accent);background:var(--accent-soft);font-weight:600}
  .mstat{margin:0 0 12px}
  .mstat .ml{display:flex;justify-content:space-between;font-size:11.5px;color:var(--muted);margin-bottom:4px}
  .mstat .ml b{color:var(--ink);font-variant-numeric:tabular-nums;font-family:var(--mono);font-weight:600}
  .mbar{height:8px;border-radius:5px;background:var(--sunken);overflow:hidden}
  .mbar > i{display:block;height:100%;background:var(--accent)}
  .mnote{display:grid;grid-template-columns:1fr auto;gap:4px 12px;font-family:var(--mono);font-size:11px;
    color:var(--muted);border-top:1px solid var(--border);padding-top:10px;margin-top:4px}
  .mnote b{color:var(--body);font-weight:600;text-align:right;font-variant-numeric:tabular-nums}

  /* Oceanpayment merchant-console treatment. Kept last so the demo stays a
     single offline file while overriding the earlier generic shell tokens. */
  :root,:root[data-theme="light"],:root[data-theme="dark"]{
    color-scheme:light;
    --canvas:#f5f7f5; --surface:#fff; --sunken:#f1f4f1; --border:#e3e9e4; --border-2:#cfd9d1;
    --ink:#17221b; --body:#3d4a41; --muted:#6d786f; --faint:#929b94;
    --side:#fff; --side-2:#f6f8f6; --side-ink:#17221b; --side-muted:#68726b;
    --side-active:#e9f6ee; --side-border:#e3e9e4;
    --accent:#087a70; --accent-soft:#dff3ef;
    --good:#178a52; --good-bg:#e5f4ec; --warn:#c88722; --warn-bg:#fff4df;
    --crit:#c84646; --crit-bg:#fbeaea; --info:#3676a8; --deep:#123b3a;
    --sh:0 1px 2px rgba(18,59,58,.035),0 8px 20px -16px rgba(18,59,58,.22);
    --sans:ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
  }
  body{font-size:14px;background:var(--canvas)}
  .app{grid-template-columns:220px minmax(0,1fr)}
  .side{box-shadow:none}
  .sbrand{display:block;padding:24px 22px 18px;border-bottom:1px solid var(--side-border)}
  .ocean-name{font-size:20px;font-weight:800;letter-spacing:-.5px;color:var(--accent);line-height:1.1}
  .brand-product{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--side-muted);margin-top:7px}
  .navlbl{color:var(--faint);padding:22px 20px 6px;letter-spacing:.12em}
  .nav{padding:4px 10px}
  .nav a{position:relative;color:var(--side-muted);padding:11px 12px;border-radius:8px;font-size:14px}
  .nav a:hover{color:var(--ink);background:var(--side-2)}
  .nav a.on{color:var(--accent);background:var(--side-active);font-weight:700}
  .nav a.on:before{content:"";position:absolute;left:0;top:10px;bottom:10px;width:3px;border-radius:2px;background:var(--accent)}
  .top{min-height:64px;padding:0 32px;flex-wrap:nowrap;box-shadow:none}
  .crumb-sep{padding:0 7px;color:var(--faint)}
  .tbtn{min-height:34px}
  .tbtn{border-radius:8px}.tbtn.primary{background:var(--accent);border-color:var(--accent)}
  .merchant-account{display:flex;align-items:center;gap:8px;padding-left:14px;margin-left:2px;border-left:1px solid var(--border);white-space:nowrap}
  .merchant-account span{font-size:11px;color:var(--faint)} .merchant-account strong{font-size:13px;color:var(--ink);font-weight:650}
  .content{width:100%;max-width:1440px;margin:0 auto;padding:28px 32px 40px;
    grid-template-columns:minmax(0,1fr) 320px;gap:20px}
  #v-prev,#v-safe{grid-template-columns:1fr} #v-prev .stack,#v-safe .stack{width:100%;max-width:920px}
  .page-head{grid-column:1/-1;display:flex;align-items:flex-end;justify-content:space-between;gap:24px;
    margin-bottom:2px;padding-bottom:18px;border-bottom:1px solid var(--border)}
  .page-head h1{margin:3px 0 4px;color:var(--ink);font-size:25px;line-height:1.25;letter-spacing:-.02em}
  .page-head p{margin:0;color:var(--muted);font-size:13.5px}
  .stack,.rail{gap:16px}.rail{top:80px}
  .summary,.card{border-radius:10px;box-shadow:var(--sh)}
  .summary{padding:18px 20px}.card .hd{padding:13px 18px}.bd{padding:18px}
  .eyebrow{letter-spacing:.1em}.srow{gap:18px 30px}
  .field .k{letter-spacing:.02em;text-transform:none}.field .v{font-size:13.5px}
  .pill{border-radius:5px}.step.done .b{background:var(--accent);border-color:var(--accent)}
  .scenario-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:10px 0 14px}
  .scenario-card{display:flex;flex-direction:column;align-items:flex-start;gap:4px;text-align:left;min-height:72px;
    padding:12px 13px;border:1px solid var(--border);border-radius:8px;background:var(--surface);cursor:pointer;
    color:var(--body);font-family:var(--sans)}
  .scenario-card strong{color:var(--ink);font-size:13px}.scenario-card span{font-size:11.5px;color:var(--muted)}
  .scenario-card:hover{border-color:var(--border-2);background:var(--side-2)}
  .scenario-card.on{border-color:var(--accent);background:var(--accent-soft)}
  .scenario-card.on strong{color:var(--accent)}
  .risk-form{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
  .risk-form .chk{justify-content:flex-start}.amount-field{grid-column:1/3;color:var(--muted);font-size:12px}
  .amount-field span{display:block;margin-bottom:5px}.risk-form .tbtn{align-self:end;height:41px}
  .missing-box{background:var(--warn-bg);border-color:#ddb66d;padding:15px 16px}
  .missing-item{border-radius:6px}.missing-item.next{background:#fff9ed}
  .note{line-height:1.65}.agent{align-items:flex-start}.atag{background:var(--accent-soft);color:var(--accent);font-family:var(--sans);font-weight:700}
  @media(max-width:1080px){.content{grid-template-columns:1fr}.page-head{grid-column:1}.rail{position:static}}
  @media(max-width:840px){.app{grid-template-columns:1fr}.side{display:none}.content{padding:22px 20px 32px}.top{padding:0 20px}}
  @media(max-width:600px){.content{padding:18px 14px 28px}.top{padding:0 14px}.top .tbtn{padding:7px 9px}.merchant-account{display:none}
    .page-head{align-items:flex-start}.scenario-grid,.risk-form{grid-template-columns:1fr}.amount-field{grid-column:1}.steps{overflow-x:auto;flex-wrap:nowrap;padding-bottom:4px}.step{white-space:nowrap}.sep{min-width:12px;margin:0 4px}}

  /* Transaction Diagnostic System */
  .global-search{position:relative;width:min(420px,34vw)}
  .global-search input{height:38px;padding:8px 58px 8px 35px;border-radius:8px;background:var(--canvas)}
  .global-search:before{content:"";position:absolute;left:13px;top:12px;width:11px;height:11px;border:1.5px solid var(--muted);border-radius:50%;z-index:1}
  .global-search:after{content:"";position:absolute;left:23px;top:23px;width:6px;height:1.5px;background:var(--muted);transform:rotate(45deg);z-index:1}
  .shortcut{position:absolute;right:8px;top:8px;color:var(--muted);font:11px var(--mono);border:1px solid var(--border);border-radius:5px;padding:2px 5px;background:var(--surface)}
  .env-chip{font-size:11px;font-weight:700;color:var(--accent);background:var(--accent-soft);border:1px solid #b8ddd6;border-radius:5px;padding:4px 8px}
  .avatar{width:30px;height:30px;border-radius:50%;background:var(--deep);color:#fff;display:grid;place-items:center;font-size:11px;font-weight:750}
  .content.full{max-width:1440px}.content.full.view{display:none}.content.full.view.on{display:block}.content.full .page-head{display:flex}
  .metric-strip{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));border:1px solid var(--border);border-radius:10px;background:var(--surface);overflow:hidden;margin-bottom:16px}
  .metric-cell{padding:14px 16px;border-right:1px solid var(--border)}.metric-cell:last-child{border-right:0}
  .metric-label{font-size:11.5px;color:var(--muted)}.metric-value{font:700 22px/1.3 var(--sans);color:var(--ink);font-variant-numeric:tabular-nums;margin-top:4px}.metric-delta{font-size:11px;color:var(--muted);margin-top:2px}.down{color:var(--crit)}.up{color:var(--good)}
  .ops-grid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(320px,.8fr);gap:16px}.panel{background:var(--surface);border:1px solid var(--border);border-radius:10px}.panel-hd{height:48px;padding:0 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}.panel-hd h2{font-size:14px;color:var(--ink);margin:0}.panel-bd{padding:16px}
  .segmented{display:flex;gap:2px;background:var(--sunken);padding:2px;border-radius:6px}.segmented button{border:0;background:transparent;padding:5px 8px;border-radius:4px;color:var(--muted);font-size:11px}.segmented button.on{background:var(--surface);color:var(--ink);box-shadow:0 1px 2px rgba(0,0,0,.06)}
  .chart{height:224px;display:flex;align-items:flex-end;gap:7px;padding:18px 6px 26px;border-bottom:1px solid var(--border);position:relative}.chart:before,.chart:after{content:"";position:absolute;left:0;right:0;height:1px;background:var(--border)}.chart:before{top:34%}.chart:after{top:66%}.bar{flex:1;background:#9fd7cf;border-radius:3px 3px 0 0;min-width:8px;z-index:1}.bar.fail{background:#d9e6e3}.chart-caption{display:flex;justify-content:space-between;color:var(--muted);font-size:10px;margin-top:8px}
  .attention{padding:0}.attention-row{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:center;padding:13px 16px;border-bottom:1px solid var(--border);cursor:pointer}.attention-row:last-child{border-bottom:0}.attention-row:hover{background:var(--canvas)}.attention-row strong{font-size:12.5px;color:var(--ink)}.attention-row p{font-size:11.5px;color:var(--muted);margin:2px 0 0}.count{font:700 13px var(--mono);color:var(--ink)}
  .status-dot{width:8px;height:8px;border-radius:50%;background:var(--good)}.status-dot.warn{background:var(--warn)}.status-dot.crit{background:var(--crit)}
  .table-tools{display:flex;gap:8px;align-items:center;margin-bottom:12px}.table-tools input,.table-tools select{width:auto;height:36px;padding:7px 10px}.table-tools input{min-width:240px}.op-table{width:100%;border-collapse:collapse;background:var(--surface);border:1px solid var(--border);border-radius:10px;overflow:hidden}.op-table th{background:#f0f5f3;color:var(--muted);font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;text-align:left;padding:10px 12px;border-bottom:1px solid var(--border);white-space:nowrap}.op-table td{padding:11px 12px;border-bottom:1px solid var(--border);font-size:12px;color:var(--body);white-space:nowrap}.op-table tbody tr{cursor:pointer}.op-table tbody tr:hover{background:#f7faf9}.op-table tbody tr:last-child td{border-bottom:0}.op-table .primary-id{font:600 12px var(--mono);color:var(--accent)}
  .op-table .sub-id{font:10.5px var(--mono);color:var(--muted);margin-top:3px}.op-table .stage-code{font-size:11.5px;color:var(--body)}.op-table .stage-code code{display:block;margin-top:3px;color:var(--muted);background:transparent;padding:0}.op-table .action-cell{width:1%;white-space:nowrap}
  .diag-layout{display:grid;grid-template-columns:minmax(0,1.45fr) 350px;gap:16px}.diag-result{border-top:3px solid var(--crit)}.diag-hero{display:grid;grid-template-columns:1fr auto;gap:20px}.diag-title{font-size:20px;line-height:1.35;color:var(--ink);font-weight:750}.confidence{min-width:112px;text-align:right}.confidence strong{display:block;font:750 30px var(--mono);color:var(--ink)}.confidence span{font-size:11px;color:var(--muted)}
  .fact-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:0;border:1px solid var(--border);border-radius:8px;margin:15px 0;overflow:hidden}.fact{padding:11px 12px;border-right:1px solid var(--border)}.fact:last-child{border-right:0}.fact span{display:block;color:var(--muted);font-size:10.5px}.fact strong{display:block;color:var(--ink);font-size:12px;margin-top:2px}
  .path{display:flex;align-items:center;gap:0;overflow-x:auto;padding:6px 0}.path-node{min-width:108px;border:1px solid var(--border);border-radius:7px;padding:9px 10px;background:var(--surface)}.path-node strong{display:block;color:var(--ink);font-size:11.5px}.path-node span{font-size:10.5px;color:var(--muted)}.path-node.bad{border-color:#e1a0a0;background:var(--crit-bg)}.path-link{height:1px;min-width:25px;background:var(--border2)}
  .triad{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px}.triad-item{border:1px solid var(--border);border-radius:8px;padding:12px}.triad-item h4{font-size:11px;color:var(--muted);margin:0 0 7px;text-transform:uppercase;letter-spacing:.05em}.triad-item p{font-size:12px;color:var(--body);margin:0;line-height:1.6}.triad-item.actionable{background:var(--accent-soft);border-color:#b8ddd6}.evidence-line{display:flex;gap:9px;padding:10px 0;border-bottom:1px solid var(--border);font-size:12px}.evidence-line:last-child{border:0}.evidence-line b{color:var(--ink)}.evidence-line span{color:var(--muted)}
  .customer-alert{border:1px solid #e3bd76;border-left:4px solid var(--warn);background:var(--warn-bg);border-radius:8px;padding:13px 14px;margin-bottom:14px}.customer-alert strong{display:block;color:#765115}.customer-alert p{margin:4px 0 0;color:#85632d;font-size:12px}
  .secondary-nav{margin-top:auto;border-top:1px solid var(--side-border);padding:10px}.secondary-nav a{font-size:12px}
  .task-guide{display:grid;grid-template-columns:repeat(3,1fr);gap:0;background:var(--surface);border:1px solid var(--border);border-radius:10px;margin-bottom:16px;overflow:hidden}
  .guide-step{display:grid;grid-template-columns:30px 1fr;gap:10px;padding:15px 16px;border-right:1px solid var(--border)}.guide-step:last-child{border-right:0}
  .guide-no{width:26px;height:26px;border-radius:50%;display:grid;place-items:center;background:var(--accent-soft);color:var(--accent);font-weight:750}
  .guide-step strong{display:block;color:var(--ink);font-size:13px}.guide-step span{display:block;color:var(--muted);font-size:11.5px;margin-top:2px}
  .work-grid{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:16px}.work-aside{display:flex;flex-direction:column;gap:16px}
  .quick-row{padding:14px 16px;border-bottom:1px solid var(--border)}.quick-row:last-child{border-bottom:0}.quick-row strong{display:block;color:var(--ink);font-size:13px}.quick-row p{margin:3px 0 9px;color:var(--muted);font-size:11.5px}
  .diag-layout.clear{grid-template-columns:minmax(0,1fr) 300px}.diag-result{border-top:0}.diagnosis-summary{border-left:4px solid var(--crit)}
  .diagnosis-summary.good{border-left-color:var(--good)}.diagnosis-summary.warn{border-left-color:var(--warn)}
  .diagnosis-kicker{color:var(--muted);font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}.diagnosis-title{font-size:22px;line-height:1.35;color:var(--ink);font-weight:760;margin:5px 0 8px}.diagnosis-copy{font-size:13px;line-height:1.7;color:var(--body);margin:0}
  .next-action{margin-top:16px;padding:14px 15px;border-radius:8px;background:var(--accent-soft);border:1px solid #b8ddd6}.next-action strong{display:block;color:var(--accent);font-size:13px}.next-action p{margin:4px 0 0;color:var(--body);font-size:12.5px}
  .missing-checklist{display:flex;flex-direction:column;gap:8px;margin-top:10px}.missing-row{display:flex;align-items:center;gap:10px;background:var(--surface);border:1px solid var(--border);border-radius:7px;padding:9px 10px;color:var(--body);font-size:12.5px}.missing-row.next{border-color:#ddb66d;background:#fffaf0;font-weight:700;color:#765115}.missing-row .box{width:18px;height:18px;border:1.5px solid currentColor;border-radius:4px;display:grid;place-items:center;font-size:10px;flex:0 0 auto}
  .source-case{margin:0 0 14px;padding:12px 13px;background:var(--accent-soft);border:1px solid #b8ddd6;border-radius:8px}.source-case strong{display:block;color:var(--accent);font-size:12.5px}.source-case span{display:block;color:var(--body);font:11.5px var(--mono);margin-top:3px}
  .field-label{display:block;color:var(--ink);font-size:12px;font-weight:700;margin:12px 0 6px}.helper{font-size:11.5px;color:var(--muted);margin-top:7px}.technical{border-top:1px solid var(--border);margin-top:16px;padding-top:12px}.technical summary{cursor:pointer;color:var(--accent);font-size:12.5px;font-weight:700}.technical[open] summary{margin-bottom:12px}
  .case-records{margin-top:0}.case-records summary{cursor:pointer;color:var(--body);font-weight:700}.case-records .record-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:14px}
  @media(max-width:1180px){.metric-strip{grid-template-columns:repeat(3,1fr)}.metric-cell:nth-child(3){border-right:0}.metric-cell:nth-child(-n+3){border-bottom:1px solid var(--border)}.ops-grid,.diag-layout{grid-template-columns:1fr}.diag-layout>.rail{display:none}}
  @media(max-width:1180px){.work-grid,.diag-layout.clear{grid-template-columns:1fr}.work-aside{display:grid;grid-template-columns:1fr 1fr}}
  @media(max-width:840px){.global-search{width:100%}.top{height:auto;padding:10px 14px;flex-wrap:wrap}.metric-strip{grid-template-columns:repeat(2,1fr)}.metric-cell{border-bottom:1px solid var(--border)}.fact-grid,.triad,.task-guide{grid-template-columns:1fr}.guide-step{border-right:0;border-bottom:1px solid var(--border)}.guide-step:last-child{border-bottom:0}.work-aside,.case-records .record-grid{grid-template-columns:1fr}.fact{border-right:0;border-bottom:1px solid var(--border)}}
</style>
</head>
<body>
<div class="app">
  <aside class="side">
    <div class="sbrand">
      <div class="ocean-name">Oceanpayment</div>
      <div class="brand-product">交易诊断系统</div>
    </div>
    <div class="navlbl">工作台</div>
    <nav class="nav">
      <a class="on" data-v="overview">交易与诊断</a>
      <a data-v="flow">案件中心</a>
      <a data-v="prev">交易风险</a>
    </nav>
  </aside>

  <div class="main">
    <div class="top">
      <div class="crumb"><b id="crumbRoot">商户工作台</b><span class="crumb-sep">/</span><span id="crumbId" class="id">交易与诊断</span></div>
      <div class="grow"></div>
      <div class="global-search"><input id="globalSearch" placeholder="搜索 Payment ID、订单号、商户" autocomplete="off"><span class="shortcut">⌘K</span></div>
      <div class="merchant-account"><span>商户</span><strong>OceanStore</strong></div>
    </div>

    <!-- 交易与诊断工作台 -->
    <div class="content full view on" id="v-overview">
      <div class="page-head"><div><div class="eyebrow">Merchant workspace</div><h1>交易与诊断</h1><p>查找一笔交易，查看处理原因；客户提出争议时，再创建案件并补齐材料。</p></div><button class="tbtn primary" onclick="focusTransactionSearch()">查找交易</button></div>
      <div class="task-guide" aria-label="使用步骤">
        <div class="guide-step"><span class="guide-no">1</span><div><strong>查找交易</strong><span>输入 Payment ID、订单号或商户</span></div></div>
        <div class="guide-step"><span class="guide-no">2</span><div><strong>查看诊断</strong><span>点击交易，确认发生了什么和下一步</span></div></div>
        <div class="guide-step"><span class="guide-no">3</span><div><strong>创建并补全案件</strong><span>系统会逐项列出仍缺的材料</span></div></div>
      </div>
      <div class="work-grid">
        <section class="panel"><div class="panel-hd"><h2>最近交易</h2><div class="grow"></div><span class="muted" id="transactionCount">共 6 笔</span></div><div class="panel-bd">
          <div class="table-tools"><input id="tableSearch" placeholder="Payment ID、订单号或商户"><select id="statusFilter"><option value="ALL">全部状态</option><option value="FAILED">只看失败</option><option value="SUCCESS">只看成功</option><option value="PENDING">只看处理中</option></select></div>
          <div style="overflow:auto"><table class="op-table"><thead><tr><th>交易</th><th>金额</th><th>状态</th><th>当前节点</th><th>操作</th></tr></thead><tbody id="transactionRows"></tbody></table></div>
        </div></section>
        <aside class="work-aside">
          <section class="panel"><div class="panel-hd"><h2>需要处理</h2><span class="pill p-warn">2 项</span></div><div class="quick-row"><strong>案件材料待补全</strong><p>系统会按优先级提示下一项材料。</p><button class="tbtn" onclick="showView('flow')">进入案件中心</button></div><div class="quick-row"><strong>授权状态待核对</strong><p>1 笔交易不应立即重复扣款。</p><button class="tbtn" onclick="openTransaction('OP-20260814-7156')">查看交易</button></div></section>
          <section class="panel"><div class="panel-hd"><h2>创建案件</h2></div><div class="panel-bd"><p class="muted" style="margin-top:0">已有 Payment ID 时，先查交易再建案；没有时可直接填写案件说明。</p><button class="tbtn primary" onclick="reset(null)">手动创建案件</button></div></section>
        </aside>
      </div>
    </div>

    <!-- 交易诊断 -->
    <div class="content full view" id="v-diagnosis">
      <div class="page-head"><div><div class="eyebrow">Transaction diagnosis</div><h1>交易诊断</h1><p>先看结论和下一步；技术证据可按需展开。</p></div><button class="tbtn" onclick="showView('overview')">返回交易列表</button></div>
      <div class="diag-layout clear"><div class="stack">
        <section class="panel diagnosis-summary" id="diagnosisSummary"><div class="panel-hd"><h2>发生了什么</h2><div class="grow"></div><span class="pill p-crit" id="diagStatus">支付失败</span></div><div class="panel-bd">
          <div class="diagnosis-kicker">诊断结论</div><div class="diagnosis-title" id="diagCause">3DS 挑战未完成，发卡行拒绝授权</div><p class="diagnosis-copy" id="diagMeaning">失败发生在持卡人验证阶段，授权尚未发起，不是重复扣款。</p>
          <div class="fact-grid"><div class="fact"><span>Payment ID</span><strong id="diagId">OP-20260814-8421</strong></div><div class="fact"><span>响应码</span><strong id="diagCode">3DS-201</strong></div><div class="fact"><span>失败阶段</span><strong id="diagStage">3DS Challenge</strong></div><div class="fact"><span>影响</span><strong id="diagImpact">授权未发起</strong></div></div>
          <div class="next-action"><strong>建议下一步</strong><p id="diagAdvice">请客户重新支付并保持验证窗口；若持续出现，再检查 3DS 回调域名。</p></div>
          <div class="actions"><button class="tbtn primary" onclick="startCaseFromDiagnosis()">客户提出争议，创建案件</button><button class="tbtn" onclick="showView('overview')">查看其他交易</button></div><div class="helper">支付失败不会自动建案；只有客户提出争议或需要提交材料时才创建案件。</div>
          <details class="technical"><summary>查看处理路径与技术证据</summary><div class="path"><div class="path-node"><strong>Checkout</strong><span>请求已接收</span></div><i class="path-link"></i><div class="path-node"><strong>Risk Check</strong><span>通过</span></div><i class="path-link"></i><div class="path-node bad"><strong>3DS Challenge</strong><span>超时 / 未完成</span></div><i class="path-link"></i><div class="path-node"><strong>Authorization</strong><span>未执行</span></div><i class="path-link"></i><div class="path-node"><strong>Capture</strong><span>未执行</span></div></div><div class="triad"><div class="triad-item"><h4>Observed facts</h4><p>challenge_status=timeout；浏览器回调缺失；授权请求未生成。</p></div><div class="triad-item"><h4>System interpretation</h4><p>失败发生在持卡人验证阶段，不是余额不足或商户配置拒绝。</p></div><div class="triad-item actionable"><h4>Recommended action</h4><p>引导客户重新支付并保持验证窗口；若持续出现，检查 3DS 回调域名。</p></div></div></details>
        </div></section>
      </div><aside class="work-aside"><div class="customer-alert" id="diagnosisAlert"><strong>需要商户补充 2 项信息</strong><p>持卡人账单地址、设备 IP 归属。补全后可继续复核路由异常。</p></div><section class="panel"><div class="panel-hd"><h2>如何创建和补全案件</h2></div><div class="panel-bd"><div class="guide-step" style="padding:0 0 12px;border:0"><span class="guide-no">1</span><div><strong>创建案件</strong><span>带入当前 Payment ID 并选择争议类型</span></div></div><div class="guide-step" style="padding:12px 0;border:0;border-top:1px solid var(--border)"><span class="guide-no">2</span><div><strong>查看缺口</strong><span>系统会明确显示还缺几项、下一项是什么</span></div></div><div class="guide-step" style="padding:12px 0 0;border:0;border-top:1px solid var(--border)"><span class="guide-no">3</span><div><strong>逐项补交</strong><span>每补一项都会自动重新检查</span></div></div></div></section></aside></div>
    </div>

    <!-- 拒付处理 -->
    <div class="content view" id="v-flow">
      <div class="page-head"><div><h1>案件中心</h1>
        <p>创建案件后，系统会按优先级列出缺失材料，并引导你逐项补全。</p></div><button class="tbtn" onclick="reset(null)">新建案件</button></div>
      <div class="stack">
        <div class="summary">
          <div id="caseHead"><span class="empty">尚未创建案件 · 请在下方选择争议类型。</span></div>
          <div class="steps" id="steps"></div>
        </div>
        <div class="card">
          <div class="hd"><h3>案件处理</h3><span class="eyebrow" id="phaseTag">创建案件</span></div>
          <div class="bd" id="action"></div>
        </div>
        <div class="card" id="verdictCard" style="display:none">
          <div class="hd"><h3>材料就绪评估</h3><span class="eyebrow">规则评估</span></div>
          <div class="bd" id="verdictBody"></div>
        </div>
        <details class="card case-records"><summary class="hd">查看案件处理记录</summary><div class="bd record-grid"><div><h3>处理记录</h3><ul class="tl" id="auditOut"><li class="empty">建案后自动记录。</li></ul></div><div><h3>判断依据</h3><div id="agentOut"><div class="empty">—</div></div></div></div></details>
      </div>
      <div class="rail"></div>
    </div>

    <!-- 交易前预防 -->
    <div class="content view" id="v-prev">
      <div class="page-head"><div><h1>交易预警</h1>
        <p>在交易完成前识别拒付风险，并提示应提前留存的材料。</p></div></div>
      <div class="stack"><div class="card">
        <div class="hd"><h3>交易信息</h3><span class="eyebrow">实时评估</span></div>
        <div class="bd">
          <div class="risk-form">
            <label class="chk"><input type="checkbox" id="p_no3ds" style="width:auto"> 未完成 3DS</label>
            <label class="chk"><input type="checkbox" id="p_noavs" style="width:auto"> AVS 地址不匹配</label>
            <label class="chk"><input type="checkbox" id="p_cross" style="width:auto"> 跨境交易</label>
            <label class="amount-field"><span>交易金额</span><input id="p_amount" placeholder="例如 4200"></label>
            <button class="tbtn primary" onclick="assessPrevention()">开始评估</button>
          </div>
          <div id="preventionOut" class="mt"></div>
        </div>
      </div></div>
      <div class="rail"></div>
    </div>

    <!-- 安全与指标 -->
    <div class="content view" id="v-safe">
      <div class="page-head"><div><h1>规则与运营</h1>
        <p>查看信息安全拦截和案件处理概览，确认系统始终在授权边界内运行。</p></div></div>
      <div class="stack">
        <div class="card">
          <div class="hd"><h3>敏感信息检查</h3><span class="eyebrow">卡号不入库</span></div>
          <div class="bd">
            <input type="text" id="safeText" value="请退款到卡号 4111 1111 1111 1111">
            <div class="actions"><button class="tbtn primary" onclick="safetyScan()">检查内容</button>
              <span class="muted">检测到卡号后立即阻断，结果不会回显原文。</span></div>
            <div id="safeOut" class="mt"></div>
          </div>
        </div>
        <div class="card">
          <div class="hd"><h3>案件概览</h3><span class="eyebrow">本次演示</span></div>
          <div class="bd" id="metricsOut"><span class="empty">—</span></div>
        </div>
      </div>
      <div class="rail"></div>
    </div>
  </div>
</div>

<script>
const BASE="/api/v1/chargeback";
const S={caseId:null,loc:"zh",packaged:false,appealed:false,last:null,cardNetwork:"VISA",
  scenarioIndex:0,autoEvidence:["transaction.receipt","fulfillment.tracking"],selectedTransaction:null,sourceTransaction:null};
const SCENARIOS=[
  {label:"Visa 13.1 · 未收到货",meta:"已有 2 项 · 仍缺 3 项",network:"VISA",
    available:["transaction.receipt","fulfillment.tracking"],
    desc:"客户声称未收到商品；商户目前只有交易收据和物流轨迹，尚未取得签收证明、地址匹配及客服沟通。"},
  {label:"Visa 10.4 · 非本人交易",meta:"已有 1 项 · 仍缺 5 项",network:"VISA",available:["transaction.receipt"],
    desc:"持卡人声称这笔交易不是本人、属于盗刷；商户目前只有交易收据，缺少 3DS、AVS/CVV、设备/IP 和历史交易关联。"},
  {label:"Mastercard 4853 · 商品不符",meta:"已有 2 项 · 仍缺 3 项",network:"MASTERCARD",
    available:["transaction.receipt","product.description"],
    desc:"客户声称收到的商品与下单页面描述不符；商户目前只有交易收据和商品页面，缺少签收、沟通和政策材料。"},
];
const TRANSACTIONS=[
  {id:"OP-20260814-8421",order:"ORD-908421",merchant:"OceanStore",amount:"EUR 238.00",status:"FAILED",method:"Visa •••• 1842",stage:"3DS Challenge",code:"3DS-201",time:"20:46:08"},
  {id:"OP-20260814-8399",order:"ORD-908399",merchant:"OceanStore",amount:"USD 86.40",status:"SUCCESS",method:"Mastercard •••• 6091",stage:"Capture",code:"00",time:"20:43:21"},
  {id:"OP-20260814-8338",order:"ORD-908338",merchant:"North Peak",amount:"EUR 419.00",status:"FAILED",method:"Visa •••• 3380",stage:"3DS Challenge",code:"3DS-201",time:"20:37:12"},
  {id:"OP-20260814-8280",order:"ORD-908280",merchant:"OceanStore",amount:"GBP 52.90",status:"PENDING",method:"Apple Pay",stage:"Authorization",code:"—",time:"20:31:57"},
  {id:"OP-20260814-7156",order:"ORD-907156",merchant:"Luma Market",amount:"USD 1,420.00",status:"FAILED",method:"Mastercard •••• 0517",stage:"Authorization",code:"91",time:"19:18:44"},
  {id:"OP-20260814-7024",order:"ORD-907024",merchant:"OceanStore",amount:"USD 132.00",status:"SUCCESS",method:"Visa •••• 7288",stage:"Capture",code:"00",time:"19:04:18"},
];
const PHASE={NEEDS_INTAKE:["未建案","p-mut","创建案件"],REASON_PROPOSED:["待确认原因","p-warn","确认原因"],
  NEED_EVIDENCE:["补充材料","p-acc","补充材料"],ASSESSED:["评估完成","p-good","评估结果"]};
const REASON_LABEL={FRAUD_CARD_NOT_PRESENT:"非本人交易",PRODUCT_NOT_RECEIVED:"未收到商品",
  PRODUCT_NOT_AS_DESCRIBED:"商品或服务与描述不符",DUPLICATE_PROCESSING:"重复扣款",
  CREDIT_NOT_PROCESSED:"退款未入账",SUBSCRIPTION_CANCELED:"订阅取消后仍扣款",AUTHORIZATION_ERROR:"授权异常"};
const TEAM_LABEL={RISK:"风控团队",CUSTOMER_SUPPORT:"客服团队",BUSINESS:"业务团队",
  TECHNICAL_SUPPORT:"技术支持",FINANCE:"财务团队",PSP_SUPPORT:"支付支持"};
const AGENT_LABEL={IntakeAgent:"案件识别",EvidenceAgent:"材料校验",AssessAgent:"规则评估",HumanGate:"人工确认"};
const SOURCE_LABEL={MODEL:"辅助说明",FALLBACK:"规则说明",HEURISTIC:"规则识别"};
const EVENT_LABEL={CASE_OPENED:"案件创建",REASON_CLASSIFIED:"争议原因识别",REASON_CONFIRMED:"争议原因确认",
  EVIDENCE_ADDED:"材料已补充",COLLECTION_FINALIZED:"材料收集结束"};
const RISK_LABEL={LOW:"低风险",MEDIUM:"中风险",HIGH:"高风险"};
const FACTOR_LABEL={NO_3DS:"未完成 3DS",AVS_MISMATCH:"AVS 地址不匹配",CVV_MISMATCH:"CVV 不匹配",
  DEVICE_IP_MISMATCH:"设备与 IP 异常",HIGH_TICKET:"高额交易",HIGH_RISK_MCC:"高风险行业",
  CROSS_BORDER:"跨境交易",SHIPPING_BILLING_MISMATCH:"收货与账单地址不符",REPEAT_DISPUTER:"历史争议较多",DIGITAL_GOODS:"数字商品"};
const EVIDENCE_LABEL={"transaction.receipt":"交易收据","auth.avs_result":"AVS 验证结果","auth.cvv_result":"CVV 验证结果",
  "auth.threeds":"3DS 认证记录","auth.device_ip_match":"设备与 IP 关联","fulfillment.tracking":"物流跟踪号/轨迹",
  "fulfillment.proof_of_delivery":"签收证明","fulfillment.address_match":"收货地址匹配","product.description":"商品页面",
  "billing.refund_record":"退款记录","policy.terms_refund":"条款与退款政策","comms.customer":"客户沟通记录",
  "subscription.cancellation_record":"取消订阅记录","history.prior_transactions":"历史交易记录","billing.duplicate_check":"重复扣款核验"};
const $=(id)=>document.getElementById(id);
const esc=(s)=>String(s==null?"":s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const cleanCopy=(s)=>String(s||"").replace(/（合成模型输出，仅用于离线演示）/g,"").trim();
const actionLabel=(s)=>cleanCopy(s).replace(/胜诉评估 ([0-9.]+)（数字由内核判定）/,"材料就绪度 $1（规则评估）");
const detailLabel=(s)=>REASON_LABEL[s]||EVIDENCE_LABEL[s]||s;
async function api(m,p,b){const o={method:m,headers:{'Content-Type':'application/json'}};
  if(b!==undefined)o.body=JSON.stringify(b);
  const r=await fetch(BASE+p,o);return{ok:r.ok,status:r.status,data:await r.json().catch(()=>({}))};}

const STATUS_VIEW={FAILED:['失败','p-crit'],SUCCESS:['成功','p-good'],PENDING:['处理中','p-warn']};
function showView(v){
  if(v==='transactions')v='overview';
  const navView=v==='diagnosis'?'overview':v;
  document.querySelectorAll('.nav a').forEach(x=>x.classList.toggle('on',x.dataset.v===navView));
  document.querySelectorAll('.view').forEach(x=>x.classList.remove('on'));
  const view=$('v-'+v);if(view)view.classList.add('on');
  const navCrumb={overview:["商户工作台","交易与诊断"],diagnosis:["交易与诊断","诊断结果"],flow:["案件中心",S.caseId?S.caseId.slice(0,18):"新建案件"],prev:["交易风险","实时评估"],safe:["系统管理","安全检查"]}[v]||["商户工作台",v];
  $('crumbRoot').textContent=navCrumb[0];$('crumbId').textContent=navCrumb[1];
}
document.querySelectorAll('.nav a').forEach(a=>a.addEventListener('click',()=>showView(a.dataset.v)));
function renderTransactions(){const query=($('tableSearch').value||'').toLowerCase();const status=$('statusFilter').value;
  const rows=TRANSACTIONS.filter(t=>(status==='ALL'||t.status===status)&&Object.values(t).join(' ').toLowerCase().includes(query));
  $('transactionCount').textContent=`共 ${rows.length} 笔`;
  $('transactionRows').innerHTML=rows.map(t=>{const s=STATUS_VIEW[t.status];return `<tr onclick="openTransaction('${t.id}')"><td class="primary-id">${esc(t.id)}<div class="sub-id">${esc(t.order)}</div></td><td class="num">${esc(t.amount)}</td><td><span class="pill ${s[1]}">${s[0]}</span></td><td class="stage-code">${esc(t.stage)}<code>${esc(t.code)}</code></td><td class="action-cell"><button class="tbtn" onclick="event.stopPropagation();openTransaction('${t.id}')">查看诊断</button></td></tr>`;}).join('')||'<tr><td colspan="5" class="empty">没有匹配的交易</td></tr>';}
function openTransaction(id){const t=TRANSACTIONS.find(x=>x.id===id)||TRANSACTIONS[0];
  S.selectedTransaction=t;
  $('diagId').textContent=t.id;$('diagStage').textContent=t.stage;$('diagCode').textContent=t.code;
  const summary=$('diagnosisSummary');const status=$('diagStatus');
  if(t.code==='91'){$('diagCause').textContent='收单通道未及时响应，授权状态仍待核对';$('diagImpact').textContent='不要重复扣款';$('diagMeaning').textContent='上游没有在时限内返回最终状态，目前不能判断授权成功或失败。';$('diagAdvice').textContent='先使用 Payment ID 查询上游最终状态；确认失败后再引导客户重试。';$('diagnosisAlert').innerHTML='<strong>现在不需要补材料</strong><p>请先核对授权状态，避免产生重复扣款。</p>';summary.className='panel diagnosis-summary warn';status.className='pill p-warn';status.textContent='状态待核对';}
  else if(t.status==='SUCCESS'){$('diagCause').textContent='交易处理完成，未发现支付异常';$('diagImpact').textContent='已成功入账';$('diagMeaning').textContent='授权与请款链路完整；如果客户对商品或交易提出异议，可基于这笔交易创建案件。';$('diagAdvice').textContent='无需处理支付链路。只有收到客户争议时，才创建案件并收集对应材料。';$('diagnosisAlert').innerHTML='<strong>当前无需补充信息</strong><p>交易链路完整；创建案件后，系统会按争议类型列出材料缺口。</p>';summary.className='panel diagnosis-summary good';status.className='pill p-good';status.textContent='支付成功';}
  else{$('diagCause').textContent='3DS 挑战未完成，发卡行拒绝授权';$('diagImpact').textContent='授权未发起';$('diagMeaning').textContent='失败发生在持卡人验证阶段，授权尚未发起，不是重复扣款。';$('diagAdvice').textContent='请客户重新支付并保持验证窗口；若持续出现，再检查 3DS 回调域名。';$('diagnosisAlert').innerHTML='<strong>需要商户补充 2 项信息</strong><p>持卡人账单地址、设备 IP 归属。补全后可继续复核路由异常。</p>';summary.className='panel diagnosis-summary';status.className='pill p-crit';status.textContent='支付失败';}
  showView('diagnosis');}
$('tableSearch').addEventListener('input',renderTransactions);$('statusFilter').addEventListener('change',renderTransactions);
$('globalSearch').addEventListener('keydown',event=>{if(event.key==='Enter'){const q=event.target.value.toLowerCase();const hit=TRANSACTIONS.find(t=>Object.values(t).join(' ').toLowerCase().includes(q));if(hit)openTransaction(hit.id);else{showView('overview');$('tableSearch').value=event.target.value;renderTransactions();}}});
document.addEventListener('keydown',event=>{if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'){event.preventDefault();$('globalSearch').focus();}});
function focusTransactionSearch(){showView('overview');$('tableSearch').focus();}
function startCaseFromDiagnosis(){reset(S.selectedTransaction);}
function reset(source=null){S.caseId=null;S.packaged=false;S.appealed=false;S.last=null;S.cardNetwork="VISA";S.sourceTransaction=source;
  S.scenarioIndex=0;S.autoEvidence=SCENARIOS[0].available.slice();
  $('caseHead').innerHTML=source?`<span class="empty">将从交易 ${esc(source.id)} 创建案件。</span>`:'<span class="empty">尚未创建案件 · 请在下方选择争议类型。</span>';
  $('crumbId').textContent='新建案件';$('verdictCard').style.display='none';
  $('auditOut').innerHTML='<li class="empty">建案后自动记录。</li>';$('agentOut').innerHTML='<div class="empty">—</div>';
  renderStages();renderAction();document.querySelector('.nav a[data-v="flow"]').click();}

const STAGES=["创建案件","补全材料","检查结果","生成材料"];
function stageStatus(){const st=STAGES.map(()=> "");const d=S.last;
  if(!S.caseId){st[0]="now";return st;}
  st[0]="done";const ph=d?d.phase:null;
  if(ph==="REASON_PROPOSED"||ph==="NEED_EVIDENCE"){st[1]="now";return st;}
  st[1]="done";st[2]="done";st[3]=S.packaged?"done":"now";
  return st;}
function renderStages(){const stt=stageStatus();let h="";
  STAGES.forEach((n,i)=>{if(i)h+=`<span class="sep ${stt[i]==='done'||stt[i-1]==='done'?'done':''}"></span>`;
    h+=`<span class="step ${stt[i]}"><span class="b">${stt[i]==='done'?'✓':(i+1)}</span>${n}</span>`;});
  $('steps').innerHTML=h;}

async function openCase(loadAvailable=true){const {ok,data}=await api("POST","/cases",{description:$('desc').value.trim()});
  if(!ok){$('action').innerHTML='<span class="pill p-crit">建案失败：描述不能为空</span>';return;}
  S.caseId=data.case_id;S.packaged=false;S.appealed=false;
  S.autoEvidence=SCENARIOS[S.scenarioIndex].available.slice();apply(data);
  if(loadAvailable){while(S.last&&S.last.phase==="NEED_EVIDENCE"&&S.autoEvidence.length){await submitEvidence(S.autoEvidence.shift());}}}
async function refreshCase(){if(!S.caseId)return;apply((await api("GET",`/cases/${S.caseId}`)).data);}
async function confirmReason(){const v=$('fix')?$('fix').value:"";apply((await api("POST",`/cases/${S.caseId}/confirm`,v?{reason_code:v}:{})).data);}
async function submitEvidence(code){apply((await api("POST",`/cases/${S.caseId}/evidence`,{evidence_code:code})).data);}
async function finalize(){apply((await api("POST",`/cases/${S.caseId}/finalize`)).data);}
function fillScenario(i){const d=$('desc');if(d)d.value=SCENARIOS[i].desc;S.scenarioIndex=i;
  S.cardNetwork=SCENARIOS[i].network;S.autoEvidence=SCENARIOS[i].available.slice();
  if(d&&S.sourceTransaction)d.value=`交易 ${S.sourceTransaction.id}（订单 ${S.sourceTransaction.order}，${S.sourceTransaction.amount}）。${SCENARIOS[i].desc}`;
  document.querySelectorAll('.scenario-card').forEach(c=>c.classList.toggle('on',+c.dataset.i===i));}
async function autoRun(){if(!S.caseId)await openCase(false);let g=0;
  while(S.last&&S.last.phase!=="ASSESSED"&&g++<40){
    if(S.last.phase==="REASON_PROPOSED")await confirmReason();
    else if(S.last.phase==="NEED_EVIDENCE"&&S.autoEvidence.length){
      await submitEvidence(S.autoEvidence.shift());}else break;}}
async function completeAll(){let g=0;while(S.last&&S.last.phase==="NEED_EVIDENCE"&&g++<40){
  await submitEvidence(S.last.next_evidence);}}

function apply(d){if(!d||!d.case_id)return;S.last=d;
  $('crumbId').textContent=d.case_id.slice(0,18);
  renderCaseHead(d);renderStages();renderAction();renderTrace(d);
  const ready=d.phase==="ASSESSED";$('verdictCard').style.display=ready?"block":"none";
  if(ready)renderAssess(d);refreshAudit();refreshMetrics();}

function renderCaseHead(d){
  const conf=d.reason_confirmed?'<span class="pill p-good">已确认</span>':'<span class="pill p-warn">待确认</span>';
  const st=PHASE[d.phase]||["—","p-mut",""];
  let h=`<div class="srow">`
    +`<div class="field"><div class="k">案件</div><div class="v mono">${esc(d.case_id.slice(0,18))}</div></div>`
    +`<div class="field"><div class="k">争议原因</div><div class="v">${esc(REASON_LABEL[d.reason_code]||d.reason_code||"—")} ${conf}</div></div>`;
  if(S.sourceTransaction)h+=`<div class="field"><div class="k">关联交易</div><div class="v mono">${esc(S.sourceTransaction.id)}</div></div>`;
  if(d.facts&&d.facts.amount)h+=`<div class="field"><div class="k">金额</div><div class="v num">${esc(d.facts.amount)} ${esc(d.facts.currency||"")}</div></div>`;
  if(d.deadline){const dl=d.deadline;let cls='p-mut',lb='充裕';
    if(dl.overdue){cls='p-crit';lb='已逾期';}
    else if(dl.days_remaining<=3){cls='p-crit';lb='紧迫';}
    else if(dl.days_remaining<=7){cls='p-warn';lb='临近';}
    const txt=dl.overdue?'已逾期':`还剩 ${dl.days_remaining} 天`;
    h+=`<div class="field"><div class="k">举证时限</div><div class="v"><span class="num">${txt}</span> <span class="pill ${cls}">${lb}</span></div></div>`;}
  h+=`<div class="field"><div class="k">状态</div><div class="v"><span class="pill ${st[1]}">${st[0]}</span></div></div></div>`;
  $('caseHead').innerHTML=h;}

function renderAction(){const d=S.last;const tag=$('phaseTag');
  if(!S.caseId){if(tag)tag.textContent="创建案件";
    const cards=SCENARIOS.map((s,i)=>`<button class="scenario-card${i===0?' on':''}" data-i="${i}" onclick="fillScenario(${i})">`
      +`<strong>${esc(s.label)}</strong><span>${esc(s.meta)}</span></button>`).join("");
    const source=S.sourceTransaction?`<div class="source-case"><strong>已带入当前交易</strong><span>${esc(S.sourceTransaction.id)} · ${esc(S.sourceTransaction.order)} · ${esc(S.sourceTransaction.amount)}</span></div>`:"";
    const initial=(S.sourceTransaction?`交易 ${S.sourceTransaction.id}（订单 ${S.sourceTransaction.order}，${S.sourceTransaction.amount}）。`:"")+SCENARIOS[0].desc;
    $('action').innerHTML=source+`<div style="color:var(--ink);font-weight:700">1. 选择客户提出的争议类型</div>`
      +`<div class="scenario-grid">${cards}</div>`
      +`<label class="field-label" for="desc">2. 确认案件说明</label><textarea id="desc" rows="3">${esc(initial)}</textarea>`
      +`<div class="helper">创建后会自动识别已有材料，并明确显示仍缺什么。</div>`
      +`<div class="actions"><button class="tbtn primary" onclick="openCase()">确认创建案件</button></div>`;return;}
  const ph=d.phase;if(tag)tag.textContent=(PHASE[ph]||["","",""])[2];
  if(ph==="REASON_PROPOSED"){
    $('action').innerHTML=`<div class="muted">${esc(d.question||"")}</div>`
      +`<div class="actions"><select id="fix" style="max-width:280px"></select>`
      +`<button class="tbtn primary" onclick="confirmReason()">确认争议原因</button></div>`;populateReasons();
  }else if(ph==="NEED_EVIDENCE"){
    const labels=d.missing_labels||[];const next=d.next_evidence_label||"下一项证据";
    const question=cleanCopy(d.question||"");
    const missing=labels.map((x,i)=>`<div class="missing-row ${x===next?'next':''}"><span class="box">${i+1}</span><span>${x===next?'下一项优先补交：':''}${esc(x)}</span></div>`).join("");
    $('action').innerHTML=`<div class="missing-box"><div class="missing-head"><span>材料尚未齐全</span>`
      +`<span class="missing-count">仍缺 ${labels.length} 项</span></div><div class="missing-checklist">${missing}</div></div>`
      +(question?`<div style="font-size:15px;color:var(--ink);font-weight:600;margin-top:14px">${esc(question)}</div>`:"")
      +`<div class="helper">每补交一项，系统都会自动重新检查并提示下一项。</div>`
      +`<div class="actions"><button class="tbtn primary" onclick="submitEvidence('${esc(d.next_evidence)}')">补交：${esc(next)}</button>`
      +`<button class="tbtn" onclick="finalize()">本次无法提供，提交人工复核</button></div>`;
  }else if(ph==="ASSESSED"){$('action').innerHTML='<span class="muted">材料收集已完成。请查看下方评估结果并选择下一步。</span>';}
  else $('action').innerHTML=`<span class="muted">阶段：${esc(ph)}</span>`;}
async function populateReasons(){const {data}=await api("GET",`/catalog?locale=${S.loc}`);const sel=$('fix');if(!sel)return;
  sel.innerHTML='<option value="">（接受系统判定）</option>'+data.reasons.map(r=>`<option value="${esc(r.code)}">${esc(r.label)}</option>`).join("");}

function renderAssess(d){const a=d.assessment;if(!a)return;
  const pct=Math.round(parseFloat(a.evidence_readiness||a.win_likelihood||"0")*100);
  const col=pct>=60?'var(--good)':(pct>=30?'var(--warn)':'var(--crit)');
  const rev=a.requires_human?'<span class="pill p-warn">需人工复核</span>':'<span class="pill p-good">材料已齐全</span>';
  const src=SOURCE_LABEL[a.explanation_source]||"规则说明";
  const bd=a.evidence_breakdown||[];const have=bd.filter(i=>i.present).length;const cov=bd.length?Math.round(have/bd.length*100):0;
  const chk=bd.map(i=>`<div class="ei"><span class="tick ${i.present?'y':'n'}">${i.present?'✓':'•'}</span>`
    +`${esc(i.label)}${i.critical?' <span class="crit-tag">关键</span>':''}</div>`).join("");
  $('verdictBody').innerHTML=`<div class="verdict"><div><div class="vnum" style="color:${col}">${pct}%</div>`
    +`<div class="vcap">规则证据就绪度 · 非胜诉概率</div></div>`
    +`<div class="vmeta"><div class="row"><span class="pill p-acc">规则评估</span>${rev}`
    +`<span class="pill p-mut">负责团队 · ${esc(TEAM_LABEL[a.responsible_team]||a.responsible_team)}</span>`
    +`<span class="pill p-mut">说明来源 · ${src}</span></div>`
    +`<div class="cov"><div class="track"><i style="width:${cov}%"></i></div><span class="n">证据 ${have}/${bd.length}</span></div></div></div>`
    +`<div class="ev">${chk}</div>`
    +`<div class="note">${cleanCopy(a.explanation)?esc(cleanCopy(a.explanation))+" ":""}<b>该分数仅表示规则要求的材料就绪程度，不代表真实胜诉概率；说明文字仅作辅助。</b></div>`
    +`<div class="actions"><select id="network" onchange="S.cardNetwork=this.value" style="max-width:180px">`
    +`<option value="VISA" ${S.cardNetwork==='VISA'?'selected':''}>Visa</option>`
    +`<option value="MASTERCARD" ${S.cardNetwork==='MASTERCARD'?'selected':''}>Mastercard</option></select>`
    +`<button class="tbtn primary" onclick="doPackage()">生成申诉材料包</button>`
    +`<button class="tbtn" onclick="doAppeal(false)">预览申诉草稿</button>`
    +`<button class="tbtn danger" onclick="doAppeal(true)">人工确认并模拟提交</button></div>`
    +`<div id="pkgOut" class="mt"></div><div id="appealOut" class="mt"></div>`;}
async function doPackage(){const network=$('network')?$('network').value:S.cardNetwork;S.cardNetwork=network;
  const {ok,data}=await api("GET",`/cases/${S.caseId}/package?locale=${S.loc}&card_network=${encodeURIComponent(network)}`);
  if(!ok){$('pkgOut').innerHTML='<span class="pill p-warn">案件未就绪</span>';return;}
  S.packaged=true;renderStages();
  $('pkgOut').innerHTML=`<div class="kv"><span class="k">材料包</span><span><b style="color:var(--ink)">${esc(data.reason_label)}</b>`
    +` · ${esc(data.card_network||"")} ${esc(data.scheme_reason_code||"")} · 完整度 ${esc(data.completeness)} `
    +`${data.ready_to_submit?'<span class="pill p-good">可提交</span>':'<span class="pill p-warn">未就绪</span>'}</span></div>`
    +`<div class="kv"><span class="k">需证明</span><span>${data.required_assertions.map(esc).join("；")||"—"}</span></div>`
    +`<div class="kv"><span class="k">随附</span><span>${data.ordered_evidence.map(e=>esc(e.label)).join("、")||"—"}</span></div>`
    +`<div class="kv"><span class="k">依据</span><span>${esc(data.source_document||"合成默认规则")} ${esc(data.rule_version||"")} · ${esc(data.source_section||"")}</span></div>`
    +`<div class="note">${esc(data.cover_note)}${data.rule_limitation?`<br><b>边界：</b>${esc(data.rule_limitation)}`:""}</div>`;}
async function doAppeal(approve){const network=$('network')?$('network').value:S.cardNetwork;
  const base={card_network:network};const payload=approve?{...base,human_approved:true,actor_id:"ou_reviewer"}:base;
  const {data}=await api("POST",`/cases/${S.caseId}/appeal`,payload);
  if(data.submitted){S.appealed=true;renderStages();}
  const b=data.submitted?'<span class="pill p-good">模拟提交成功</span>':`<span class="pill p-warn">仅生成草稿 · ${esc(data.blocked_reason||"")}</span>`;
  $('appealOut').innerHTML=`<div class="kv"><span class="k">申诉</span><span>${b}`
    +(data.submission_id?` <code>${esc(data.submission_id)}</code>`:"")+`</span></div>`
    +`<div class="note" style="white-space:pre-wrap">${esc(data.draft)}</div>`;refreshAudit();refreshMetrics();}

function renderTrace(d){const t=d.agent_trace||[];
  $('agentOut').innerHTML=t.length?t.map(x=>`<div class="agent"><span class="atag">${esc(AGENT_LABEL[x.agent]||x.agent)}</span>`
    +`<span>${esc(actionLabel(x.action))}${x.source?` <span class="src">· ${esc(SOURCE_LABEL[x.source]||x.source)}</span>`:""}</span></div>`).join(""):'<div class="empty">—</div>';}
async function refreshAudit(){if(!S.caseId)return;const {ok,data}=await api("GET",`/cases/${S.caseId}/audit`);if(!ok)return;
  $('auditOut').innerHTML=data.events.map(e=>`<li><div class="e">${esc(EVENT_LABEL[e.event_type]||e.event_type)}${e.detail?` · ${esc(detailLabel(e.detail))}`:""}</div>`
    +`<div class="m">版本 ${e.case_revision}</div></li>`).join("")||'<li class="empty">—</li>';}
async function refreshMetrics(){const {data}=await api("GET","/metrics");const c=(data&&data.counts)||{};
  if(!Object.keys(c).length){$('metricsOut').innerHTML='<span class="empty">暂无（运行一个案子后出现）</span>';return;}
  const g=k=>c[k]||0;
  const rhT=g('requires_human_true'),rhF=g('requires_human_false'),rhTot=rhT+rhF,rhPct=rhTot?Math.round(rhT/rhTot*100):0;
  const mdl=g('explanation_source_MODEL'),fb=g('explanation_source_FALLBACK'),sTot=mdl+fb,mdlPct=sTot?Math.round(mdl/sTot*100):0;
  let h="";
  if(rhTot)h+=`<div class="mstat"><div class="ml"><span>需人工复核率</span><b>${rhPct}%</b></div><div class="mbar"><i style="width:${rhPct}%"></i></div></div>`;
  if(sTot)h+=`<div class="mstat"><div class="ml"><span>辅助说明使用率</span><b>辅助 ${mdl} · 规则 ${fb}</b></div><div class="mbar"><i style="width:${mdlPct}%"></i></div></div>`;
  const extra=[['评估次数',g('assessments_total')],['申诉已提交',g('appeal_submitted')],['申诉被阻断',g('appeal_blocked')]];
  h+=`<div class="mnote">`+extra.map(x=>`<span>${x[0]}</span><b>${x[1]}</b>`).join("")+`</div>`;
  $('metricsOut').innerHTML=h;}
async function assessPrevention(){
  const b={three_ds_authenticated:!$('p_no3ds').checked,avs_match:!$('p_noavs').checked,cross_border:$('p_cross').checked,amount:($('p_amount').value||"0")};
  const {ok,data}=await api("POST","/prevention/assess",b);
  if(!ok){$('preventionOut').innerHTML='<span class="pill p-crit">请求无效</span>';return;}
  const cls={LOW:'p-good',MEDIUM:'p-warn',HIGH:'p-crit'}[data.risk_level]||'p-mut';
  const col={LOW:'var(--good)',MEDIUM:'var(--warn)',HIGH:'var(--crit)'}[data.risk_level]||'var(--muted)';
  $('preventionOut').innerHTML=`<div class="verdict"><div><div class="vnum" style="font-size:32px;color:${col}">${esc(RISK_LABEL[data.risk_level]||data.risk_level)}</div>`
    +`<div class="vcap">拒付风险 · 评分 ${esc(data.risk_score)}</div></div><div class="vmeta">`
    +`<div class="row">${data.factors.map(f=>`<span class="pill ${cls}">${esc(FACTOR_LABEL[f]||f)}</span>`).join("")||'<span class="muted">未发现明显风险因子</span>'}`
    +`${data.recommend_manual_review?'<span class="pill p-warn">建议人工复核</span>':''}</div>`
    +`<div class="note" style="margin:0">建议现在留存：${data.recommended_evidence.map(e=>esc(e.label)).join("、")||"—"}。`
    +(cleanCopy(data.advice)?`<br>${esc(cleanCopy(data.advice))}`:"")+`</div></div></div>`;
  refreshMetrics();}
async function safetyScan(){const {ok,data}=await api("POST","/safety/scan",{text:$('safeText').value});
  if(!ok){$('safeOut').innerHTML='<span class="pill p-crit">请求无效</span>';return;}
  const p=data.accepted?'<span class="pill p-good">✓ 通过</span>':'<span class="pill p-crit">⛔ 已拦截</span>';
  $('safeOut').innerHTML=`<div class="note" style="margin:0">${p} &nbsp;${esc(data.detail)}</div>`;}

renderTransactions();renderStages();renderAction();refreshMetrics();
</script>
</body>
</html>
"""


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/demo")


@router.get("/demo", include_in_schema=False, response_class=HTMLResponse)
def demo_page() -> HTMLResponse:
    return HTMLResponse(_DEMO_HTML)
