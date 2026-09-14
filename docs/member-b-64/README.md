# Member B / issue #64 交接入口

本分支包含基于 `f1fc063c9adcb52c47ca77298de9d5cc8bd2432c` 验收的 B 改动，供 A/C 审阅和独立复验。草稿 PR 的目标是 `oceanpilot-v2`，不是 `master`。上传不等于合并、远程部署、正式冻结或完成 Stage 4/5。

- [启动、新演练与恢复](RUNBOOK.md)
- [最终测试结果](FINAL-RESULTS.md) · [完整 pytest 日志](evidence/pytest-isolated-runtime.log)
- [代码变化和浏览器验证范围](VERIFICATION.md)
- [技术答辩与 PDF/截图支持缺口](TECHNICAL-QA.md)
- [20 核心引用支持表](core-reference-support.csv)
- [本地验收构建清单](build-manifest.json) · [固定依赖](runtime-requirements.txt)

以上验收文档中的“尚未提交/推送”描述记录验收时状态；用户随后授权上传，当前远端代码以本分支提交为准。清单里的 Git HEAD、绝对路径、实例 ID 和含生成包元信息的哈希指向 B 当时的本地验收环境，并非新的生产发布标识。

账号凭据、运行数据库、虚拟环境和本地浏览器会话均不在仓库中。克隆后按 runbook 在新目录创建独立实例；不要假定 B 的 localhost 地址能从别人的电脑访问。本文档链接的完整测试日志已随分支提供，其余本地截图/恢复过程记录仍在 B 机器上，联合录制时另行核对。
