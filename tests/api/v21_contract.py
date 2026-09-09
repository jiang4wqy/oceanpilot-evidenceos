"""Reviewed additive V2.1 HTTP contract, shared by the foundation snapshots."""

V21_PATHS = {
    "/api/v2/session",
    "/api/v2/session/login",
    "/api/v2/session/logout",
    "/api/v2/runtime",
    "/api/v2/director/accounts",
    "/api/v2/director/accounts/{user_id}/status",
    "/api/v2/director/transactions",
    "/api/v2/intake/events",
    "/api/v2/intake/events/{event_id}/retry",
    "/api/v2/command-schemas",
    "/api/v2/cases/{case_id}/collaboration",
    "/api/v2/cases/{case_id}/collaboration/messages",
    "/api/v2/cases/{case_id}/collaboration/read",
    "/api/v2/cases/{case_id}/collaboration/handoffs",
    "/api/v2/cases/{case_id}/collaboration/handoffs/{handoff_id}",
    "/api/v2/cases/{case_id}/collaboration/files",
    "/api/v2/cases/{case_id}/collaboration/files/{object_id}",
    "/api/v2/integrations/feishu/outbox",
    "/api/v2/integrations/feishu/outbox/{outbox_id}/send",
}


V21_METHODS = {
    path: (
        {"get", "post"}
        if path
        in {
            "/api/v2/director/accounts",
            "/api/v2/director/transactions",
            "/api/v2/intake/events",
            "/api/v2/integrations/feishu/outbox",
        }
        else {"get"}
        if path
        in {
            "/api/v2/session",
            "/api/v2/runtime",
            "/api/v2/command-schemas",
            "/api/v2/cases/{case_id}/collaboration",
            "/api/v2/cases/{case_id}/collaboration/files/{object_id}",
        }
        else {"post"}
    )
    for path in V21_PATHS
}
