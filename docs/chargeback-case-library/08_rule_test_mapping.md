# 规则测试映射（08_rule_test_mapping.md）

> 生成时间：2026-09-07T15:34:14Z。将案例映射到原因码、规则版本、证据要求、预期判断、阻塞条件、边界条件与测试断言。
> 警告：表中时限存在地区差异与版本差异（见 10_conflicts_and_data_gaps.md），生产规则须以卡组织正式 Standards 为准。

## American Express｜C04｜Goods/Services Returned or Refused

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 ['CONFLICT-014']｜期限政策 未说明（需收单机构确认）｜生产可用 否｜来源 SRC-03
- **规则定位**：§15（第 15 章）

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-032 | §15（第 15 章） | 条件性 | 无物流记录时提示补证 | 见 10 冲突清单 | 退货判定正确 |

## American Express｜C05｜Goods/Services Cancelled

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 ['CONFLICT-014']｜期限政策 未说明（需收单机构确认）｜生产可用 否｜来源 SRC-03
- **规则定位**：§16（第 16 章）

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-033 | §16（第 16 章） | 抗辩 | 时间证据缺失时提示 | 见 10 冲突清单 | 时间判定正确 |

## American Express｜C08 / C02｜Goods/Services Not Received / Credit Not Processed

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 ['CONFLICT-014']｜期限政策 未说明（需收单机构确认）｜生产可用 否｜来源 SRC-03
- **规则定位**：SRC-03 §28

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-052 | SRC-03 §28 | 信息不足 | Amex 规则未确认时禁止自动判责 | 见 10 冲突清单 | 明确提示规则未确认 |

## Mastercard｜2011（Refund previously issued）｜Credit Previously Issued

- **Provenance**：验证状态 CONFLICTING_SOURCES｜冲突 ['CONFLICT-006']｜期限政策 存在版本差异（见冲突清单）｜生产可用 否｜来源 SRC-02
- **规则定位**：P38；P510-512；P68-69；P935

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-016 | P38; P68-69; P510-512; P935 | 抗辩 | 未记录退款禁止提交 | 见 10 冲突清单 | 退款匹配正确 |

## Mastercard｜4808｜Authorization-related Chargeback

- **Provenance**：验证状态 CONFLICTING_SOURCES / VERIFIED_EXTRACTED｜冲突 ['CONFLICT-006']｜期限政策 存在版本差异（见冲突清单） / 明确 / 未说明（Visa 需收单机构确认 / 演示设定）｜生产可用 否｜来源 SRC-02
- **规则定位**：P115；P56-57；P61；P64-65；P84；P885-886；P921-922；P934；SRC-02 P54-150/P880-947；合成案例，无原文定位（见 derived_from_rule_ids）

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-007 | P64-65; P84; P934 | 抗辩 | 比对失败则建议接受 | 见 10 冲突清单 | 金额校验结果正确 |
| CB-CASE-008 | P61; P885-886 | 抗辩 | 无 | 见 10 冲突清单 | 门槛判定正确 |
| CB-CASE-009 | P115; P921-922; P56-57 | 抗辩 | 无 | 见 10 冲突清单 | 限额判定正确 |
| CB-CASE-049 | SRC-02 P54-150/P880-947 | 条件性 | 无记录建议接受 | 见 10 冲突清单 | 判定正确 |
| CB-CASE-062 | 合成案例，无原文定位（见 derived_from_rule_ids） | 接受 | 规则命中直接建议接受 | 见 10 冲突清单 | 建议=ACCEPT |

## Mastercard｜4834｜Point-of-Interaction Error

- **Provenance**：验证状态 CONFLICTING_SOURCES / NEEDS_CONFIRMATION｜冲突 ['CONFLICT-004', 'CONFLICT-006']｜期限政策 明确 / 未说明（Visa 需收单机构确认 / 演示设定）｜生产可用 否｜来源 SRC-02, SRC-03
- **规则定位**：SRC-02 P685-776/P1324-1407；合成案例，无原文定位（见 derived_from_rule_ids）

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-050 | SRC-02 P685-776/P1324-1407 | 条件性 | 证据缺失建议接受 | 见 10 冲突清单 | 子类判定正确 |
| CB-CASE-073 | 合成案例，无原文定位（见 derived_from_rule_ids） | 接受 | 重复判定未确认禁止提交 | 见 10 冲突清单 | 判定正确 |

## Mastercard｜4834（ATM Cash and Currency Errors）｜Point-of-Interaction Error

- **Provenance**：验证状态 VERIFIED_EXTRACTED｜冲突 无｜期限政策 明确｜生产可用 是｜来源 SRC-02
- **规则定位**：P741；P872-873

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-015 | P741; P872-873 | 条件性 | 无 | 见 10 冲突清单 | 正反例判定正确 |

## Mastercard｜4834（Currency Errors）｜Point-of-Interaction Error

- **Provenance**：验证状态 VERIFIED_EXTRACTED｜冲突 无｜期限政策 明确｜生产可用 是｜来源 SRC-02
- **规则定位**：P1371；P741-742

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-014 | P741-742; P1371 | 条件性 | 无收据禁止提交 | 见 10 冲突清单 | 差额计算正确 |

## Mastercard｜4834（Duplicate / Paid by Other Means）｜Point-of-Interaction Error

- **Provenance**：验证状态 VERIFIED_EXTRACTED｜冲突 无｜期限政策 明确｜生产可用 是｜来源 SRC-02
- **规则定位**：P1327-1328；P690

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-017 | P690; P1327-1328 | 条件性 | 无 | 见 10 冲突清单 | 重复判定正确 |

## Mastercard｜4834（Unreasonable Amount）｜Point-of-Interaction Error

- **Provenance**：验证状态 VERIFIED_EXTRACTED｜冲突 无｜期限政策 明确｜生产可用 是｜来源 SRC-02
- **规则定位**：P1395；P770

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-018 | P770; P1395 | 抗辩 | 无 | 见 10 冲突清单 | 抗辩码=2700 |

## Mastercard｜4837｜No Cardholder Authorization

- **Provenance**：验证状态 CONFLICTING_SOURCES｜冲突 ['CONFLICT-006']｜期限政策 明确｜生产可用 否｜来源 SRC-02, SRC-03
- **规则定位**：SRC-02 P489-563；SRC-03 §28

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-048 | SRC-02 P489-563; SRC-03 §28 | 条件性 | 无 CE 建议接受 | 见 10 冲突清单 | 匹配正确 |

## Mastercard｜4853｜Cardholder Dispute

- **Provenance**：验证状态 CONFLICTING_SOURCES / NEEDS_CONFIRMATION / VERIFIED_EXTRACTED｜冲突 ['CONFLICT-006']｜期限政策 存在版本差异（见冲突清单） / 明确 / 未说明（Visa 需收单机构确认 / 演示设定）｜生产可用 否｜来源 SRC-02, SRC-03
- **规则定位**：P1103；P1106；P1112；P1511；P178；P368；P371；P381；P967；P968；SRC-02 P157-177/P953-967；SRC-02 P177-184/P967-983；SRC-02 P273-276/P1036-1051；SRC-03 §28；§12（第 12 章）；合成案例，无原文定位（见 derived_from_rule_ids）

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-002 | P178; P968; P1511 | 条件性 | 金额未确认禁止提交 | 见 10 冲突清单 | 金额=833.00；引用 P178/P968/P1511 |
| CB-CASE-003 | P178; P968; P1511 | 抗辩 | 弃权书缺失时不允许提交 | 见 10 冲突清单 | 证据齐全判定 PASS；规则引用页码正确 |
| CB-CASE-004 | P178; P967; P1511 | 抗辩 | 无证据时提交按钮禁用 | 见 10 冲突清单 | 规则引用正确；证据项校验生效 |
| CB-CASE-012 | P368; P371; P381; P1103; P1106; P1112 | 条件性 | 告知缺失建议接受 | 见 10 冲突清单 | 告知判定正确 |
| CB-CASE-031 | §12（第 12 章） | 抗辩 | 日志缺失阻止提交 | 见 10 冲突清单 | 证据链生成正确 |
| CB-CASE-045 | SRC-02 P157-177/P953-967; SRC-03 §28 | 条件性 | 证据不足阻止提交 | 见 10 冲突清单 | 路径与证据匹配 |
| CB-CASE-046 | SRC-02 P177-184/P967-983 | 条件性 | 无证明阻止提交 | 见 10 冲突清单 | 判定正确 |
| CB-CASE-047 | SRC-02 P273-276/P1036-1051 | 条件性 | 无记录建议接受 | 见 10 冲突清单 | 匹配正确 |
| CB-CASE-064 | 合成案例，无原文定位（见 derived_from_rule_ids） | 接受 | 提交入口锁定 | 见 10 冲突清单 | 状态=EXPIRED；提交被禁 |
| CB-CASE-066 | 合成案例，无原文定位（见 derived_from_rule_ids） | 抗辩 | 未确认前提案不执行 | 见 10 冲突清单 | 提案含规则引用；确认后执行；审计日志完整 |
| CB-CASE-067 | 合成案例，无原文定位（见 derived_from_rule_ids） | 抗辩 | revision 不匹配拒绝执行 | 见 10 冲突清单 | 过期提案被拒绝；新提案成功 |
| CB-CASE-074 | 合成案例，无原文定位（见 derived_from_rule_ids） | 抗辩 | 记录缺失阻止提交 | 见 10 冲突清单 | 对比正确 |

## Mastercard｜4853/4837｜Cardholder Dispute / No Cardholder Authorization

- **Provenance**：验证状态 VERIFIED_EXTRACTED｜冲突 无｜期限政策 明确｜生产可用 是｜来源 SRC-02
- **规则定位**：P1090；P1093；P1189；P350；P353；P501

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-011 | P350; P353; P501; P1090; P1093; P1189 | 抗辩 | 原交易未关联禁止提交 | 见 10 冲突清单 | addendum 判定正确 |

## Mastercard｜4853/4850｜Cardholder Dispute / Installment Billing Dispute

- **Provenance**：验证状态 VERIFIED_EXTRACTED｜冲突 无｜期限政策 明确｜生产可用 是｜来源 SRC-02
- **规则定位**：P1064；P1076；P312；P330

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-010 | P312; P330; P1064; P1076 | 条件性 | 未定性禁止提交 | 见 10 冲突清单 | 定性正确；引用 P312/P330 |

## Mastercard｜4853/4854｜Cardholder Dispute / NEC

- **Provenance**：验证状态 VERIFIED_EXTRACTED｜冲突 无｜期限政策 未说明（需收单机构确认）｜生产可用 是｜来源 SRC-02
- **规则定位**：P1157；P152；P460；P950

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-001 | P152; P460; P950; P1157 | 信息不足 | 规则引擎禁止对 tort 类提交抗辩 | 见 10 冲突清单 | Agent 引用来源页码；系统状态=不可提交 |

## Mastercard｜4853/4855｜Cardholder Dispute（版本切换）

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 ['CONFLICT-005']｜期限政策 未说明（Visa 需收单机构确认 / 演示设定）｜生产可用 否｜来源 SRC-02, SRC-03
- **规则定位**：合成案例，无原文定位（见 derived_from_rule_ids）

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-070 | 合成案例，无原文定位（见 derived_from_rule_ids） | 条件性 | 历史案件禁止套用新规则 | 见 10 冲突清单 | 快照版本号正确 |

## Mastercard｜4853（Change of Reason）｜Cardholder Dispute

- **Provenance**：验证状态 CONFLICTING_SOURCES｜冲突 ['CONFLICT-006']｜期限政策 明确｜生产可用 否｜来源 SRC-02
- **规则定位**：P1171；P477

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-013 | P477; P1171 | 条件性 | 旧证据未归档前禁止提交 | 见 10 冲突清单 | 证据清单随原因刷新 |

## Mastercard｜4853（抗辩码 2001）｜Cardholder Dispute / Suspected Altered Documentation

- **Provenance**：验证状态 VERIFIED_EXTRACTED｜冲突 无｜期限政策 存在版本差异（见冲突清单）｜生产可用 是｜来源 SRC-02
- **规则定位**：P1094；P1330；P162；P184；P335；P694；P957

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-005 | P162; P184; P335; P694; P957; P1094; P1330 | 抗辩 | 说明为空禁止提交 | 见 10 冲突清单 | 抗辩码=2001；草稿引用规则 |

## Mastercard｜4853（抗辩码 2004）｜Cardholder Dispute / Suspected Return Fraud

- **Provenance**：验证状态 VERIFIED_EXTRACTED｜冲突 无｜期限政策 存在版本差异（见冲突清单）｜生产可用 是｜来源 SRC-02
- **规则定位**：P1042；P163；P279；P958

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-006 | P163; P279; P958; P1042 | 抗辩 | 无检验记录禁止提交 | 见 10 冲突清单 | 抗辩码=2004 |

## Mastercard｜4870/4871｜Chip Liability Shift (Counterfeit / Lost-Stolen-NRI)

- **Provenance**：验证状态 CONFLICTING_SOURCES｜冲突 ['CONFLICT-009']｜期限政策 明确｜生产可用 否｜来源 SRC-02
- **规则定位**：SRC-02 P578-636/P1241-1288

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-051 | SRC-02 P578-636/P1241-1288 | 条件性 | 无 | 见 10 冲突清单 | 责任判定正确 |

## Mastercard｜Compliance Case（All Other Rules Violations）｜Compliance

- **Provenance**：验证状态 VERIFIED_EXTRACTED｜冲突 无｜期限政策 明确｜生产可用 是｜来源 SRC-02
- **规则定位**：P1495-1497

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-019 | P1495-1497 | 信息不足 | 无 | 见 10 冲突清单 | 15 分钟判定正确 |

## Mastercard（Ethoca）｜预防类（对应 4837/4863 场景）｜预防（No Cardholder Authorization 前置）

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 ['CONFLICT-013']｜期限政策 未说明（需收单机构确认）｜生产可用 否｜来源 SRC-03
- **规则定位**：§20（第 20 章）

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-034 | §20（第 20 章） | 信息不足 | 无 | 见 10 冲突清单 | 详情展示完整 |

## N/A（产品安全）｜N/A｜Cross-tenant access

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 无｜期限政策 明确｜生产可用 否｜来源 SRC-01, SRC-02
- **规则定位**：合成案例，无原文定位（见 derived_from_rule_ids）

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-069 | 合成案例，无原文定位（见 derived_from_rule_ids） | 信息不足 | 租户边界强制 | 见 10 冲突清单 | 403 返回；审计留痕 |

## Visa｜10.4｜Other Fraud – Card-Absent Environment

- **Provenance**：验证状态 CONFLICTING_SOURCES｜冲突 ['CONFLICT-003', 'CONFLICT-012']｜期限政策 未说明（Visa 需收单机构确认 / 演示设定） / 未说明（需收单机构确认）｜生产可用 否｜来源 SRC-01, SRC-03
- **规则定位**：SRC-01 P26/P54-58；SRC-03 §3；§3（第 3 章，约 60-90 行）；合成案例，无原文定位（见 derived_from_rule_ids）

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-025 | §3（第 3 章，约 60-90 行） | 条件性 | 证据不足阻止提交 | 见 10 冲突清单 | CE3.0 判定正确；缺失证据列表正确 |
| CB-CASE-040 | SRC-01 P26/P54-58; SRC-03 §3 | 条件性 | 证据不足时阻止提交并建议接受 | 见 10 冲突清单 | CE 判定正确；缺失项列表正确 |
| CB-CASE-061 | 合成案例，无原文定位（见 derived_from_rule_ids） | 接受 | 准备度<阈值：提交按钮禁用+原因展示 | 见 10 冲突清单 | 提交被阻止；建议=ACCEPT；原因引用规则 |
| CB-CASE-071 | 合成案例，无原文定位（见 derived_from_rule_ids） | 抗辩 | 无 | 见 10 冲突清单 | 证据链讲解正确 |

## Visa｜10.4（Fraud 类保护规则）｜Other Fraud – Card-Absent

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 ['CONFLICT-012']｜期限政策 未说明（需收单机构确认）｜生产可用 否｜来源 SRC-01
- **规则定位**：P14

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-022 | P14 | 条件性 | ECI 7 且无其他证据→建议接受 | 见 10 冲突清单 | ECI 判定正确 |

## Visa｜11.3｜No Authorization / Late Presentment

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 ['CONFLICT-001', 'CONFLICT-012']｜期限政策 未说明（需收单机构确认）｜生产可用 否｜来源 SRC-01, SRC-03
- **规则定位**：SRC-01 P31；SRC-03 §10

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-042 | SRC-01 P31; SRC-03 §10 | 条件性 | 数据缺失时转人工 | 见 10 冲突清单 | 判责结果正确 |

## Visa｜12.6.1｜Duplicate Processing

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 ['CONFLICT-002', 'CONFLICT-012']｜期限政策 未说明（需收单机构确认）｜生产可用 否｜来源 SRC-03
- **规则定位**：§9（第 9 章）

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-030 | §9（第 9 章） | 条件性 | 仅金额相同时要求更多字段 | 见 10 冲突清单 | 重复判定正确 |

## Visa｜12.6.1/12.6.2｜Duplicate Processing / Paid by Other Means

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 ['CONFLICT-002', 'CONFLICT-012']｜期限政策 未说明（需收单机构确认）｜生产可用 否｜来源 SRC-01, SRC-03
- **规则定位**：SRC-01 P37-38；SRC-03 §9

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-043 | SRC-01 P37-38; SRC-03 §9 | 条件性 | 金额相同但字段不全→转人工 | 见 10 冲突清单 | 判定正确 |

## Visa｜13.1｜Merchandise/Services Not Received

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 ['CONFLICT-012']｜期限政策 未说明（Visa 需收单机构确认 / 演示设定） / 未说明（需收单机构确认）｜生产可用 否｜来源 SRC-01, SRC-03
- **规则定位**：SRC-01 P40-41；SRC-03 §5；§5（第 5 章）；合成案例，无原文定位（见 derived_from_rule_ids）

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-026 | §5（第 5 章） | 条件性 | POD 缺失阻止提交 | 见 10 冲突清单 | 证据链判定正确 |
| CB-CASE-041 | SRC-01 P40-41; SRC-03 §5 | 条件性 | POD 缺失阻止提交 | 见 10 冲突清单 | 证据链判定正确 |
| CB-CASE-060 | 合成案例，无原文定位（见 derived_from_rule_ids） | 抗辩 | 无（正面路径） | 见 10 冲突清单 | 准备度评分≥90；草稿引用规则；提交成功且幂等键唯一 |
| CB-CASE-063 | 合成案例，无原文定位（见 derived_from_rule_ids） | 抗辩 | 截止前 72 小时强制提醒 | 见 10 冲突清单 | 飞书卡片含截止时间与链接 |
| CB-CASE-065 | 合成案例，无原文定位（见 derived_from_rule_ids） | 抗辩 | 低置信字段未修正禁止提交 | 见 10 冲突清单 | 修正后校验通过 |
| CB-CASE-068 | 合成案例，无原文定位（见 derived_from_rule_ids） | 抗辩 | 无（重试是内部机制） | 见 10 冲突清单 | 无重复提交；回执唯一 |

## Visa｜13.2｜Cancelled Recurring Transaction

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 ['CONFLICT-012']｜期限政策 未说明（需收单机构确认）｜生产可用 否｜来源 SRC-03
- **规则定位**：§6（第 6 章）

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-027 | §6（第 6 章） | 条件性 | 无取消证据时建议接受 | 见 10 冲突清单 | 时间线判定正确 |

## Visa｜13.3｜Not as Described or Defective

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 ['CONFLICT-012']｜期限政策 未说明（需收单机构确认）｜生产可用 否｜来源 SRC-01, SRC-03
- **规则定位**：P43-44；§7（第 7 章）

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-021 | P43-44 | 条件性 | 无发票禁止提交 | 见 10 冲突清单 | 证据清单正确 |
| CB-CASE-028 | §7（第 7 章） | 条件性 | 无发货记录阻止提交 | 见 10 冲突清单 | 对比逻辑正确 |

## Visa｜13.6｜Credit Not Processed

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 ['CONFLICT-012']｜期限政策 未说明（Visa 需收单机构确认 / 演示设定） / 未说明（需收单机构确认）｜生产可用 否｜来源 SRC-01, SRC-03
- **规则定位**：§8（第 8 章）；合成案例，无原文定位（见 derived_from_rule_ids）

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-029 | §8（第 8 章） | 条件性 | 无退款记录建议接受 | 见 10 冲突清单 | 退款匹配正确 |
| CB-CASE-072 | 合成案例，无原文定位（见 derived_from_rule_ids） | 抗辩 | 无 ARN 建议接受 | 见 10 冲突清单 | 匹配正确 |

## Visa｜13.7｜Cancelled Merchandise/Services

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 ['CONFLICT-012']｜期限政策 未说明（需收单机构确认）｜生产可用 否｜来源 SRC-01
- **规则定位**：P17；P49-50；SRC-01 P49-50

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-023 | P17; P49-50 | 条件性 | 14 天内取消且未退款→建议直接退款 | 见 10 冲突清单 | 窗口判定正确 |
| CB-CASE-044 | SRC-01 P49-50 | 条件性 | 政策未披露→建议退款 | 见 10 冲突清单 | 判定正确 |

## Visa｜13.7（Cancelled Merchandise/Services 相关）｜Cancelled Merchandise/Services

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 ['CONFLICT-012']｜期限政策 未说明（需收单机构确认）｜生产可用 否｜来源 SRC-01
- **规则定位**：P18

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-020 | P18 | 信息不足 | 无披露证据时建议接受 | 见 10 冲突清单 | 披露证据项校验生效 |

## Visa｜Compliance（无 Dispute Condition）｜Compliance

- **Provenance**：验证状态 NEEDS_CONFIRMATION｜冲突 ['CONFLICT-012']｜期限政策 未说明（需收单机构确认）｜生产可用 否｜来源 SRC-01
- **规则定位**：P20

| 案例 | 规则依据 | 预期判断 | 阻塞条件 | 边界/例外 | 测试断言 |
|---|---|---|---|---|---|
| CB-CASE-024 | P20 | 信息不足 | 无 | 见 10 冲突清单 | 流程归类正确 |
