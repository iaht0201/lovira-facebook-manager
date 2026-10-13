import os
import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import contextmanager

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from lovira.storage.page_profiles import PageProfileStore


class FakeDB:
    def __init__(self, path):
        self.path = path

    @contextmanager
    def connection_scope(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        with self.connection_scope() as conn:
            with conn:
                yield conn


class PageProfileStoreTests(unittest.TestCase):
    def test_public_merge_and_token_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = FakeDB(str(Path(tmp) / "lovira.db"))
            with db.transaction() as conn:
                conn.execute("CREATE TABLE pages(id TEXT PRIMARY KEY, name TEXT, avatar_url TEXT, status TEXT, updated_at TEXT)")
                conn.execute("INSERT INTO pages(id,name,avatar_url,status) VALUES ('page_1','Old','', 'unverified')")
            store = PageProfileStore(db)
            store.save_public("page_1", {"name": "New", "followers_count": 123})
            store.save_public("page_1", {"website": "https://example.com"})
            store.save_token_meta("page_1", {"status": "ready", "expires_at": 0,
                                              "access_token": "SECRET_SHOULD_NOT_STORE"})
            result = store.get("page_1")
            self.assertEqual(result["public"]["followers_count"], 123)
            self.assertEqual(result["public"]["website"], "https://example.com")
            self.assertEqual(result["token"]["expires_at"], 0)
            self.assertNotIn("access_token", result["token"])
            store.set_status("page_1", "ready")
            with db.connection_scope() as conn:
                self.assertEqual(conn.execute("SELECT status FROM pages").fetchone()[0], "ready")
                conn.execute("DELETE FROM pages WHERE id='page_1'")
                conn.commit()
            self.assertEqual(store.get_all(), {})


if __name__ == "__main__":
    unittest.main()
