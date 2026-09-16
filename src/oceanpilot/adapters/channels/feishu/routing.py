"""Route only verified envelopes. Never route a group query to the case service."""

from oceanpilot.adapters.channels.feishu.v2 import FeishuV2Error


class FeishuMessageRouter:
    def __init__(self, public, private):
        self.public, self.private = public, private

    def handle(self, payload, *, mode):
        event = payload.get("event", {})
        if not isinstance(event, dict):
            raise FeishuV2Error("INVALID_CALLBACK")
        if mode == "card":
            # Private adapter checks verified user, immutable binding version,
            # verified DM address AND the original delivered message receipt.
            return self.private.handle(payload, mode=mode)
        message = event.get("message", {})
        if not isinstance(message, dict):
            raise FeishuV2Error("INVALID_CALLBACK")
        if message.get("chat_type") == "p2p":
            return self.private.handle(payload, mode=mode)
        return self.public.handle(payload, mode=mode)

    def start(self):
        self.public.start()
        self.private.start()

    def close(self):
        self.public.close()
        self.private.close()
