# DeepSeek 本地接入与密钥存放指南

本指南供后续开发者在本机启用 OceanPilot 的 DeepSeek Provider。密钥只允许进入
Git 忽略的 `.env` 或受控的部署 Secret Manager；禁止写入源码、测试、飞书文档、
截图、Issue、PR、聊天记录或日志。

## 1. 撤销已经暴露的密钥

只要密钥曾出现在聊天、截图、提交记录或共享文档中，就应视为已经泄露。先在
DeepSeek 控制台撤销旧密钥并生成新密钥。不要尝试继续使用或“删除后复用”旧密钥；
聊天消息的删除能力也不能替代密钥轮换。

## 2. 创建本机 `.env`

在仓库根目录执行：

```powershell
Copy-Item .env.example .env
```

仓库位置：

```text
C:\Users\lenovo\Documents\Codex\2026-08-04\zhao\work\oceanpilot-master
```

只在本机编辑 `.env`，写入：

```dotenv
OCEANPILOT_CHARGEBACK_LIVE_MODEL=1
OCEANPILOT_MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

在本机把新密钥粘贴到 `DEEPSEEK_API_KEY=` 的等号后；不要把填写后的内容复制到聊天或
截图中。

`.gitignore` 已忽略 `.env` 和 `.env.*`，但仍应在提交前主动验证：

```powershell
git check-ignore .env
git status --short
```

第一条命令应输出 `.env`；第二条命令不应把 `.env` 列为待提交文件。

## 3. 安装依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

项目使用 `python-dotenv` 让 Uvicorn 的 `--env-file` 参数安全读取本机配置。应用代码、
测试和 CI 默认不会自动加载 `.env`，避免测试意外访问外部模型。

## 4. 在线连通性验证

只使用 Synthetic 文本运行可选 live 测试：

```powershell
.\.venv\Scripts\dotenv.exe -f .env run -- `
  .\.venv\Scripts\python.exe -m pytest tests/model/test_deepseek_live.py -q
```

通过标准：

- IntakeAgent 能返回合法争议类型；
- AssessAgent 返回非空模型说明；
- 确定性评估结果没有被模型修改；
- 终端和异常信息中不出现密钥。

## 5. 启动 DeepSeek 演示服务

```powershell
.\.venv\Scripts\python.exe -m uvicorn oceanpilot.main:create_app --factory `
  --env-file .env --host 127.0.0.1 --port 8002
```

打开：

```text
http://127.0.0.1:8002/demo
```

不传 `--env-file .env`、关闭 `OCEANPILOT_CHARGEBACK_LIVE_MODEL` 或缺少有效密钥时，
系统保持离线 `ScriptedModelProvider`，案件、规则、证据和人工闸门仍可运行。

## 6. 安全路由

- LOW：Synthetic、非敏感内容可直接发送给所选外部模型；
- MEDIUM：经过 `RegexRedactor` 脱敏后发送；
- HIGH：优先使用配置的本地隔离模型；未配置时只允许走脱敏外部路径；
- 模型只负责理解、补问、解释和起草；
- 证据就绪度、规则版本、责任路由和人工审批由确定性系统控制；
- 不得向 DeepSeek 发送真实卡号、CVV、密钥、个人身份信息或未脱敏交易正文。

## 7. 密钥轮换与故障处理

出现以下任一情况，应立即撤销并重建密钥：

- 密钥被发送到聊天或飞书；
- 密钥出现在截图、终端录屏、日志或错误响应；
- `.env` 被误加入 Git；
- 开发设备丢失或成员权限发生变化；
- DeepSeek 控制台出现未知调用或用量异常。

密钥失效或上游不可用时，不要把错误详情返回给前端。OceanPilot 应记录固定、脱敏的
Provider 失败状态并回退到确定性说明；不得为了“保证演示成功”把密钥硬编码到项目中。
