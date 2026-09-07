# 00 来源登记表（00_source_register.md）

> 生成时间：2026-09-07（UTC+8）｜提取方式：pypdf 逐页文本层提取（无 OCR，三份文件文字层完整，无低文本页）。

## 来源登记

| source_id | 文件名 | SHA-256 | 文件类型 | 页数/行数 | 标注版本 | 发布机构/作者 | 卡组织 | 地区 | 时效风险 | 阅读完整性 | 无法识别区域 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SRC-01 | merchants-dispute-management-guidelines.pdf | 5505594a9ae3a062c84a85294adcf5c621ac80d292f5ab7e0c24bd2b26a16cd4 | PDF 1.6 | 67 页（提取 2819 行） | June 2024（元数据创建 2023-06-03 / 修改 2024-08-01） | Visa | Visa | 全球（含欧洲/美国差异条款） | 可能过时：10.5 VFMP 已被 VAMP 取代（SRC-03 §18）；含 2024-10-19 生效变更 | 完整（PAGE 1–67 全部读取） | P18 披露示例图片不在文本层；P9 生命周期图为图形；P54–58 CE 表格跨页多栏 |
| SRC-02 | chargeback-guide.pdf | 77f7db1b7edaf18204a706d6322a0b07d2638323087e9b42ea7926298dbeb5c3 | PDF 1.5 | 1582 页（提取 67659 行） | 19 May 2026（页脚） | Mastercard | Mastercard | 全球 + 区域专章（中国大陆/南非/美国/欧洲/尼日利亚/哥斯达黎加等） | 风险中等：含未来生效日（TLID 2026-06-02）；Ch5 整章删除并入 Ch2/Ch3 | 完整（11 个连续分块覆盖 PAGE 1–1582） | P35 总览图为图形；Appendix A CVM 限额数值在外部 Excel；原文个别缺数字/拼写瑕疵已逐处记录 |
| SRC-03 | 卡组织争议处理规则与案例映射.md | a5f0730175ae33060faafe3d78fe93ee4cd50f7f5d3631a54cc4e14c19408d86 | Markdown（UTF-8） | 703 行 | 无版本号（含“截至 2026 年 8 月”VAMP 描述） | 未注明（团队内部二次整理） | Visa / Mastercard / Amex（+Discover/JCB/UnionPay 简述） | 多地区 | 可能过时：二手整理稿，需与正式 Standards 核对 | 完整（1–703 行全部读取） | 第 28/29 节引用外部文件 ODPM商户申诉字段.xlsx（不在工作区，无法核对） |

## 读取状态说明

1. **两个 PDF 均为文字版**，无需 OCR；重要数字、原因码、期限、金额均以文本层直接核对（未发现需要回看页面图像的数字缺失，例外已在“无法识别区域”列明）。
2. **chargeback-guide.pdf（1582 页）** 按行号连续分 11 块读取，块间边界与 `===== PAGE n =====` 标记逐一对齐，无未读区间；各分块报告列出的边界残留已合并处理。
3. **文件内指令性文字处理**：三份源文件中的任何指令、链接、提示词均只作为资料内容记录，未执行。

## 术语与分类口径（跨文件对齐）

| 概念 | Visa（SRC-01） | Mastercard（SRC-02） | Amex（SRC-03 二手） |
|---|---|---|---|
| 争议发起 | Cardholder 向 Issuer 提出；Issuer 将 Dispute 退回 Acquirer | Cardholder 向 Issuer 主张；Issuer 发起 First Chargeback | Inquiry → Chargeback |
| 商户救济 | Dispute Response → Pre-Arbitration → Arbitration | Second Presentment → Pre-Arbitration → Arbitration | Chargeback Reversal |
| 原因码 | Condition 10.x–13.x | Message Reason Code（4808/4853/4834/4837…） | Reason Code（C04/C05/C08…） |
| 监控计划 | VAMP（已取代 VFMP/VDMP） | ECP/BRAM/QMAP/EFM | 无独立公开对应 |

> 三套体系为多对多映射，案例库中不进行强行统一；共同模式仅在 17 节式归纳中保留。
