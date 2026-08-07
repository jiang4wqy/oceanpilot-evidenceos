# `domain/` — 领域内核 / business core

**最内层。纯 Python,无 IO、无框架、无厂商 SDK。** 这里是可信、可确定性单测的业务规则。

依赖规则:只能 import stdlib 与本层。**禁止** import `fastapi`/`sqlite3`/`oceanpilot.api`/`oceanpilot.adapters`(由 `tests/domain/test_import_boundaries.py` 强制)。

设计取向:**内核只做决策,不做解释、不做 IO。** agent 在外层包裹它、生成人话;内核给出的数字/路由/是否人工复核才是权威。

| 模块 | 职责 |
|---|---|
| `chargeback.py` | 拒付判定内核:理由码/证据码枚举 + 权重规则表;`assess_chargeback()` 给出胜诉率(**缺关键证据门控**)、完整度、责任团队、时限、是否需人工。 |
| `chargeback_prevention.py` | 争议发生前的风险内核:按合成信号加权打分,建议现在该留哪些证据;最强输出为"建议人工复核"。 |
| `evidence_catalog.py` | 证据码 → {中文标签, 说明, 为何重要, 合格示例}(对全部证据码穷尽,有测试保证)。`request_sentence`/`rebuttal_line` 让补证问句与申诉信不漏原始 token。 |
| `reason_catalog.py` | 拒付理由码 → 中文标签 + `confirm_prompt`(人工确认理由时的话术)。 |
| `security.py` | 敏感数据校验:识别卡号(Luhn)/PII;`assert_no_sensitive_data()` 拒收。合成数据红线的守门人。 |
| `models.py` / `enums.py` / `state_machine.py` | 基础版(支付异常)案件聚合、枚举、状态迁移。 |
| `diagnosis.py` / `evidence_policy.py` | 基础版确定性诊断规则与证据完整度策略。 |
| `errors.py` | 领域异常(如 `SensitiveDataRejected`)。 |

新增枚举成员时:记得同步 `evidence_catalog` / `reason_catalog`(穷尽性测试会提醒你)。
