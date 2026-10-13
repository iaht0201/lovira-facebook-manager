import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from lovira.integrations.facebook.page_enrichment import PageEnrichmentClient, GraphRequestError


class DummyClient:
    api_version = "v21.0"
    timeout = 12


class PageEnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.service = PageEnrichmentClient(DummyClient())

    @patch.dict(os.environ, {"LOVIRA_FB_APP_ID": "", "LOVIRA_FB_APP_SECRET": ""})
    def test_unverified_when_no_grants_are_proven(self):
        self.service._get = lambda endpoint, token, **args: {"id": "123", "name": "Example"}
        audit = self.service.inspect_page_token("123", "EAA_token", [])
        self.assertEqual(audit["status"], "unverified")
        self.assertIsNone(audit["expires_at"])

    @patch.dict(os.environ, {"LOVIRA_FB_APP_ID": "", "LOVIRA_FB_APP_SECRET": ""})
    def test_ready_only_with_publish_task(self):
        self.service._get = lambda endpoint, token, **args: {"id": "123", "name": "Example"}
        self.assertEqual(self.service.inspect_page_token("123", "token", ["CREATE_CONTENT"])["status"], "ready")
        self.assertEqual(self.service.inspect_page_token("123", "token", ["ANALYZE"])["status"],
                         "insufficient_permissions")

    def test_mismatched_id_cannot_replace_token(self):
        self.service._get = lambda endpoint, token, **args: {"id": "456", "name": "Wrong"}
        with self.assertRaises(GraphRequestError):
            self.service.inspect_page_token("123", "token", [])

    def test_expired_token_190(self):
        def fake(*_a, **_kw):
            raise GraphRequestError("Token revoked", code=190)
        self.service._get = fake
        data = self.service.inspect_page_token("123", "token")
        self.assertEqual(data["status"], "token_expired")

    def test_network_failure_is_not_expiry(self):
        def fake(*_a, **_kw):
            raise GraphRequestError("Mạng lỗi", kind="network")
        self.service._get = fake
        with self.assertRaises(GraphRequestError) as ctx:
            self.service.inspect_page_token("123", "token")
        self.assertIsNone(ctx.exception.code)

    def test_partial_public_data(self):
        def fake(_endpoint, _token, **params):
            fields = params["fields"]
            if "picture" in fields:
                return {"id": "123", "name": "Example", "picture": {"data": {"url": "https://example.com/p.png"}}}
            if fields == "followers_count,fan_count":
                raise GraphRequestError("field blocked", code=100)
            if fields == "followers_count":
                return {"followers_count": 315}
            if fields == "fan_count":
                raise GraphRequestError("field blocked", code=100)
            return {}
        self.service._get = fake
        profile = self.service.fetch_public_info("123", "token")
        self.assertEqual(profile["followers_count"], 315)
        self.assertNotIn("fan_count", profile)
        self.assertEqual(profile["avatar_url"], "https://example.com/p.png")


if __name__ == "__main__":
    unittest.main()
