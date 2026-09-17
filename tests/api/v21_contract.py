"""Reviewed additive V2.1 HTTP contract, shared by the foundation snapshots."""

V21_PATHS = {
    "/api/v2/session",
    "/api/v2/session/login",
    "/api/v2/session/logout",
    "/api/v2/runtime",
    "/api/v2/admin/accounts",
    "/api/v2/admin/accounts/{user_id}/status",
    "/api/v2/admin/transactions",
    "/api/v2/intake/events",
    "/api/v2/intake/events/{event_id}/retry",
    "/api/v2/intake/simulations/preview",
    "/api/v2/intake/simulations",
    "/api/v2/command-schemas",
    "/api/v2/cases/{case_id}/collaboration",
    "/api/v2/cases/{case_id}/collaboration/messages",
    "/api/v2/cases/{case_id}/collaboration/read",
    "/api/v2/cases/{case_id}/collaboration/handoffs",
    "/api/v2/cases/{case_id}/collaboration/handoffs/{handoff_id}",
    "/api/v2/cases/{case_id}/collaboration/files",
    "/api/v2/cases/{case_id}/collaboration/files/{object_id}",
    "/api/v2/cases/{case_id}/collaboration/files/{object_id}/pages/{page_number}",
    "/api/v2/integrations/feishu/outbox",
    "/api/v2/integrations/feishu/outbox/{outbox_id}/send",
    "/api/v2/integrations/feishu/binding",
    "/api/v2/integrations/feishu/binding/pairs",
    "/api/v2/integrations/feishu/binding/pairs/{pair_id}",
    "/api/v2/integrations/feishu/binding/pairs/{pair_id}/confirm",
}


V21_METHODS = {
    path: (
        {"get", "post"}
        if path
        in {
            "/api/v2/admin/accounts",
            "/api/v2/admin/transactions",
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
            "/api/v2/cases/{case_id}/collaboration/files/{object_id}/pages/{page_number}",
            "/api/v2/integrations/feishu/binding/pairs/{pair_id}",
        }
        else {"post"}
    )
    for path in V21_PATHS
}
V21_METHODS["/api/v2/integrations/feishu/binding"] = {"get", "delete"}
