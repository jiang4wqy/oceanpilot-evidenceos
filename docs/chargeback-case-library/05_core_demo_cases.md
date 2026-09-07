# 05 核心演示案例（05_core_demo_cases.md）

> 筛选原则：①真实业务痛点；②原因/行业代表性；③证据明确；④能展示 Agent 与人工确认；⑤能展示快照/审计/权限；⑥正常与异常路径；⑦来源可定位；⑧非专业评委可懂；⑨不依赖外部系统。
> 共筛选 **20 个核心案例**（JSON 中 core=true；SOURCE_EXPLICIT 7 + RULE_DERIVED 1 + SYNTHETIC_DEMO 12），本文件列出演示编排。

## 一、核心案例清单

| # | case_template_id | 标题 | 类别 | 演示主题 |
|---|---|---|---|---|
| 1 | CB-CASE-034 | Sicredi × Ethoca Consumer Clarity | SOURCE_EXPLICIT | 路演开场故事（唯一真实案例） |
| 2 | CB-CASE-025 | Visa 10.4 SGD 899 未授权 | SOURCE_EXPLICIT | 欺诈 CE3.0 证据链 |
| 3 | CB-CASE-026 | Visa 13.1 iPhone USD 1,200 未收到 | SOURCE_EXPLICIT | 未收货证据链（Tracking→POD） |
| 4 | CB-CASE-031 | MC 4853 课程 USD 499“无法访问” | SOURCE_EXPLICIT | 数字商品消费日志 |
| 5 | CB-CASE-027 | Visa 13.2 SaaS 取消后扣款 | SOURCE_EXPLICIT | 订阅时间线 |
| 6 | CB-CASE-002 | 终身会员 18 个月折算 USD 833 | SOURCE_EXPLICIT | 金额计算规则 |
| 7 | CB-CASE-001 | 油漆工泼漆（侵权不适用） | SOURCE_EXPLICIT | 规则边界 |
| 8 | CB-CASE-040 | Visa 10.4 规则还原场景 | RULE_DERIVED | 规则引擎基准 |
| 9 | CB-CASE-060 | 证据充分抗辩（正面主路径） | SYNTHETIC_DEMO | 全模块串联演示 |
| 10 | CB-CASE-061 | 证据缺失阻止提交（负面路径） | SYNTHETIC_DEMO | 阻断+接受+飞书 |
| 12 | CB-CASE-062 | 规则直判接受（4808 无授权） | SYNTHETIC_DEMO | 规则直判+接受 |
| 13 | CB-CASE-063 | 临近截止飞书提醒 | SYNTHETIC_DEMO | 飞书提醒 |
| 14 | CB-CASE-064 | 已过期案件 | SYNTHETIC_DEMO | 状态机 |
| 15 | CB-CASE-065 | 文件抽取人工修正 | SYNTHETIC_DEMO | OCR 低置信修正 |
| 16 | CB-CASE-066 | Agent 提案+用户确认 | SYNTHETIC_DEMO | Agent 交互与审计 |
| 17 | CB-CASE-067 | 提案 revision 过期被拒 | SYNTHETIC_DEMO | 并发控制 |
| 18 | CB-CASE-068 | 上游超时幂等重试 | SYNTHETIC_DEMO | 可靠性 |
| 19 | CB-CASE-069 | 跨租户访问阻断 | SYNTHETIC_DEMO | 安全 |
| 20 | CB-CASE-070 | 规则版本变化快照不变 | SYNTHETIC_DEMO | 版本管理 |
| 21 | CB-CASE-071 | 路演友好欺诈故事 | SYNTHETIC_DEMO | 路演叙事 |

## 二、推荐演示顺序（比赛路演剧本）

1. **开场（CB-CASE-034 + CB-CASE-071）**：用通俗故事讲“商户莫名其妙被扣钱”→ 引入友好欺诈与 OceanPilot 价值主张。
2. **正路径（CB-CASE-060）**：首页待办 → 证据链 → 准备度 95% → 草稿 → 人工确认 → 提交回执。覆盖首页/列表/详情/证据/准备度/草稿/材料包/审核/提交。
3. **负路径（CB-CASE-061）**：准备度 12%，系统阻止提交并建议接受，触发飞书提醒 → 接受。
4. **Agent 交互（CB-CASE-066）**：Agent 生成提案 → 用户确认 → 执行留痕；再演示（CB-CASE-067）并发更新导致 revision 过期。
5. **可靠性（CB-CASE-068）**：上游超时 → 幂等重试 → 唯一回执。
6. **安全与版本（CB-CASE-069 / CB-CASE-070）**：跨租户 403；历史案件快照不受新版本规则影响。
7. **收尾（CB-CASE-002 / CB-CASE-001）**：用“18 个月折算 833 美元”“油漆工泼漆不能拒付”两个规则故事展示专业性。

## 三、每个核心案例的操作路径

- **CB-CASE-060**：首页待办（置顶）→ 案件列表 → 详情证据链视图 → 准备度评估 → 生成草稿与材料包 → 人工确认 → 审核 → 上游提交 → 回执。验收断言：准备度≥90、草稿引用规则、幂等键唯一。
- **CB-CASE-061**：首页低准备度标记 → Agent 解释 CE 缺失 → 提交按钮禁用并展示原因 → 一键接受 → 飞书通知。断言：提交被阻止、建议=ACCEPT、原因引用规则。
- **CB-CASE-062**：规则直判 4808 → 建议接受 → 一键接受。断言：建议=ACCEPT。
- **CB-CASE-063**：飞书卡片（T-72h）→ 点击跳转案件 → 提交。断言：卡片含截止时间与链接。
- **CB-CASE-064**：已过期分组 → 详情锁定状态 → Agent 复盘。断言：状态=EXPIRED、提交被禁。
- **CB-CASE-065**：证据页低置信字段高亮 → 人工比对原件修正 → 重新校验 → 提交。断言：修正后校验通过。
- **CB-CASE-066**：Agent 面板提案预览（含规则引用）→ 用户确认 → 执行 → 审计留痕。断言：提案含规则引用、确认后执行、审计完整。
- **CB-CASE-067**：确认弹窗报“案件已更新”→ 基于最新版本重新生成 → 确认提交。断言：过期提案被拒、新提案成功。
- **CB-CASE-068**：提交转圈提示重试 → 自动幂等重试 → 成功回执 → 审计展示“一次业务提交+两次网络重试”。断言：无重复提交、回执唯一。
- **CB-CASE-069**：跨租户 URL 访问 → 403 → 安全审计告警。断言：403、审计留痕。
- **CB-CASE-070**：历史案件显示规则版本 2026-05 → 新案件使用 2026-06 → 对比说明。断言：快照版本号正确。

## 四、推荐路演故事（通俗版）

见 11_plain_language_casebook.md 的“路演三分钟故事”。

## 五、演示依赖说明

- 合成案例中“截止时间”“飞书提醒阈值（T-72h）”“准备度阈值”“revision 机制”“幂等重试”均为 OceanPilot 产品设定，无卡组织原文依据，已在各案例 synthetic_meta 标注。
- 唯一真实案例（Sicredi）来自卡组织官方营销资料，非仲裁判例，演示时须表述为“官方公开案例”，不得宣称“胜诉判例”。
