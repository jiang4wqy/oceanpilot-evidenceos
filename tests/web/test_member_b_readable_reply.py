"""Readable AI display keeps the complete original available and escaped."""

import subprocess
from pathlib import Path


def test_ai_reply_compacts_old_checklists_without_losing_original():
    source = Path("src/oceanpilot/web/v2/collaboration.js").read_text()
    helper = source.split("  function readableAnswer(body) {", 1)[1].split("  function same", 1)[0]
    script = (
        r"""
const assert = require('node:assert/strict');
const esc = value => value.replaceAll('&','&amp;').replaceAll('<','&lt;');
function readableAnswer(body) {
"""
        + helper
        + r"""
const input = '尚缺以下登记材料：\n' +
'- 交易收据（transaction.receipt）：核对金额；登记不表示真实性已核验。\n' +
'材料内容检查：请核对原件。\n材料内容检查：请核对原件。\n\n' +
'本次检索到的指南参考：\nCB-CASE-041 <script>';
const output = readableAnswer(input);
const main = output.split('<details')[0];
assert.ok(main.includes('请补充以下材料：'));
assert.ok(main.includes('- 交易收据'));
assert.ok(!main.includes('transaction.receipt'));
assert.ok(!main.includes('CB-CASE'));
assert.equal(main.split('请核对原件。').length, 2);
assert.ok(output.includes('transaction.receipt'));
assert.ok(output.includes('CB-CASE-041 &lt;script>'));
assert.ok(!output.includes('<script>'));
"""
    )
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
