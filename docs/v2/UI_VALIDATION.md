# V2 工作台浏览器验收

验证日期：2026-09-08。使用本地 FastAPI、独立合成数据库与 Headless Chrome；所有案件、证据引用、资金事件与回执均为 `SYNTHETIC_DEMO`，上游提交为 Mock。

## 已验证流程

- A 正常抗辩：从运营工作台加载演示案件，经商户门户明确 Contest、逐项登记 6 项证据、提交审核；切换风控角色审核通过；运营生成草稿；主管确认 PII 检查并冻结；运营 Mock 提交并读取回执、登记终局 WON 与返还资金；主管核对、运营通知、主管关闭。全部操作通过界面表单执行，案件从 v2 推进至 v19。
- A 知识复用：关闭后由运营提取脱敏知识候选，再从治理页面由管理员审核批准，案件推进至 v21。
- D 财务异常：通过界面加载终局且有资金差异的案例；主管重新核对实际净影响，运营通知商户，主管关闭。差异状态在修正前可见，未因 WON 自动关闭。
- B / C：通过界面分别加载关键证据缺失与 SLA 超期案例；队列、准备度、下一步和角色要求正确显示。C 的未响应处理仍需人工记录，界面不将其自动视为 Accept。

上述浏览器操作未产生 JavaScript 页面错误。商户视图在 320、390、600、780、1024、1512 像素宽度下均未产生页面横向溢出。

## 自动化边界验证

`PYTHONPATH=src .venv/bin/python -m pytest tests/web/test_v2_rendering.py -q`

结果：13 passed。覆盖自包含资源、商户与 Agent 权限控件、XSS 转义、多维队列、异步案件选择隔离、旧版计划失效、旧版人工确认拒绝、未知规则不默认猜测可用权利，以及结果不确定时保留原命令 ID / 角色 / revision 重试。金额显示另验证 USD、JPY、KWD 不同最小货币单位，无法格式化时保留原始单位。

Ruff 检查通过；浏览器脚本语法检查通过。

## 截图

- [运营工作台](screenshots/operations-desktop.png)：A / B / C / D 队列，D 终局与资金差异独立显示。
- [商户门户](screenshots/merchant-desktop.png)：B 缺证案例。
- [商户移动视图](screenshots/merchant-mobile.png)：390 像素宽度。
- [Mock 提交回执](screenshots/submission-receipt.png)：冻结证据包、人工审核和回执。
- [资金差异](screenshots/financial-discrepancy.png)：D 核对前。
- [关闭条件](screenshots/closed-financial.png)：D 核对、通知并关闭后。
- [平台治理](screenshots/governance-desktop.png)：规则、权限、集成状态与已批准知识。

截图不包含真实商户资料、文件正文或支付凭据。证据功能登记对象引用和元数据，不上传或解析原始文件；飞书与生产身份认证仍按治理页面报告的实际配置状态展示。

## OceanPilot 常驻智能体与三方协作追加验收

商户客户端以 OceanPilot 对话、我的待办、证据准备与 OceanPayment 反馈为核心；运营端保留完整案件流程与常驻 Agent 侧栏。两端明确区分商户、OceanPayment、OceanPilot 三方责任，不新增独立 Agent 页面。

- 浏览器确认：未编辑的已保存商户任务提案经人工勾选确认，调用案件提案 `/execute` 接口，返回 200；补填材料引用后，改走普通版本化命令，证据登记成功。
- 商户客户端实际发送案件问题，返回 `source=MODEL`、`provider=DEEPSEEK`、实际 `model=deepseek-v4-flash`。界面同时保留确定性工具记录与模型回答各自来源，不将工具检查宣传成模型推理过程。
- 商户继续登记一份材料后，案件推进至 v6，自动收到 `AUTO_EVENT:REGISTER_EVIDENCE` 的真实模型跟进（`MODEL / DEEPSEEK / deepseek-v4-flash`）；工具观察与模型解读均关联 v6，后台待处理状态归零，浏览器无 JavaScript 错误。
- 保存的提案必须匹配案件 revision 与 owner；旧版提案失效，需要人工补充输入或修改字段的提案走普通命令。Agent 轮询保留未发送文本，切换案件或角色后不展示先前请求的迟到回答。
- 追加 UI 回归合计 21 passed，包括真实首屏缺少输入元素、来源区分、XSS、原提案确认、编辑与必填提案回退、owner 权限和迟到回答隔离。商户端六种屏宽未出现页面横向溢出。

新截图：[运营 Agent](screenshots/agent-operations.png)、[商户客户端](screenshots/agent-merchant.png)、[移动客户端](screenshots/agent-mobile.png)、[提案人工确认](screenshots/agent-proposal-confirmation.png)、[已完成工具记录](screenshots/agent-tools.png)。
