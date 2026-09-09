# V2.1 飞书协作与授权测试群 Outbox（X01）

已实现签名回调、可信账号与群绑定、案件共享消息、卡片预览、持久投递队列、显式发送、真实消息接口适配及回执重试。默认关闭外发。**本次没有真实飞书租户 smoke，没有发送任何外部消息；Gate 5 的真实飞书验收尚未完成。** 本地测试中的消息回执来自显式注入的 mock transport，不能作为线上已投递证据。上游案件提交仍是 Mock。

## 接口与生命周期

| 接口 | 用途与权限 |
| --- | --- |
| `POST /api/v2/integrations/feishu/events` | 签名 URL challenge、`im.message.receive_v1` 回调 |
| `POST /api/v2/integrations/feishu/card` | 签名 `card.action.trigger`；仅可信商户确认 Accept/Contest |
| `GET /api/v2/integrations/feishu/outbox?case_id=...` | 当前可信 OP、审核人或主管查看本案预览、投递状态、最近 100 条记录和可用测试群引用 |
| `POST /api/v2/integrations/feishu/outbox` | 当前可信 OP、审核人或主管创建本地预览；无网络调用 |
| `POST /api/v2/integrations/feishu/outbox/{id}/send` | 当前可信 OP、审核人或主管显式确认发送或重试；必须再次通过案件及目标授权校验 |

`initialize_dispute_feishu(app, db_path, base_url, environ=...)` 只能在 FastAPI lifespan 内、`app.state.disputes` 与协作服务初始化后调用。构造 application 不打开数据库。初始化提供 `app.state.dispute_feishu`、`dispute_feishu_verifier` 和 `dispute_feishu_outbox`；lifespan 退出时调用 outbox 的 `close()`。

可信入站配置缺失或无效时，回调与 outbox API 返回 `503 FEISHU_V2_DISABLED`。入站有效但出站未授权时，回调仍可记录共享消息和决定；显式发送返回 `503 FEISHU_OUTBOUND_DISABLED`。浏览器 outbox API 使用现有真实 session、CSRF 和服务端账号目录，不接受 `X-Demo-Role` 或请求体自报身份。

## 入站的账号、商户及群授权

所需本机配置：

- `FEISHU_ENCRYPT_KEY`：签名校验密钥。
- `FEISHU_VERIFICATION_TOKEN`：每个 payload 的 token，包括 challenge。
- `OCEANPILOT_V2_FEISHU_BINDINGS_JSON`：`actors` 和 `chats` 映射。

用 `binding_key(kind, tenant_key, external_id)` 创建域分离 SHA-256 索引。actor key 绑定租户与实际 sender/operator 的 `open_id`；chat key 绑定租户与 chat ID。哈希仅是最小化存储的索引，不能取代签名认证。

以下仅为合成配置结构，不可直接用于真实投递：

```python
from oceanpilot.adapters.channels.feishu.v2 import binding_key

bindings = {
    "actors": {
        binding_key("actor", "synthetic-tenant", "synthetic-open-id"): {
            "role": "MERCHANT",
            "actor_id": "existing-server-user-id",
            "merchant_id": "synthetic-merchant",
        }
    },
    "chats": {
        binding_key("chat", "synthetic-tenant", "synthetic-chat-id"): "synthetic-merchant"
    },
}
```

允许绑定角色为 `MERCHANT`、`OPERATOR`、`RISK_OFFICER`、`SUPERVISOR`；不允许外部 actor 使用保留的内核 `AGENT` 角色。`actor_id` 必须对应当前启用的服务端账号，角色匹配、商户授权和案件 participants 仍由 access policy 逐次校验。即使回调响应已持久化，账号撤销或案件访问撤销后也不能读取其回放。治理 `ADMIN` 不自动获得业务权限。

不能从卡片 value、消息文字或 URL 中获取可信 role、merchant、revision。未知租户、actor、chat 或商户不匹配均拒绝。每次业务操作还调用 `disputes.get_case(case_id, identity)`；同一个商户群内有多案时，消息必须显式指定案件。

## 出站的本机授权开关

只接受部署者在本机配置的测试群，不提供远程 API 修改授权名单。除了有效入站配置，必须同时具备：

1. `OCEANPILOT_V21_FEISHU_OUTBOUND=authorized-test`。
2. `FEISHU_APP_ID` 与 `FEISHU_APP_SECRET`。
3. `OCEANPILOT_V21_FEISHU_TEST_TARGETS_JSON` 中明确的测试群授权；与可信 chat→merchant 映射一致。

名单结构：

```json
{
  "targets": [{
    "tenant_key": "synthetic-tenant",
    "chat_id": "synthetic-chat-id",
    "merchant_id": "synthetic-merchant",
    "authorized": true,
    "authorization_reference": "owner-approved-synthetic-test-space",
    "label": "合成验收群",
    "allow_callback_replies": false
  }]
}
```

`authorized` 必须为 JSON boolean `true`，授权依据不得为空。`allow_callback_replies` 默认 false；只有单独明确设为 true，已验证入站回调产生的回复／卡片更新才可由后台发送。**本地预览永不因这个开关而自动发送。** 缺少任一条件不会构造真实出站 client。API 请求不能传入 chat ID、租户、APP secret 或 `automatic=true` 来绕过配置。

真实配置属于后续明确授权操作。本次实现及验收均没有填写任何真实测试群、调用真实消息 API 或读取／输出真实密钥。

## 预览、发送与回执

先 GET 本案 outbox，选择服务端返回的 `target_ref`，随后创建预览：

```json
{
  "command_id": "a-new-unique-command-id",
  "case_id": "the-authorized-case-id",
  "target_ref": "64-character-server-returned-chat-hash",
  "kind": "NEW_DISPUTE"
}
```

可用卡片种类：`NEW_DISPUTE`、`MISSING_EVIDENCE`、`SLA_REMINDER`、`REVIEW_FEEDBACK`、`SUMMARY`。响应包含可检查的 `card`、`case_revision`、`state=PREVIEW`、`delivery_status=NOT_SENT` 和 `message_id=null`。预览不伪造投递成功。确认后向该记录 `/send` 提交 `{"confirmed":true}`。

卡片冻结当时内容和案件版本。未发送预览在案件变化或生成满一小时后不可发送，需要新的预览命令；系统不会静默刷新已审核内容。卡片只含共享可见计划、缺证、商户截止和引用，不包含 OP 内部截止、内部讨论、材料包草稿或账务明细。深链为 `/v2/merchant/cases/{case_id}`。

`v21_feishu_outbox` 保留案件、操作者、目标哈希、授权引用、冻结卡片、固定 UUID、操作类型、每次尝试的时间／操作者／状态、最后回执。原始 tenant/chat ID 不写入该表；reply/update 必需的 provider message ID 会持久化，凭据及原始回调体不会。

| 状态 | 含义 |
| --- | --- |
| `PREVIEW` | 本地已生成，尚未发送 |
| `PENDING` | 单独获准自动回复的回调队列项，等待发送 |
| `SENDING` | 已获得并发发送租约，等待 provider 响应 |
| `SENT` | provider 返回成功消息回执；`delivery_status=DELIVERED_TO_FEISHU`，有 `message_id` |
| `UNCERTAIN` | 网络／provider 回执无法确认；不冒称成功，由人员显式重试 |
| `BLOCKED` | 自动项因授权撤销、案件变化等被阻断，没有发送 |

同 command ID 的 actor 或 payload 改变返回 409。SENT 重试只返回已存回执，不再次调用网络。发送／回复的网络超时或进程重启后，显式重试保留同一个 provider UUID 和完全相同卡片内容；并发发送通过 SQLite 租约防止同时调用。失去响应的发送不无限自动重试，仍显示 UNCERTAIN。PATCH 没有 provider UUID，重试用相同消息 ID 和相同内容；案件已进入新版本时，旧 PATCH 即使 UNCERTAIN 也拒绝，避免覆盖新版卡片。

实际 provider 的去重保留期与租户故障恢复尚未实测，因此不能承诺跨任意长时间或任意故障的“全局恰好一次”。SENT 表示飞书服务接受，并不表示商户已读、已确认业务结果或资金操作成功。

## 签名回调与共享线程

`@OceanPilot CASE_ID 还缺什么？` 和飞书渲染的 `@_user_1 CASE_ID ...` 被识别。文字经敏感数据检查，可信 identity 与 case 校验后，V2.1 保存为 `COLLABORATION_MESSAGE`，进入本案 `SHARED` journal；带 `channel=FEISHU`、哈希 event/thread 引用及真实操作者。普通聊天、Agent 回复和投递状态不增加案件业务 revision，不使待批准业务动作失效。

当前飞书回调回答使用确定性 `case_plan`，明确标记 `source=DETERMINISTIC, provider=DETERMINISTIC, model=case-plan`。它把有版本和来源的摘要同时写入共享线程，并在获准自动回复时排入线程 reply 队列；不会伪称调用外部模型。正式模型讨论仍可在共享网页线程进行。回执写入中断时使用首个已验证事件冻结的答案重放；后来的业务变化不会偷偷改写旧回复。旧版本已经记住的 COMMENT 命令保持原命令语义和幂等回放，新聊天不再走该业务命令。

卡片 Accept/Contest 只显示规则已核验、`allowed_actions` 明确允许的动作；未知／空权限卡只保留查看案件。按钮含 Feishu confirmation dialog 与严格 boolean `confirmed`。opaque `card_ref` 在服务端绑定案件、版本、商户、chat、卡片种类及一小时有效期；过期、跨案、跨群、错误角色、过时版本均不能执行。决定仍是单一 `MERCHANT_DECISION` 事务，领域层原子写入业务状态、collaboration 和 audit；业务观察者将公开决定桥接到 SHARED。不会再补第二个非原子的 COMMENT。

卡片回调更新只允许指向本 outbox 已确认投递到同 chat、同 case 的 message ID。普通消息带 root ID 时，若它是本 outbox 已知的其他案件根消息，则拒绝跨案件回复。无可验证 provider message ID 时不伪造回复。提交成功后的出站排队异常不会把已经提交的业务决定变成 500；回调回执会如实报告 `NOT_QUEUED`，可在本地检查／重新创建预览。

## 验证与尚未完成的真实联调

请求体上限 64 KiB，仅 JSON。原有 verifier 在业务处理前验证 SHA-256 签名、token、唯一签名请求头和 300 秒时窗。错误使用 `application/problem+json` 与固定错误码，异常细节不回显。事件 ID 按租户隔离并绑定完整 payload fingerprint，修改原事件的 actor／内容／操作均冲突。

本地回归：

```bash
PYTHONPATH=src .venv/bin/pytest -q \
  tests/channels/test_dispute_feishu.py \
  tests/channels/test_dispute_feishu_outbox.py \
  tests/feishu/test_client.py \
  tests/application/test_dispute_collaboration.py
```

这四组本次合计 **142 passed**；包括真实服务端账号与签名 HTTP、案件共享线程、商户决定原子审计、同案回执、网络失去回执后的幂等恢复、并发发送、权限撤销、跨案件 root 阻断和 callback 后台 drain。所有消息 transport 均为本地合成 mock。

真实 Gate 5 尚需用户明确授权的测试空间、管理员配置及可达 HTTPS callback URL，按实际 tenant 的签名／确认 payload 验证商户操作、真实 reply/update、回执和跨端可见性。当前 verifier 只支持签名明文 JSON，未实现加密 body 解密；加密回调会拒绝。没有真实回执之前不能将 Gate 5 标记通过。

接口依据是飞书官方的[发送消息](https://open.feishu.cn/document/server-docs/im-v1/message/create)、[回复消息](https://open.feishu.cn/document/server-docs/im-v1/message/reply)与[更新应用发送的消息卡片](https://open.feishu.cn/document/server-docs/im-v1/message-card/patch)。字段和 HTTP 方法另核对官方 Python SDK 的 [`reply_message_request_body.py`](https://github.com/larksuite/oapi-sdk-python/blob/v2_main/lark_oapi/api/im/v1/model/reply_message_request_body.py)、[`reply_message_request.py`](https://github.com/larksuite/oapi-sdk-python/blob/v2_main/lark_oapi/api/im/v1/model/reply_message_request.py)、[`patch_message_request_body.py`](https://github.com/larksuite/oapi-sdk-python/blob/v2_main/lark_oapi/api/im/v1/model/patch_message_request_body.py) 和 [`patch_message_request.py`](https://github.com/larksuite/oapi-sdk-python/blob/v2_main/lark_oapi/api/im/v1/model/patch_message_request.py)：reply 为 POST、包含 `content/msg_type/reply_in_thread/uuid`，patch 为 PATCH、仅 `content`。
