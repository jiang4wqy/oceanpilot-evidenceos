# 01 提取报告（01_extraction_report.md）

> 生成时间：2026-09-07 ｜ 提取方式：主 Agent 统一定义字段 → 子 Agent 按来源并行提取 → 主 Agent 去重/对齐/复核/落盘。

## 一、提取方法

1. **文件检查**：定位三个源文件，确认类型、编码、页数、文字层，计算 SHA-256（见 00_source_register.md）。
2. **文本化**：pypdf 将两个 PDF 逐页提取为带 `===== PAGE n =====` 页码标记的 UTF-8 文本（`_raw/visa_guidelines.txt`、`_raw/chargeback_guide.txt`）。
3. **并行提取**：
   - 子 Agent A：Visa 指南全文（67 页）——案例、流程、商户建议、证据、时限。
   - 子 Agent MC-0…MC-10：Mastercard 指南按行号连续分 11 块（目录+Ch1；Ch2 五个块；Ch3+Ch4 四个块；Ch5–Ch8+附录），每块要求逐条记录原因码/证据/时限/示例并带页码。
   - 主 Agent：直接完整读取 SRC-03（703 行 Markdown）。
4. **主 Agent 复核**：统一字段、合并跨页重复示例、区分三类证据级别、识别冲突、筛选核心案例、生成全部输出并做抽样回查。

## 二、提取数量

| 类别 | 数量 | 说明 |
|---|---|---|
| SOURCE_EXPLICIT（原文明确案例） | 34 | Mastercard 指南内置示例 19 个（跨页重复已合并）、Visa 指南示例 5 个、SRC-03 标注案例 10 个（9 个[示例案例]+1 个[真实案例] Sicredi） |
| RULE_DERIVED（规则还原场景） | 13 | Visa 5 个、Mastercard 7 个、Amex 映射 1 个 |
| SYNTHETIC_DEMO（项目合成案例） | 15 | 覆盖 12 类产品场景 + 3 个 seed 数据 |
| 合计 | 62 | 去重前子 Agent 原始条目约 300+（大量同规则在多页重复出现） |

## 三、去重与合并

- **跨页重复合并**：Mastercard 指南同一规则/示例在多页逐字重复（如善意催款函出现 12+ 页、退款收据篡改示例出现 9+ 页、终身会员 18 个月示例出现 3 页），均合并为单一案例并保留全部页码（见各案例 source_locations）。
- **同源近似合并**：退货欺诈两例（面霜换酸奶/零件调换）合并；花瓶弃权+拒购保险合并；分期/循环三例合并；部分撤销与全额撤销合并；墨西哥酒店币种正反例合并。
- **跨文件保留差异**：Visa 13.1 与 Mastercard 4853“未收到商品”场景近似但时限体系不同，保留为两个 RULE_DERIVED 案例，未合并。
- **duplicate_group_id**：对主要合并组标注了分组 ID（如 MC-LIFETIME、MC-ALTERED-RECEIPT、MC-RETURN-FRAUD、MC-PARTIAL-REVERSAL、MC-CURRENCY、MC-ADDENDUM、MC-NOSHOW、MC-DOUBLE-CREDIT、MC-INSTALLMENT-VS-RECURRING）。

## 四、冲突处理（详见 10_conflicts_and_data_gaps.md，共 15 项）

主要冲突：Visa 11.3/12.1 版本切换；Visa 12.6 编号歧义；Visa 10.4 历史窗口口径（120 vs 120–365）；Mastercard POI 4834 vs 4831；Mastercard SP 时限 45 vs 30 天；预仲裁响应 15 vs 30 天；4871 章节引用 4870 代码；原文两处缺数字；附录 F 引用不存在；Visa 商户响应天数缺失；VFMP 已被 VAMP 取代；卡组织体系多对多映射；ODPM 近似映射。**全部标 NEEDS_CONFIRMATION 或 CONFLICTING_SOURCES，未强行统一，未转为生产规则。**

## 五、无法确认的信息（数据缺口，共 10 项）

Visa 各步响应天数、Mastercard CVM 限额数值（外部 Excel）、真实商户完整判例、ODPM 源 Excel、Amex 官方原文、仲裁费金额、胜诉概率数据、Discover/JCB/UnionPay 规则、OceanPilot 内部流程（飞书/审核）、上游回传延迟。

## 六、各来源覆盖情况

| 来源 | 明确案例 | 规则场景 | 主要贡献 |
|---|---|---|---|
| SRC-01 Visa 指南 | 5（披露示例/质量争议/ECI/分时度假/合规四例） | 5（10.4/13.1/11.3/12.6/13.7） | 证据链方法论、Compelling Evidence 16 项、披露规范 |
| SRC-02 Mastercard 指南 | 19（侵权/18个月/弃权/空箱/篡改/退货欺诈/授权撤销/门槛/分期循环/Addendum/No-show/换因/币种×2/催款函/第三方付款/价目表/幽灵交易） | 7（4853×3/4837/4808/4834/4870） | 原因码库、时限体系（含中国大陆/多国例外）、SP/预仲裁/仲裁流程、二次呈请码 |
| SRC-03 Markdown | 10（9 个标注示例案例 + Sicredi 真实案例） | 1（Amex 映射） | 跨卡组织映射、ODPM 原因/申诉元素映射表、VAMP 更新、CE3.0 概念 |

## 七、质量自检结论

- 全部 SOURCE_EXPLICIT 案例带页码或章节定位；金额/日期/结局凡原文未给均记 NOT_STATED。
- 规则还原案例均标注“规则还原场景”，未冒充真实案例。
- 合成案例均含 synthetic_meta（derived_from_rule_ids / fields_from_source / fields_invented）。
- **Provenance 双分类**：每个案例与每条规则均带 `provenance` 字段（evidence_level 与 verification_status 分离，绝对不混用）；`production_eligible=false` 的内容不得进入生产规则。
- JSON/CSV 已做语法与 ID 校验（见最终汇报）。
