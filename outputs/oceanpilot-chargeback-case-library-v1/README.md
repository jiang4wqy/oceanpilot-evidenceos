# OceanPilot 公开拒付案例库 v1

本目录包含 12 个公开最终决定案例和 24 个规则推演合成案例。主文件为 `OceanPilot_拒付案例库_v1.xlsx`。

## 怎么用

1. 在“案例总表”按理由族、行业或特殊标签筛选。
2. 到“处理流程”查看每一步责任人、产出和升级条件。
3. 到“证据明细”查看已有/缺失证据和缺失影响。
4. 把 recommendation/product_gap 转为产品规则、回归测试或导师确认问题。

## 文件

- `cases.csv`：一案一行。
- `case_steps.csv`：一案多步骤。
- `evidence_items.csv`：一案多证据。
- `sources.csv`：来源和适用范围。
- `synthetic_case_samples.import.json`：仅 24 个合成案例，可用项目校验器导入。

## 重要边界

公开案例是对公开文书的事实摘要；FOS裁决通常评价金融机构是否公平处理，不等同卡组织仲裁结果。合成案例结果均为“模拟预期”，不代表Oceanpayment真实规则或胜诉率。本库不含PII、真实订单号、IP/设备指纹原值或任何凭据。

## 校验

`oceanpilot-validate-data --case-samples outputs/oceanpilot-chargeback-case-library-v1/synthetic_case_samples.import.json`
