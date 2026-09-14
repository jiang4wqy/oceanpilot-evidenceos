# 最终候选核验 — 2026-09-14

独立 `.venv` / Python 3.12.13；基线 f1fc063 加本地 B 补丁；未提交/推送。构建哈希（包含本地生成的包元信息）：

`2947e6069d5f757f1333502c8b46141ebdedb4e636e93ff070efd91db8dc18b3`

当前数据实例 `78cae79a-979a-4438-a024-1614cadc141a`，目录 `work/member-b-demo/recovery-final`，监听 `127.0.0.1:8015`。快照 `snapshot-review-final`，详细来源链、逐文件构建哈希、依赖与三库快照哈希见 `build-manifest.json`。运行后登录/已读会正常改变库文件，快照哈希只指备份时点。

| 命令/范围 | 结果 |
|---|---|
| `PYTHONPATH=src .venv/bin/python -m pytest -q -ra` | **2249 passed, 6 skipped, 2 warnings in 138.45s** |
| `.venv/bin/ruff check src tests scripts/member_b_demo.py scripts/member_b_rehearsal.py` | PASS |
| `.venv/bin/ruff format --check src tests scripts/member_b_demo.py scripts/member_b_rehearsal.py` | PASS，279 files |
| `git diff --check` | PASS |
| `.venv/bin/ruff check .` | 10 个既有错误，仅在两个旧辅助脚本；未清理 A 的脚本 |
| 实际网页：商户决定→缺字段阻断→替换→完整材料→提交审核 | PASS/EXPECTED BUSINESS BLOCK，v10 OP_REVIEW，结果 UNKNOWN/NOT_FINAL |
| SQLite 安全备份→新目录恢复→正常登录/API下载/网页查看 | PASS，五份活动材料对象/哈希、签收 revision 2、案件 revision 10 与当前负责人一致 |
| 1440/1174/390 CSS px 布局 | 已检查；1440 与 390 scrollWidth 等于 viewportWidth |

跳过 5 个实时模型测试（缺 DEEPSEEK_API_KEY / ANTHROPIC_API_KEY）及 1 个 PowerShell 测试（本机无 PowerShell）。Starlette/httpx 和 AnyIO 别名弃用警告保留。测试日志保存在工作区 `../member-b-64-handoff/final-pytest-isolated-runtime.log`，没有把跳过项算为通过。

本轮浏览器未验证完整 Mock 提交/UNKNOWN 查询、直接接受、建议接受、关闭案件、双设备同时操作或实时飞书。完整自动集只是这些既有行为的支持证据。C 独立三次主路径、录制/展示冻结及 A/C 联合环境仍待确认。

当前产品文件格式仅 TXT/JSON/单行 CSV；不支持 PDF/图片识别、OCR、恶意文件扫描或文件真实性证明。老师反馈真实客户以截图/PDF 为主，已记入 `TECHNICAL-QA.md`。
