from html.parser import HTMLParser

from oceanpilot.web.rendering import (
    render_business_page,
    render_merchant_page,
    render_operations_page,
)


class AssetReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.external_assets = []
        self.embedded_images = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "script" and "src" in attributes:
            self.external_assets.append(attributes["src"])
        if tag == "link" and attributes.get("rel") == "stylesheet":
            self.external_assets.append(attributes.get("href"))
        if tag == "img":
            self.embedded_images.append(attributes.get("src", ""))


def test_composed_pages_still_embed_every_runtime_asset():
    for body in (
        render_merchant_page(),
        render_business_page(),
        render_operations_page("http://127.0.0.1:8002"),
    ):
        references = AssetReferences()
        references.feed(body)
        assert not references.external_assets
        assert references.embedded_images
        assert all(src.startswith("data:image/png;base64,") for src in references.embedded_images)
        assert "__PAGE_SCRIPT__" not in body
        assert "__PAGE_STYLES__" not in body
        assert "__OCEANPAYMENT_LOGO__" not in body
        assert "__WORKSPACE_CONFIG__" not in body
        assert "__ROLE_LABEL__" not in body


def test_operations_configuration_does_not_leak_between_app_instances():
    first = render_operations_page("http://127.0.0.1:9123/")
    second = render_operations_page("http://127.0.0.1:9456")
    assert 'const CLIENT_BASE="http://127.0.0.1:9123"' in first
    assert "9456" not in first
    assert 'const CLIENT_BASE="http://127.0.0.1:9456"' in second
    assert "9123" not in second
