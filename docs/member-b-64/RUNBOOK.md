> 图片/PDF/Word 与可选实时模型启动：见 [DOCUMENT-UPLOAD.md](DOCUMENT-UPLOAD.md)。默认启动仍离线。

# Member B：独立合成演示候选版

2026-09-14。用于 #64 / #66 的本地验收候选，尚未获 C 独立三次验收，未标记全 Stage 4/5 完成，也未提交、推送或发布。

## 版本、责任与入口

- 代码目录：`/Users/luxinyu/Desktop/飞书 ai 大赛/work/oceanpilot-member-b-64`。
- 基线：`f1fc063c9adcb52c47ca77298de9d5cc8bd2432c`，detached worktree 加本地 B 修改。实际构建以 `instance.json` 的 `code.sha256` 和逐文件哈希为准，不能仅用 Git HEAD 指代演示代码。
- B 卢薪宇 / @RyanLu0203 负责业务、界面、B 回归、启动/停止与恢复；A 朱泽林 / @zelin-michael-zhu 负责飞书适配、配置与隧道；C Jiang / @jiang4wqy 负责独立验收和录制。
- 计划端口 8014 已被旧实例使用，未停止或修改旧实例。本候选使用 **127.0.0.1:8015**，外部/手机 URL 尚未联合确认。A 的 8002 不是本数据库。
- 当前运行数据：`work/member-b-demo/recovery-final`；从 `snapshot-review-final` 经 SQLite backup API 恢复，保留母实例 `candidate-01`。
- Python 3.12.13；本工作树 `.venv`。版本清单见 `runtime-requirements.txt`。不读取 `.env`，不继承飞书/模型密钥。服务仅监听回环地址，模型关闭，上游 Mock。
- 登录 `/v2/login`；商户 `/v2/merchant`；运营/风控/主管 `/v2/operations`；来源库 `/v2/operations/library`；导演 `/v2/director`。不使用 V1 `/demo`。

## 启动、停止、重启

在终端执行：

```sh
cd '/Users/luxinyu/Desktop/飞书 ai 大赛/work/oceanpilot-member-b-64'
PYTHONPATH=src .venv/bin/python scripts/member_b_demo.py status --instance work/member-b-demo/recovery-final
PYTHONPATH=src .venv/bin/python scripts/member_b_demo.py start --instance work/member-b-demo/recovery-final
```

看到 `Application startup complete` 后访问 `http://127.0.0.1:8015/v2/login`。`status` 不代表服务正在运行；它检查数据与版本标识。启动会拒绝端口被占用、代码/所记录依赖漂移、或直接启动备份快照。

停止前把本演示页面离开到空白页，断开 SSE 长连接；只在本实例的终端按一次 Ctrl+C，等待 `Application shutdown complete` 和 `Finished server process`。不要运行全局 pkill。重启使用同一条 start 命令，不新建/覆盖数据库。若后台任务尚未结束，等待正常退出，避免把半关闭状态当成备份时点。

## 私有账号

凭据只在每个实例的 `private-accounts.json`（0600），目录 0700；不得贴入 GitHub、视频或共享文档。商户 `merchant-a`、另一商户 `merchant-b`；运营 `operator-a` / `operator-b`；风控 `risk-reviewer`；主管 `supervisor`；管理员 `administrator`；导演 `director`。各自使用现有独立账号，不能通过修改请求头假扮角色。两人联合测试应使用独立浏览器配置文件/设备；当前 B 的浏览器测试为同一浏览器逐次登出登录，不宣称已经完成双设备并发验收。

## 新演练与重置

优先新建案件，保留之前的材料、审计和状态：

```sh
PYTHONPATH=src .venv/bin/python scripts/member_b_rehearsal.py --instance work/member-b-demo/recovery-final
```

脚本用私有导演账号正常登录、HTTP 登记明确的合成交易，再由运营通过标准事件接入并发布商户任务。每次生成新交易/事件/案件 ID；不写数据库业务状态、不预填证据/决定/审核/结果。终端输出案件 ID、样例目录。样例从实际受保护下载接口取得，五项材料各含 sufficient / missing_field / wrong_transaction，共 15 份 JSON。

主案例是 **B-SYN-VISA131 合成补充**，不是某个真实核心案例的复现；不自动挂靠 CB-CASE-060，也不携带参考答案。使用程序已有 Visa 13.1 Mock 合成政策，完整 5 项必需材料，其中 tracking / proof_of_delivery 为关键项。72/96/120 小时是合成 UTC 经过小时，不是卡组织正式时限。

需要完全空白环境时，先停止已运行的演示，再指定从未存在的目录：

```sh
PYTHONPATH=src .venv/bin/python scripts/member_b_demo.py new --instance work/member-b-demo/recording-02 --port 8015
PYTHONPATH=src .venv/bin/python scripts/member_b_demo.py start --instance work/member-b-demo/recording-02
```

`new` 会拒绝覆盖现有目录，生成新账号和新数据身份。禁止删除旧目录作为“重置”，禁止恢复或替换共享开发数据库。

## 可重复的录制路径

1. 运行新演练脚本。商户打开其新案件，选择提出抗辩，自行填写合成决策事实并勾选确认。决定与授权字段保持空白，不提供“已获授权”的自动断言。
2. “抗辩材料”→签收证明“选择文件”，上传本案 `fulfillment.proof_of_delivery-missing_field.json`。应出现缺少 `delivered_at`，提交被阻止。这是 **EXPECTED BUSINESS BLOCK**。
3. 同一材料“选择文件/上传修订版”会选中原文件的替换选项；上传 `fulfillment.proof_of_delivery-sufficient.json`。应只有一个有效签收材料，材料 revision 增加，旧文件历史保留。不要选择“新增文件（保留已有文件）”来掩盖旧材料问题。
4. 商户通过真实文件选择器上传 `transaction.receipt`、`fulfillment.tracking`、`comms.customer` 足够版。普通必需项缺失仍阻止提交，不能因两个关键项已齐就提交。
5. 运营用自己的账号打开同一案件→本案文件与材料，选择“收货地址匹配”，上传该案 `fulfillment.address_match-sufficient.json`。这是明确标注的**合成系统记录导出**，不是官方连接器或真实系统核对。
6. 商户刷新，五项齐备后“提交材料给 OceanPayment”，勾选本次确认。应到 `OP_REVIEW`，当前负责人为独立风控审核员；期限切为内部目标，旧商户任务完成，商户无需重复提交。
7. 录制可止于此：业务结果 UNKNOWN、NOT_FINAL。风控审核、主管批准、正式 Mock 提交、查询和资金结案须继续走各自正常人工动作，不能强行获胜/结案。

错交易异常：另建案件，把任一对应材料的 wrong_transaction 版作为初稿；应指出 case/transaction 不匹配，不能以改文件名解决。再明确替换成该案 sufficient 版。该异常已有真实 HTTP 流测试，B 尚未单独完成错交易浏览器录制。

## 安全备份与恢复

仅在源实例停止后执行：

```sh
PYTHONPATH=src .venv/bin/python scripts/member_b_demo.py backup --instance work/member-b-demo/recovery-final --destination work/member-b-demo/snapshot-02
PYTHONPATH=src .venv/bin/python scripts/member_b_demo.py restore --instance work/member-b-demo/snapshot-02 --destination work/member-b-demo/recovered-02 --port 8015
PYTHONPATH=src .venv/bin/python scripts/member_b_demo.py start --instance work/member-b-demo/recovered-02
```

通过 SQLite backup API 保存 core/chargeback/rules 三库，执行 integrity_check，保存 SHA-256；恢复时先核对快照哈希，新目录与新实例 ID，保留 parent_id。快照不能直接启动，已存在的目标不会被覆盖。材料字节位于 SQLite BLOB，随库恢复；独立导出的样例/截图/日志应另存，其原件仍在旧演练目录，样例也可从恢复实例按案重新下载。

若端口占用，查清进程及归属，不接管未知进程。若版本漂移，先复查代码、回归与截图，再在停止状态明确执行 `pin`；它保留旧构建清单，只更新版本身份，不更改业务状态。不得用 pin 跳过验收。若快照哈希错误，恢复会拒绝：保留现场并选已知完好的快照，不手工修正哈希。

## 依赖恢复与复验

当前已准备独立 `.venv`。需要在另一受控目录重建时，使用 Python 3.12.13：

```sh
uv venv --python 3.12.13 .venv
uv pip sync --python .venv/bin/python docs/member-b-64/runtime-requirements.txt
uv pip install --python .venv/bin/python --no-deps -e .
PYTHONPATH=src .venv/bin/python -m pytest -q -ra
.venv/bin/ruff check src tests scripts/member_b_demo.py scripts/member_b_rehearsal.py
.venv/bin/ruff format --check src tests scripts/member_b_demo.py scripts/member_b_rehearsal.py
git diff --check
```

不要在已有运行环境上盲目重建。跨设备仍需复制经核对的未提交补丁、新增脚本/测试和数据；只有 HEAD 不含 B 的修改。C 接收后须核对构建与数据清单，独立完成三次主流程，再确认可录制/冻结。提交/推送仍需用户明确授权。
