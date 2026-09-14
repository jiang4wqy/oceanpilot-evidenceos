# Stage 3 任务与材料体验审核记录

审核日期：2026-09-13
分支：`oceanpilot-v2`
基线 HEAD：`eb46b08d45d8b87c96b38a8248f890160aea436d`

本记录覆盖推进计划的“批次 3：任务与材料体验”。验证使用当前工作树、
`work/stage1-review/` 独立 SQLite 数据和 8014 本地服务；验证结束后服务已停止。

## 审核结论

批次 3 的开发者验收门禁通过：商户无需填写内部 evidence code 或材料标题；材料卡同时说明
用途、应含字段、来源方式、关键性、示例和当前内容核查状态；可下载的三类合成样例与当前
案件交易事实绑定，重新上传后仍走真实保存、哈希、解析、内容检查、版本和审计链路。

实际完成了“缺材料 → 上传缺字段版 → 明确指出缺项 → 上传修订版 → 提交 OP 审核”的连续
演练。浏览器复核同时发现并修正了一个真实问题：案件进入 `OP_REVIEW` 后，商户首页曾把
仍可选的“补充材料”误升为“你的下一步”；现在主任务严格绑定服务端 `current_task`，页面
显示“当前进展 / 独立风控审核员 / OP 人工审核”，补充修订仅保留为材料页的次要操作。

本记录不是未参与开发人员的无引导可用性测试，后者仍待执行。

## 已改代码

- 材料内容合同集中到领域目录，计划接口的 checklist 新增说明、应含字段、示例、
  `expected_source` 与 `upload_status`，UI 不再用 `present=true` 表达“审核通过”。
- 新增授权读取接口
  `GET /api/v2/cases/{case_id}/collaboration/samples/{code}`；仅 MOCK 且
  `production_eligible=false` 的案件可用，只允许当前规则清单中的已支持结构化材料。
- 每份样例明确写入“测试材料 / 合成数据”，并提供 `sufficient`、`missing_field`、
  `wrong_transaction` 三种变体；跨商户访问仍返回 404。
- 上传表单从自由输入 code/title 改为当前 checklist 下拉选择；服务端仍按所选代码、案件权限
  和 revision 校验，浏览器选项不构成授权。
- 商户页新增“收到争议 → 选择处理方式 → 准备材料 → OP 审核 → 上游处理 → 结果跟踪”阶段条。
- 材料已提交后显示“等待 OceanPayment 审核 / 查看审核进度”，不再显示可重复提交的禁用主按钮。
- 商户文件记录显示文件名、上传时间和内容核查反馈，不默认暴露 `object:` 引用或无关 UUID。
- Agent 文本的粗体、行内代码、标题和简单 Markdown 表格经过安全转换；表格分隔符不再原样显示，
  仍不开放任意 HTML。
- 案件主操作不再回退为“当前角色任意一个可执行动作”；只有服务端计划指定的当前动作同时可执行
  时才成为主操作。

## 真实连续演练

案件：`OPV2-d0d9ee31gce1e6e22`
交易：`stage1-review-transaction-001`
材料：签收证明 `fulfillment.proof_of_delivery`
最终状态：`OP_REVIEW`，revision 7，当前任务 `REVIEW`，负责人“独立风控审核员”。

| 顺序 | HTTP 请求 | Payload 摘要 | Status / 结果 |
| --- | --- | --- | --- |
| 1 | `POST /api/v2/commands` | `CONFIRM_RULE`；单项签收证明；明确三段期限 | 200，规则进入已确认状态 |
| 2 | `POST /api/v2/commands` | `PUBLISH_TASK`；要求上传匹配本案交易的签收证明 | 200，任务向商户发布 |
| 3 | `POST /api/v2/commands` | `MERCHANT_DECISION / CONTEST` | 200，进入 `EVIDENCE_COLLECTING` |
| 4 | `GET /api/v2/cases/OPV2-d0d9ee31gce1e6e22/collaboration/samples/fulfillment.proof_of_delivery?variant=missing_field` | 无 | 200，下载本案缺字段合成 JSON |
| 5 | `POST /api/v2/cases/OPV2-d0d9ee31gce1e6e22/collaboration/files` | 缺少 `delivered_at` 的实际文件内容 | 200，`content_check=INSUFFICIENT`；计划 `present=false` |
| 6 | 同一 sample GET，`variant=sufficient` | 无 | 200，下载与本案交易、金额、币种匹配的修订样例 |
| 7 | 同一 files POST | 带原 `evidence_id` 的修订文件 | 200，`content_check=SUPPORTED`；旧版本保留历史 |
| 8 | `POST /api/v2/commands` | `SUBMIT_EVIDENCE`，绑定当前 revision | 200，进入 `OP_REVIEW`，当前负责人切换到 Risk Officer |

缺字段版本的计划响应明确返回：`present=false`、`upload_status=INSUFFICIENT`、
`expected_fields=[delivered_at, recipient_confirmation]`。修订后返回：`present=true`、
`upload_status=SUPPORTED`、`next_action=SUBMIT_EVIDENCE`。

## 浏览器验收

使用商户 A 的真实 cookie 会话打开最终案件并核对：

- 首页主任务为“OP 人工审核”，负责人为“独立风控审核员”，没有把补件描述成商户当前主任务。
- 六阶段条当前停在“OP 审核”。
- 材料卡显示“为什么需要、应包含、获取方式、常见示例、关键材料、已上传待整包审核”。
- 足够版、缺字段版、错交易版均有同案授权下载链接。
- 上传区域只有“这份文件对应哪项材料”和“选择实际文件”，没有内部代码或标题输入。
- 文件记录显示 `stage3-proof-sufficient.json` 和实际时间，不显示 `object:` 引用。
- 页面显示“材料已提交，等待 OceanPayment 审核”，不提供重复提交按钮。
- 浏览器有效宽度 694 px 时 document scroll width 679 px，无横向溢出；Console 无错误。

## 自动化结果

- 新增/相关专项：**161 passed**，2 warnings。
- OpenAPI 路径合同补齐后相关合同：**39 passed**，2 warnings。
- 全库最终：**2197 passed / 6 skipped**，2 warnings，100.41 秒。
- Ruff lint、272 个 Python 文件格式检查、字节编译和 `git diff --check` 通过。

6 个跳过项仍为未配置的 DeepSeek/Claude 实时密钥、本机缺少 PowerShell；两条 warning 是既有
Starlette TestClient 与 AnyIO 弃用提示。

## 边界与后续

- 样例是按当前合成案件即时生成的 JSON，不是生产材料模板；未知自定义材料没有伪造样例。
- 当前只检查 UTF-8 TXT、JSON 和单行 CSV 的结构化内容，没有声称支持真实 PDF/OCR。
- `SYSTEM_OF_RECORD` 和 `CONDITIONAL` 项在 UI 中说明由 OceanPayment 或实际事实决定，不把
  “预期系统可得”误标为文件已存在；`MERCHANT_UPLOAD` 与 `OCR_THEN_REVIEW` 才提供商户上传入口。
- 未参与开发人员的无引导试用、每个最终核心场景包的逐一浏览器验收留到批次 5。
- Stage 0 已登记的关键证据覆盖和 SLA 计算问题仍未修改，留给批次 4。
- 尚未开始接受建议、SLA、回执未知、终局按钮等批次 4 工作。
