# 图片、PDF 与 Word 上传补充（2026-09-14）

本次按用户反馈扩大上传支持，不能把先前结构化合成检查结果等同于真实文档识别。

## 已实现的代码

- 单个原文件上限统一为 **20 MiB（20,971,520 字节）**，前端、API base64 长度和解码后校验一致。字段数量/单字段长度限制仍适用于结构化文件。
- 接受 PDF、DOCX、DOC、PNG/JPEG/WebP/GIF/BMP/TIFF、TXT、JSON、单行 CSV。浏览器依据扩展名规范化 MIME，原件按字节保存，保留 SHA-256、角色权限、下载和版本历史。
- PNG 等图片生成仅用于识别的 JPEG 副本；扫描 PDF 按页渲染后以图像块送入现有模型接口；DOCX 提取正文与嵌入图片。原件不会被识别副本覆盖。
- 识别状态单列为成功、部分、失败、未配置或仅人工。图片/PDF/Word 一律先进入 NEEDS_MANUAL，模型不能直接宣布材料通过。人工必须独立打开原件、明确勾选核验、填写从原件核实的本案交易编号/币种/金额、事实摘录与页码/文档位置。上传者不能核验自己的文件，整包批准仍独立进行。
- 同一材料选择“替换”并重传原件可重试识别，会生成新材料版本并使旧审批失效；响应丢失后复用原 command_id 读取回执，不重复调用已完成识别。
- 默认启动仍离线；只有显式提供 `--model-config` 才读取 DeepSeek 凭据。不会导入同一文件里的 Feishu、隧道、共享数据库设置。

## 实际接口

用户指定 `deepseek-v4-flash`。2026-09-14 对现有配置的端点发起合成 PNG 实测，请求名为 `deepseek-v4-flash`，返回名为 `deepseek-flash`，正确识别随机标记 BLUE-FOX-731。
[DeepSeek 官方图像文档](https://api-docs.deepseek.com/zh-cn/guides/vision/) 当前示例为 `deepseek-flash`，图像使用 OpenAI 兼容的 `image_url` base64 内容块；现有 LocalModelProvider 已支持这种序列化。Anthropic 适配器也保留图片块。非合成案件沿用 HIGH 路由，文本脱敏器无法处理像素时失败关闭，不能静默丢掉图片或直接透传。

## 启动与恢复

从 B 工作树执行；环境和实例均不与 A 的 8014 共用：

```sh
PYTHONPATH=src .venv/bin/python scripts/member_b_demo.py start \
  --instance work/member-b-demo/recovery-final \
  --model-config ../oceanpilot-v2/.env --model deepseek-v4-flash
```

`--model-config` 是本机私有配置路径，只读 `DEEPSEEK_API_KEY` 和 `DEEPSEEK_API_BASE`，不上传配置到仓库。其他同学应改为自己已有配置文件路径。省略两个模型参数即离线运行。每次启动写入不含密钥的 `run-*.json`，记录代码标识、模型和时间。重启仍使用相同三库，不重置案件。安装依赖时使用 `uv pip install --python .venv/bin/python -e '.[dev]'`；本机路径含空格，验证统一使用 `PYTHONPATH=src .venv/bin/python -m pytest`。

本次升级前备份 `work/member-b-demo/snapshot-before-documents`。恢复步骤见 RUNBOOK；恢复到新目录，不覆盖当前实例。材料仍通过应用上传，不能向 SQLite 写入识别、批准或结果。

## 边界

- 视觉请求最多读取前 10 页 PDF / 前 10 张嵌入图片，正文截取最多 40,000 字符；超过范围显示“部分”，人工检查完整原件。GIF/TIFF 等多帧图片只读取首帧并标明部分。单图片像素超过 4,000 万或解析异常时保存原件并提示识别未完成。
- 旧版 DOC 保存原件，暂不自动解析；人工打开或另存 DOCX/PDF 后替换。损坏、加密文件或模型故障不会伪装成识别成功。
- 这是文件保存、提取和人工适用性复核，不是恶意文件扫描、来源鉴定、数字签名验证或不可变存储。哈希不证明上传前未被修改。
- 实测合成样例不证明所有商户文件识别准确，不代表实际业务结果，不代替 C 的独立验收、Stage 4/5 或 A 的飞书投递验收。

## 本轮实际浏览器验收

- 在 8015、实例 78cae79a-979a-4438-a024-1614cadc141a 新建合成案件 OPV2-f56c6e88g41058abb，保留原案件 OPV2-2904b2d6g07450493。通过正常登录和商户决定进入材料准备，再逐个使用真实文件选择器上传 PNG、扫描 PDF、DOCX。
- 三个原文件最终均显示识别成功，返回模型 deepseek-flash，内容与合成交易对应，仍为 NEEDS_MANUAL；下载 SHA-256 均匹配。DOCX 首次识别失败，浏览器选择原材料替换并重传同一文件后成功，证据版本升为 2，保留第一次失败对象。案件停在 v7 / EVIDENCE_COLLECTING / UNKNOWN / NOT_FINAL，无审批、上游提交或结果。
- 使用风控独立账号打开人工核验主操作，选择图片后出现原件确认、交易关联和位置字段，确认均为空白；随后取消。浏览器没有执行人工批准。人工复核的成功/拒绝、上传者分离、旧包失效由自动回归覆盖，不能将其称为 C 的人工验收。
- 最后修正运营端“已上传待核验”被写成“缺失”、原件必填项显示“可选”以及选择器内部 ID 无业务名称的问题，Web 回归覆盖。
- 最后重启后重新用授权 HTTP 下载三个文件，哈希、识别状态和版本均保持。已创建停止状态下的 snapshot-documents-verified 三库快照；本轮未再执行一次该快照的完整恢复演练，原 RUNBOOK 的恢复机制已由生命周期回归覆盖。

合成文件见 evidence/visual-samples；接口/下载核对记录见 evidence/document-browser-http.json；代码/运行标识见 document-build-manifest.json。A 的 Feishu 和隧道配置未改动。

## 最终自动检查

- `PYTHONPATH=src .venv/bin/python -m pytest -q`：**2269 passed, 6 skipped, 2 warnings，139.49 秒**。相较 ca36a6e 的 2249 项，新增 20 项文档、视觉传输、人工核验和启动/界面回归。完整日志：evidence/pytest-document-upload.log。
- `ruff check src tests scripts/member_b_demo.py scripts/member_b_rehearsal.py` 通过；格式检查 283 个文件通过；git diff --check 通过。
- 6 项跳过：隔离测试进程未注入凭据的 5 项 live agent/Claude/DeepSeek 测试，加 1 项缺少 PowerShell。独立的现有 API 和浏览器视觉实测另列于上文，不能把跳过写成通过。
- 2 项警告仍是 Starlette/httpx 与 AnyIO BlockingPortal 弃用提示。没有运行 C 的独立三次录制验收或 A 的真实飞书投递验收。
