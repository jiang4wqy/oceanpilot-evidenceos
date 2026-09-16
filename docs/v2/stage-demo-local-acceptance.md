# 2026-09-14 本地 Demo 验收记录

结论：本地实现可以演练，正式全 Live 尚未验收。未提交或推送代码，未调整原 8002 服务或 `.env`，未启动真实飞书发送器。

## 被测版本

- 基础 Git 提交：`222e75433d13d57829fd73ab3a2185f7be56cbd5`，Demo 扩展仍在工作树。
- `member_b_demo.code_identity` 构建指纹：`4882adb65718d37aa977732c88575bb3da0a807011f0c573a621fefb0848419d`。
- 预览实例：`7e523277-e5dc-4255-83b8-6e3d619b4147`，本机端口 8016，offline / Mock / Feishu 未配置。
- 未消耗的初态案件：`OPV2-81fc7996g5492d8d1`，revision 7。实例状态检查 `code_matches: true`。

## 实际完成的检查

- 最后一轮全量 `pytest`：**2376 passed / 6 skipped / 2 dependency warnings**，134.97 秒。包含最后追加的 stage 场景范围保护；真实模型凭据缺失及 PowerShell 不可用的 6 项明确跳过。
- `Ruff check` 与 `format --check`：`src`、`tests`、`member_b_demo.py`、`member_b_rehearsal.py`、`stage_materials.py` 全通过，300 files already formatted。未修改其它工具脚本已有的 lint 问题。
- `git diff --check`、四份相关 JavaScript 的语法检查通过。
- 浏览器最终完整流程：商户与运营的初态、v1 缺时间、v2 待人工、人工核验、OP_REVIEW 共 20 个主画面检查，1920×1080 与 1366×768 均无横向或纵向溢出，pageerror 为 0。原件 saved-byte 页预览实际可见。
- 浏览器自动化使用真实登录/上传/核验表单/业务命令，但最后一步提交是已认证 HTTP，**不是飞书租户收发**。飞书两步卡片的行为在真实业务服务加模拟 transport 的接口测试中验证。
- 两份最终预览案件 PDF 均为一页文本文件，已提取检查并逐页渲染查看。v1 缺 `delivered_at`，v2 补齐。全链路测试验证旧版保留、缺失阻断、独立人工闸门及最后一次提交只增加一个 revision。
- 两页主讲 PPTX 经包完整性/尺寸/字体检查、重新导入并逐页渲染检查。没有声称在 PowerPoint 桌面应用中验收。

## 本机证据路径

- 最新完整浏览器验收：`work/stage-preview-20260914/rehearsals/aed52447-8e97-46f2-9e09-76f546b7ad53/browser-qa/acceptance.json` 及同目录截图。该实例曾从旧构建初始化，最后浏览器复核时已显式 pin 到上述最新构建，业务数据未重置。
- 未消耗的新预览案件 manifest：`work/stage-preview-ready-20260914/rehearsals/4c60450e-b65f-4983-aaad-f404f31ed3d6/stage-manifest.json`。
- 未消耗案件的四张初态浏览器检查与截图位于该目录的 `browser-qa/`。
- 演练准备目录、历史实例和旧版本原件均保留。用于测试的 8014、8015 服务已停止，当前仅保留本任务创建的 8016 预览服务；原有其它任务服务未动。

## 正式发布前必须补齐

固定 HTTPS 与独立部署、代码独立审查并合入、真实租户配对/发送/卡片回执、实际 DeepSeek 调用及降级、持续运行与重启后的实际收发、三次正式设备计时彩排、无隐私泄漏的 1080p 完整备用录屏、最终案件与构建冻结。

上述本地证据不能替代这些关卡。manifest 中 `tenant_acceptance` 保持 `NOT_RUN`，`frozen_release` 保持 `false`。
