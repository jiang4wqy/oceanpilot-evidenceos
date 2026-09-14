# Stage 2 双端与案件隔离审核记录

审核日期：2026-09-13
分支：`oceanpilot-v2`
基线 HEAD：`eb46b08d45d8b87c96b38a8248f890160aea436d`

本记录只覆盖推进计划的“批次 2：双端与案件隔离”。验证使用当前工作树、独立的
`work/stage1-review/` SQLite 数据实例和 8014 本地 HTTP 服务。验证结束后服务已停止。
本批次没有修改业务代码；Stage 1 的未提交改动仍保留在工作树中。

## 审核结论

批次 2 门禁通过：运营与商户可在不同 cookie 会话中同时访问同一案件；同一商户的两案、
另一商户的一案在服务端正确分区；共享消息同案可见，OP 内部消息不向商户投影；跨商户
直接访问案件、计划、Agent 和协作接口均返回 404。案件消息不改变业务 revision，旧提案、
跨案提案和切换案件后的迟到响应由现有回归覆盖，不能转绑或继续执行。

本轮没有发现需要新增权限分支或复制案件模型的问题，因此没有为制造代码增量而重写现有实现。

## 实际会话与案件拓扑

本次创建五个相互独立的 HTTP 客户端会话：导演、运营 A、运营 B、商户 A、商户 B；
五个 `session` cookie 均不同，未使用角色请求头模拟身份。

| 参与方 | 服务端可见案件 |
| --- | --- |
| 运营 A | `OPV2-d0d9ee31gce1e6e22`、`OPV2-c8cd045fg6060008f` |
| 商户 A | `OPV2-d0d9ee31gce1e6e22`、`OPV2-c8cd045fg6060008f` |
| 运营 B | `OPV2-5c5bc048g106c01e7` |
| 商户 B | `OPV2-5c5bc048g106c01e7` |

三个案件当前 revision 均为 1。商户 A 的第二案来自 `CB-CASE-040`，交易为
`stage2-a3-transaction`；商户 B 的案件来自 `CB-CASE-045`，交易为
`stage2-b2-transaction`。这两条标准化事件状态均为 `PROCESSED`。

## 真实 HTTP 请求矩阵

基址为 `http://127.0.0.1:8014`。GET 请求没有 request payload；鉴权来自各自独立的
HttpOnly session cookie。为避免泄露凭据，本记录不保存 cookie 值。

| 调用方 | HTTP method 与 URL | Request payload | Response | 对应后端路由 |
| --- | --- | --- | --- | --- |
| 运营 A / 商户 A | `GET /api/v2/cases` | 无 | 200；两端返回相同的两个 A 案件 ID | `api/disputes.py::list_cases` |
| 运营 B / 商户 B | `GET /api/v2/cases` | 无 | 200；两端只返回 B 案件 | `api/disputes.py::list_cases` |
| 商户 B | `GET /api/v2/cases/OPV2-c8cd045fg6060008f` | 无 | 404 | `api/disputes.py::get_case` |
| 商户 B | `GET /api/v2/cases/OPV2-c8cd045fg6060008f/plan` | 无 | 404 | `api/disputes.py::plan` |
| 商户 B | `GET /api/v2/cases/OPV2-c8cd045fg6060008f/agent` | 无 | 404 | `api/disputes.py::agent_activity` |
| 商户 B | `GET /api/v2/cases/OPV2-c8cd045fg6060008f/collaboration` | 无 | 404 | `api/dispute_collaboration.py::activity` |
| 商户 A | `POST /api/v2/cases/OPV2-c8cd045fg6060008f/collaboration/messages` | `{"command_id":"stage2-shared-777b278cd7734f9cb07f58208a74edf6","scope":"SHARED","message":"批次 2：商户 A 的同案共享消息。","ask_agent":false}` | 200；运营 A 随后读取到同一条消息 | `api/dispute_collaboration.py::message` |
| 运营 A | `POST /api/v2/cases/OPV2-c8cd045fg6060008f/collaboration/messages` | `{"command_id":"stage2-internal-d31d34cd31fb488ab334a345e265286b","scope":"OP_INTERNAL","message":"批次 2：仅 OP 可见。","ask_agent":false}` | 200；只写入 OP_INTERNAL | `api/dispute_collaboration.py::message` |
| 商户 A | `GET /api/v2/cases/OPV2-c8cd045fg6060008f/collaboration?scope=OP_INTERNAL` | 无 | 404；不能通过参数读取内部范围 | `api/dispute_collaboration.py::activity` |

404 是有意的资源隐藏策略：无权调用者不会从 403/详情差异中探测案件是否存在。权限判断在
服务端应用层执行，不依赖浏览器隐藏入口。

## 同案同步与上下文边界

- 商户 A 写入的 SHARED 消息持久化为 collaboration seq 1，运营 A 能读取同一对象。
- 运营 A 写入的 OP_INTERNAL 消息持久化为 seq 2，商户响应中不包含该消息。
- 两次消息写入后案件 `OPV2-c8cd045fg6060008f` revision 仍为 1，沟通事件没有使业务批准或提案失效。
- 页面切案的迟到响应不会覆盖当前选中案件；缺失或失权案件不会回退到另一个可见案件。
- Agent endpoint 会再次校验商户与案件范围；proposal ID 不能转绑到另一案件，旧 revision 的提案不能靠客户端提交新 revision 继续执行。

## 预期阻塞记录

首次创建商户 A 第二案时误用了 `CB-CASE-060`（事件 `stage2-a2-event`）。该模板与
`VISA / 10.4` 不匹配，接入事件被正确标记为 `QUARANTINED / TEMPLATE_SCOPE_MISMATCH`，
没有创建运行案件。随后使用匹配的 `CB-CASE-040` 重新创建独立事件并成功处理。
这是预期的 fail-closed 业务阻塞，不是产品故障，也没有删除失败记录。

## 自动化证据

定向命令：

```text
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/api/test_v21_identity.py \
  tests/api/test_dispute_collaboration_api.py \
  tests/api/test_dispute_agent_api.py \
  tests/api/test_dispute_updates_api.py \
  tests/application/test_dispute_updates.py \
  tests/web/test_v2_rendering.py \
  tests/web/test_page_runtime.py \
  tests/review/test_v21_independent_review.py
```

结果：**187 passed**，2 条 warning，30.00 秒。

重点断言包括：真实 session cookie 与轮换、列表/详情/计划/命令/更新的租户范围、参与人撤权、
共享与内部范围、文件下载范围、Agent 全端点授权、旧提案拒绝、提案跨案转绑拒绝、迟到模型
响应隔离、切案后页面状态、更新游标和独立 HTTP 审查。

## 本批次没有声称的事项

- 没有把当前自动化和开发者 HTTP 验证表述为未参与开发者的可用性测试。
- 没有验证真实外部飞书群或生产卡组织通道。
- 没有修复 Stage 0 已登记的关键证据覆盖和 SLA 风险计算问题；它们留给后续业务逻辑批次。
- 没有开始批次 3 的任务卡、上传体验或 AI 文案调整。
