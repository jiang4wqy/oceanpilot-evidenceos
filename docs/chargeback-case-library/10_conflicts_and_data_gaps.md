# 10 冲突与数据缺口（10_conflicts_and_data_gaps.md）

## 一、来源间冲突（15 项，均未强行统一）

| ID | 冲突 | 来源 | 可能原因 | 状态 |
|---|---|---|---|---|
| CONFLICT-001 | Visa 11.3（2024-04-13 起）与 12.1（至 2024-04-12）版本切换 | SRC-01 P2/P9/P31-32 | 版本切换 | NEEDS_CONFIRMATION（落库带 effective_date） |
| CONFLICT-002 | Visa 12.6 编号歧义（目录 vs 正文 12.6.1/12.6.2） | SRC-01 P2/P37-38 | 排版 | NEEDS_CONFIRMATION |
| CONFLICT-003 | Visa 10.4 历史交易窗口“120 天”vs“120–365 天” | SRC-01 P26 | 同规则两种表述 | CONFLICTING_SOURCES |
| CONFLICT-004 | Mastercard POI 4834 vs 4831 | SRC-02 目录 P11/P25、正文 | 章节模板差异+编码合并 | NEEDS_CONFIRMATION |
| CONFLICT-005 | Mastercard 淘汰码仍在消息模板中列作可选 | SRC-02 多处 | 编码合并进行中 | NEEDS_CONFIRMATION（需合并映射表） |
| CONFLICT-006 | Mastercard SP 时限 45 vs 30 天 | SRC-02 P66/P104/P119/P929/P1001/P1207 | 模板新旧混杂 | CONFLICTING_SOURCES |
| CONFLICT-007 | 预仲裁响应 15 vs 30 天 | SRC-02 P931/P944-945 | 章节差异 | NEEDS_CONFIRMATION |
| CONFLICT-008 | 仲裁提交 10 vs 15 天 | SRC-02 P932/P947 | 章节差异 | NEEDS_CONFIRMATION |
| CONFLICT-009 | 4871 章节仲裁消息文本写 4870/70 | SRC-02 P635-636 | 复制残留 | CONFLICTING_SOURCES |
| CONFLICT-010 | 原文两处缺数字（P248/P1020，对照应为 15 天） | SRC-02 | 源文档缺陷 | NEEDS_CONFIRMATION |
| CONFLICT-011 | 附录 F 引用不存在 | SRC-02 P38/P1430/P1486 | 引用未更新 | NEEDS_CONFIRMATION |
| CONFLICT-012 | Visa 商户响应天数缺失 vs MC 有明确天数 | SRC-01 P12 | 披露习惯差异 | CONFLICTING_SOURCES |
| CONFLICT-013 | Visa VFMP（10.5）已被 VAMP 取代 | SRC-01 P28 vs SRC-03 §18 | 版本时效 | CONFLICTING_SOURCES |
| CONFLICT-014 | 三大卡组织分类体系多对多、生命周期不同 | SRC-03 §1/§28/§29 | 体系差异 | CONFLICTING_SOURCES（不合并为统一规则） |
| CONFLICT-015 | ODPM 映射表中带 * 的近似映射与中英文不一致 | SRC-03 §28 | 渠道差异+未核对 | NEEDS_CONFIRMATION |

## 二、规则版本风险

1. SRC-01 为 June 2024 版：正文含 2024-10-19 生效变更、10.5 VFMP 已被 VAMP 取代——**10.5 相关演示不得引用本指南口径**。
2. SRC-02 为 2026-05-19 版：含未来生效日（TLID 2026-06-02）与 First-Party Trust 分阶段生效（2024-10-27→2026-01-21→2026-04-19）——**测试断言必须带版本参数**。
3. SRC-03 为内部二次整理稿且无日期——**ODPM 映射表需与源 Excel 复核**。
4. 落库字段建议：`rule_version` + `effective_date` + `expiry_date`（SRC-03 §27 已给出 schema 参考）。

## 三、缺失字段清单

| 缺失项 | 出处 | 处理 |
|---|---|---|
| Visa 各步响应具体天数 | SRC-01 | 待收单机构确认（GAP-001） |
| Mastercard CVM 限额数值 | SRC-02 Appendix A | 需外部 Excel（GAP-002） |
| 真实商户完整判例 | 三份资料 | 用合成案例替代，标注（GAP-003） |
| ODPM商户申诉字段.xlsx | 工作区缺失 | 向业务方索取（GAP-004） |
| Amex 官方原文 | 仅二手映射 | 获取原文后再落库（GAP-005） |
| 仲裁费金额 | 无 | 从收单费率表确认（GAP-006） |
| 胜诉概率数据 | 无 | 只展示完整度（GAP-007） |
| Discover/JCB/UnionPay 规则 | 仅简述 | 二期补充（GAP-008） |
| 飞书提醒/人工审核产品流程 | 无资料 | 产品自定，标注合成（GAP-009） |
| 上游回传延迟 | 无资料 | 联调实测（GAP-010） |

## 四、未覆盖场景（三份资料均无法支持）

1. BNPL（Klarna/Affirm）、DCB、KakaoPay 等替代支付方式的争议规则——SRC-03 §28 明确这些渠道无卡组织编码，需单独获取渠道规则。
2. 跨币种退款的汇率损失以外的复杂资金场景。
3. 卡组织未公开的仲裁内部判例。

## 五、需业务/支付专家确认的问题（NEEDS_CONFIRMATION 汇总）

1. Visa 各步响应天数与收单机构实际执行值。
2. Mastercard 冲突条款（CONFLICT-006/007/008）以哪一版本生效。
3. ODPM 原因编号 73（中英文不一致）与带 * 映射的真实含义。
4. Amex C 系列编码的证据要求与时限。
5. 飞书提醒阈值、准备度阻断阈值等产品参数取值。
6. 商户实际使用的收单机构与支持的卡组织范围（决定第一期规则范围）。

## 六、不可直接用于生产的内容

1. 全部 CONFLICTING_SOURCES 与 NEEDS_CONFIRMATION 条目（15 项冲突）不得直接转为生产规则。
2. Amex 规则（仅二手映射）。
3. 合成案例中的产品设定（截止时间、阈值、revision、幂等）仅为演示设计。
4. Sicredi 营销案例不得作为规则依据。
5. “MERCHANT_WON”等路演结局仅为演示设定，非真实裁决。
