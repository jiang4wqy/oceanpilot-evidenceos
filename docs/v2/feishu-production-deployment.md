# 飞书生产部署与迭代

本文描述当前 OceanPilot V2 飞书接入的真实运行方式。它不改变业务边界：交易、上游提交与资金仍是合成或 Mock；飞书仅承载已授权的协作、查询、提醒和人工确认。

## 一次部署，后续只换镜像

1. 准备一台可运行 Docker Compose 的 Linux 服务器，并把固定 HTTPS 域名（例如 `https://oceanpilot.example.com`）反向代理到容器 `8000` 端口。
2. 复制 `.env.example` 为服务器 `.env`，通过密钥管理器或服务器环境变量填入飞书凭据。不要把 `.env` 提交到 Git。
3. 设置 `OCEANPILOT_V2_BASE_URL=https://oceanpilot.example.com`。这个地址用于卡片中的案件链接。
4. 运行 `docker compose up -d --build`。SQLite 数据写入命名数据卷 `oceanpilot-data`，重建镜像不会删除案件或飞书回执。
5. 在飞书开放平台只配置一次：
   - 事件：`https://oceanpilot.example.com/api/v2/integrations/feishu/events`
   - 卡片：`https://oceanpilot.example.com/api/v2/integrations/feishu/card`
6. 用 `curl -f https://oceanpilot.example.com/health` 检查服务，再在飞书里发送一条测试消息并核对日志。

也可运行 `python scripts/check_feishu_readiness.py`。它只输出各层是否就绪和绑定／目标数量，不打印 App Secret、Token、Encrypt Key 或飞书原始 ID。

Quick Tunnel 只适合临时联调。`trycloudflare.com` 地址会变化且没有可用性承诺，不应作为正式回调地址。

## 安全完成用户和会话绑定

服务只接受部署人员明确绑定的飞书用户与会话。未知用户发送的已签名事件会返回 `UNTRUSTED_BINDING`，并写入 actor/chat 的域分离 SHA-256 哈希。为了在绑定后能生成出站目标，tenant、open_id、chat_id 的组合只以 AES-GCM 密文落盘，密钥由服务器的 Encrypt Key 域分离派生；明文和 Encrypt Key 均不写入数据库或候选列表。

让目标用户给机器人发送一条测试消息后，在服务器执行：

```bash
python scripts/list_feishu_binding_candidates.py
```

确认最新候选属于目标测试用户，再生成配置模板：

```bash
python scripts/list_feishu_binding_candidates.py \
  --select 1 \
  --role MERCHANT \
  --actor-id '<OceanPilot 账号 ID>' \
  --merchant-id merchant-a \
  --target
```

把输出的 `OCEANPILOT_V2_FEISHU_BINDINGS_JSON` 和 `OCEANPILOT_V21_FEISHU_TEST_TARGETS_JSON` 写入服务器密钥配置并重启容器。`--target` 只能在配有正确 `FEISHU_ENCRYPT_KEY` 的服务器上解密投递地址。该流程不会信任消息正文里的角色或商户字段。

## 开启真实卡片发送

真实发送默认关闭。只有同时满足以下条件才会创建飞书出站客户端：

- `FEISHU_APP_ID` 与 `FEISHU_APP_SECRET` 已配置；
- `OCEANPILOT_V21_FEISHU_OUTBOUND=authorized-test`；
- `OCEANPILOT_V21_FEISHU_TEST_TARGETS_JSON` 明确列出目标群、商户、授权记录，并与可信 chat 绑定一致。

首次应把 `allow_callback_replies` 保持为 `false`，先由运营端预览卡片并人工确认发送。真实群验证稳定后，才能对该授权群开启回调自动回复。

## 程序升级

正常迭代不需要重新配置飞书。首先只检查服务器环境和 Compose 配置：

```bash
sh scripts/update_server.sh --check
```

升级时运行：

```bash
git pull --ff-only
OCEANPILOT_HEALTH_URL=https://oceanpilot.example.com/health \
  sh scripts/update_server.sh
```

脚本会在容器内通过 SQLite backup API 为每个数据库创建一致备份并运行 `PRAGMA integrity_check`，然后把备份和 SHA-256 清单复制到服务器 `backups/<UTC 时间>/`。它保留升级前的镜像，重建服务后最多等待 60 秒检查固定域名健康状态；检查失败时自动恢复上一镜像并保留日志。数据库迁移依然只允许向前兼容的增量变更；若未来引入破坏性 schema 迁移，必须另外设计数据回滚。

服务器上的 `backups/` 应定期复制到异机或对象存储，不要把同机备份当作灾备。

只要固定域名和环境变量名保持不变，事件 URL、卡片 URL、Token、Encrypt Key 和可信绑定都无需改动。数据库表采用增量 `CREATE TABLE IF NOT EXISTS`；升级前仍应备份 Docker 数据卷，并在预发布环境跑完整测试。

如需换服务器，停止旧实例后复制数据卷与密钥配置，在新服务器复用同一固定域名即可。DNS/代理切换完成后，飞书开放平台通常无需改 URL。
