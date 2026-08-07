# `api/` — HTTP 接口 / driving adapter

**FastAPI 路由 + 严格 DTO。** 把 HTTP 请求映射成应用服务调用,再把结果渲染为 JSON。不写业务逻辑——只做形状转换与依赖装配。

DTO 约定:请求模型 `extra="forbid"`(拒未知字段),字符串用 `StrictStr`;响应模型也 `extra="forbid"`。校验失败 → 422,且经 `errors.py` 输出安全的 problem+json(不回显敏感输入)。

| 文件 | 说明 |
|---|---|
| `chargeback.py` | 拒付路由:`POST /cases`、`POST /cases/{id}/confirm`、`POST /cases/{id}/evidence`、`POST /cases/{id}/finalize`、`GET /cases/{id}`。经 `get_channel_service` 依赖装配 `ChargebackChannelService`(注入 supervisor / store / deadline)。 |
| `chargeback_schemas.py` | 拒付请求/响应 DTO(含 assessment / deadline / facts 子对象)。 |
| `cases.py` / `schemas.py` | 基础版(支付异常)案件路由与 DTO。 |
| `feishu.py` / `feishu_schemas.py` | 飞书事件与卡片回调路由(签名校验;未配置飞书返回固定安全 503)。 |
| `health.py` | `GET /health`。 |
| `dependencies.py` | 请求上下文(request_id / trace_id)。 |
| `errors.py` | 异常处理器 + `ProblemDetails`(RFC7807 风格,安全脱敏)。 |

> 路由集合有精确断言:`tests/api/test_lifespan_openapi.py` 与 `tests/foundation/test_foundation_api.py` 锁定 OpenAPI 路径与方法。**新增/删除端点时同步更新这两处。**

应用如何被组装(store/model/deadline 从 `app.state` 取)见 `../main.py`。
