# OceanPilot 5 分钟 Live Demo 操作手册

状态：本地实现及验收，不是已冻结的现场发布版本。真实飞书、固定 HTTPS、现场网络和三次计时彩排需独立验收。不得以模拟 transport 的测试代替租户回执。

## 当前可查看的本地实例

2026-09-14 已准备一宗未消耗的初态案件 `OPV2-81fc7996g5492d8d1`，revision 7、CONTEST、4/5 就绪。服务位于 `127.0.0.1:8016`，离线模型、Mock 上游、未启用飞书。请勿把它当作 9 月 19 日正式冻结实例，正式展示需重新检查期限。

- [商户聚焦页](http://127.0.0.1:8016/v2/merchant/cases/OPV2-81fc7996g5492d8d1?stage=1)
- [运营聚焦页](http://127.0.0.1:8016/v2/operations/cases/OPV2-81fc7996g5492d8d1?stage=1)
- 使用不同浏览器配置登录 `merchant-a` 和 `operator-a`；本机随机密码仅见 `work/stage-preview-ready-20260914/private-accounts.json`，不要投屏此文件。
- manifest 与两份 PDF：`work/stage-preview-ready-20260914/rehearsals/4c60450e-b65f-4983-aaad-f404f31ed3d6/`。
- 两页可编辑主讲材料：`output/stage-demo/OceanPilot-live-demo.pptx`，包含 C 的开场/结尾备注。
- 如本地服务停止，仓库根目录执行：`PYTHONPATH=src .venv/bin/python scripts/member_b_demo.py start --instance work/stage-preview-ready-20260914`。若源码已变，按下文回归、重建，不绕过指纹检查。

## 唯一主线

商户飞书询问缺什么，打开同一案件；上传缺送达时间的签收证明，系统阻断；上传修订版，运营独立核验原件；飞书二次确认提交；运营端进入 OP 人工审核。结束状态必须保持 UNKNOWN / NOT_FINAL，不演示银行胜诉、到账或结案。

普通 V2 页面不变。舞台链接使用现有 `/v2/merchant/cases/{id}?stage=1` 和 `/v2/operations/cases/{id}?stage=1`。账号、CSRF、available_actions、案件 revision 和业务命令全部沿用现有实现。聚焦层没有自己维护一套演示状态。

聚焦文案只适用于预定的合成 Visa 13.1、CONTEST、其余四项已就绪的场景。其它原因码、非 Mock 案件或其它材料存在缺口时，即使 URL 含 `stage=1` 也显示普通 V2 页面，不套用签收证明英雄文案。

## 已实现的准备入口

在仓库根目录操作并激活 Python 3.12 虚拟环境（本机已配置 `.venv`）。安装演练可选依赖后，为每轮创建独立目录，不使用已有共享数据目录。凭据保存在 mode 0600 的 `private-accounts.json`，勿截图、粘贴到群或提交 Git。

```bash
python -m pip install -e '.[dev,demo]'
PYTHONPATH=src python scripts/member_b_demo.py new --instance work/stage-rehearsal-01 --port 8014
PYTHONPATH=src python scripts/member_b_demo.py start --instance work/stage-rehearsal-01
```

保持服务运行，在另一个终端执行：

```bash
PYTHONPATH=src python scripts/member_b_rehearsal.py --instance work/stage-rehearsal-01 --stage-demo
```

脚本通过真实登录、交易登记、事件接收、任务发布、商户 CONTEST 和四次文件上传形成 4/5 初态。系统记录项使用运营账号上传。脚本不删除、覆盖、重置或直接改写业务数据库。反复执行只新增案件。每轮建议使用新实例，保持演示商户仅有一个有效案件，使“我还缺什么”无需现场选择案件。

输出位置为该实例下 `rehearsals/{run_id}/`，包含：

- `stage-manifest.json`：实例 ID、案件 ID、初始 revision、提交及构建指纹、双端链接、两份 PDF 路径与 SHA-256、初终态、未验收声明；不包含密码。
- `proof-of-delivery-v1-missing-time.pdf`：交易、金额、签收确认存在，缺送达时间。
- `proof-of-delivery-v2-complete.pdf`：补全送达时间，同一交易的修订材料。
- `http-trace.json`：准备请求的角色、路径和状态码，不记录登录凭据或请求体。

`--public-base-url https://已配置的固定域名` 只影响 manifest 的展示链接，不会配置 DNS、TLS、反向代理或飞书回调。参数拒绝 HTTP、URL 凭据和 trycloudflare.com 临时域名。正式域名及真实私聊启用由飞书/部署负责人完成，不在同一租户启动第二个通知 worker。

`member_b_demo.py start` 默认完全离线模型和 Mock 上游，不继承 `.env` 中的飞书发送设置。`--model-config` 仅导入指定文件中的 DeepSeek 配置，不导入共享 DB 或飞书凭据。真实租户正式环境由接入负责人按 `feishu-private-cases.md` 配置。

## 5 分钟舞台口令

| 时间 | C 主讲 | A 操作 | 画面验收点 |
| --- | --- | --- | --- |
| 0:00–0:20 | 支付争议最难的不是聊天，而是在期限内交对材料。 | 主讲材料第 1 页 | 合成 Visa 13.1，4/5 就绪 |
| 0:20–0:55 | 它知道我是哪家商户、哪宗案件、缺什么。 | 已配对飞书私聊“我还缺什么” | 当前案件、期限、签收证明用途、来源及网页入口 |
| 0:55–1:35 | 这份材料看起来完整，但它没有送达时间。 | 商户页上传 v1 PDF | 显示“缺少送达时间”，不能提交 |
| 1:35–2:05 | 补上缺口后，旧版仍然保留。 | 上传修订版，选同一材料的替换项 | 材料 v2，v1 历史保留，仍等待人工核验 |
| 2:05–2:45 | 提取是建议，不能代替人认定事实。 | 运营页打开原件，逐项核对并填写核验表 | 原件第 1 页、独立核验、正确交易与金额 |
| 2:45–3:20 | 商户确认把这份材料交给处理团队。 | 飞书新卡片点提交，再点确认 | 只产生一次 SUBMIT_EVIDENCE，运营端同步 OP 审核 |
| 3:20–4:10 | 同案跨渠道、错误能阻断、关键决定由人确认。 | 停运营结果，展开来源与审计 | revision 和真实负责人，UNKNOWN / NOT_FINAL |
| 4:10–4:55 | OceanPilot 把争议准确交给下一位负责的人。 | 主讲材料第 2 页 | 明说合成数据、Mock 上游、效果待受控验证 |

C 不操作电脑。A 使用独立商户与运营浏览器配置，避免用同一 cookie 来回登录。B 在台下准备案件、核对构建、处理应急，不上台临时切讲。

核验表不得在应用内预填“已检查原件”或自动选择通过。A 在演练前熟悉填写顺序：判断、理由、已打开原件、交易编号、币种、金额最小单位、两条事实原文、`page:1`、最终确认。正式操作必须与屏幕上的原件逐项一致。

## 原件与来源边界

文本型 PDF 的显式字段由确定性正文提取器处理，不调用模型、不猜测遗漏字段；重复字段视为缺失。页面和卡片必须如实注明。其他文档仍使用现有提取和人工兜底路径。

两份 PDF 都进入 NEEDS_MANUAL，另保留 `extraction_check_status` 表示提取内容完整与否。缺失或矛盾的显式字段不能被“支持事实”人工操作覆盖，必须修订原件。完整 PDF 也不自动通过独立人工核验。材料替换保留原件并使旧审批失效。

原件预览是从已保存字节确定性渲染的第 1 页，非 AI 重绘。新只读接口 `/files/{object_id}/pages/{page_number}` 复用原件下载权限，最多预览前 10 页，不改变原文件。超过范围、Word 或无法解析的文件应下载完整原件人工检查，不能将预览当作完整文件已验收。

飞书模型仅对已授权、已脱敏事实做关注项定位，卡片保留规则事实和业务门禁。成功标注实际返回模型名，异常使用确定性回退，预算 3 秒。未接模型时标注未调用语言模型。不要宣称本次文本型 PDF 是 DeepSeek 识别，也不要宣称模型自动做出风控判断。

## 验收分层

1. 自动测试：`PYTHONPATH=src python -m pytest -q`。重点为 `test_feishu_stage_submission.py`、`test_stage_original_preview.py`、文档替换及已有私聊安全测试。
2. 浏览器本地验收：安装 Playwright 后 `node scripts/verify_stage_browser.cjs <stage-manifest.json> --exercise`。macOS 默认独立 headless Chrome，其他路径可用 `STAGE_CHROME` 指定。仅允许专用本地实例，使用正常登录和命令。此脚本会消耗该案件，上传两版 PDF、通过真实表单记录合成人工核验，再通过已认证 HTTP 提交；它不是飞书租户验收，也不是人工阅读原件的证明。
3. 真实租户验收：固定域名、签名验证、绑定、卡片实际回执及回流、DeepSeek 降级、旧卡/转发/重复回调、两端同步，逐项留下可脱敏证据。没有此层，不能标“全 Live 已就绪”。
4. 正式设备彩排：连续三次 4:40–4:55。记录每次案件、构建 SHA、操作者、查询延迟、总时长、异常、验收人。自动浏览器耗时不算现场彩排耗时。

浏览器验收输出 `browser-qa/acceptance.json` 和两种分辨率截图。主画面在 1920×1080 与 1366×768 不应横向或纵向溢出。展开审计、完整原件和核验表允许聚焦查看细节，主流程不滚动长列表。

## 冻结与现场前检查

- 私聊基线和 Demo 扩展经独立审查、全量回归后合入，再部署固定构建。工作树 SHA 是可复核指纹，不等同于已合入发布。
- 关闭所有旧的演练实例。正式使用全新实例和专用商户，生成一次正式案件，不继续拿它做验证。
- 检查 deadline 覆盖展示时间，初态仍为 CONTEST、4/5、缺签收证明、UNKNOWN / NOT_FINAL。
- 登录、配对、单案件选择、模型预热均在上台前完成。确认私聊只存在一个授权发送器。
- 两端焦点页、飞书和两页主讲材料准备好。关闭个人通知；桌面、下载列表、终端不得出现密码、Token、原始飞书 ID。
- 准备实际租户全流程的 1080p 录屏，检查无隐私泄漏。当前自动浏览器截图不是这份备用录屏。
- 冻结后仅修 P0：泄漏、未授权动作、重复提交、主链断裂或错误终局。源代码变更后旧指纹失效，应回归、重新部署并重跑验收，不能带病强行 `pin`。

飞书卡片超过 6 秒：C 说“这一步正在通过飞书读取同一个案件，我们保留权限和版本校验。”超过约 8 秒，A 切到已核对的备用录屏并明确告知；现场不调试，不盲目重发结果不确定的操作。

## 目前不能自动代办的关卡

固定 HTTPS 域名与服务器尚待明确，现有生产私聊开关未更改。真实租户配对、真实发送、三次计时、正式设备网络、1080p 完整备用录屏、代码合入和最终冻结均不能从本地测试推定完成。由 A/B/C 按上述分工落实并记录，验收前 manifest 保持 `tenant_acceptance: NOT_RUN`、`frozen_release: false`。
