# 飞书生产部署与迭代

本文描述当前 OceanPilot V2 飞书接入的真实运行方式。它不改变业务边界：交易、上游提交与资金仍是合成或 Mock；飞书仅承载已授权的协作、查询、提醒和人工确认。

## 当前接入方式（2026-09-15）

当前默认是公开群知识助手；新增私聊案件助手为显式启用功能，采用网站会话与私聊一次性配对。请以 [私聊实施与验收说明](feishu-private-cases.md) 和 [公开知识说明](feishu-public-knowledge.md) 为准。历史 `OCEANPILOT_V2_FEISHU_BINDINGS_JSON` / `OCEANPILOT_V21_FEISHU_TEST_TARGETS_JSON` 不授权新的私聊助手，不能用下面保留的旧版人工绑定步骤替代新配对。

私聊需配置 `OCEANPILOT_FEISHU_PRIVATE_CASES=enabled`；真实私聊发送另需 `OCEANPILOT_FEISHU_PRIVATE_OUTBOUND=authorized-test` 和飞书凭据。群聊仍使用独立的群授权与已批准公开知识。绑定、确认、解除绑定均由网站已登录会话完成，案件查询与动作每次重新核验权限。上传、人工核验、证据包审批及上游提交继续使用网站流程。

2026-09-15 已在本机 8002 服务显式启用私聊，负责人批准的演示商户 A 绑定、真实飞书二次确认抗辩和接受、退回后的私聊查询、群聊隔离及自动通知已核验；服务重启后绑定、案件状态与私聊收发仍正常。材料上传与退回由真实登录态网站 HTTP 接口完成，不是独立浏览器录屏验收。第二个真实飞书身份、完整隐私失败矩阵和 C 独立验收仍未完成。

固定服务器与域名仍未提供，当前 Mac Quick Tunnel 不是固定环境。`check_feishu_readiness.py` 仅检查其加载的环境配置及网络条件，不证明运行进程已加载同样的配置，也不证明身份绑定、真实消息回执或一小时稳定性；需使用上述验收说明中的逐项实际证据。

执行固定部署前，负责人需明确授权的服务器、固定域名及管理权限获取方式；真实上游另需授权的 OceanPayment／银行接口文档、沙箱地址、认证与事件／回执契约。密钥通过私有渠道或密钥管理器提供，不写入 issue 或公开资料。不能把可见的其他主机当作部署许可，也不能按猜测实现接口后宣称真实接通。

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

## 历史参考：旧版人工用户和会话绑定（当前组合不使用）

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

## 历史参考：旧版真实卡片发送（当前组合不使用）

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
