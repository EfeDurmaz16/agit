"""Integration tests for the REST API server."""
from __future__ import annotations

import pytest

try:
    from fastapi.testclient import TestClient
    from agit.server.app import app
    from agit.server.auth import register_api_key
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False


@pytest.mark.skipif(not _FASTAPI_AVAILABLE, reason="fastapi not installed")
class TestServerAPI:
    """Test REST API endpoints."""

    @pytest.fixture(autouse=True)
    def setup(self):
        register_api_key("agit-test-key", tenant="test", agent_id="test-agent")
        self.client = TestClient(app)
        self.headers = {"X-API-Key": "agit-test-key"}

    def test_root(self):
        resp = self.client.get("/")
        assert resp.status_code == 200
        assert resp.json()["name"] == "agit API"

    def test_health(self):
        resp = self.client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_commit_and_list(self):
        # Create a commit
        resp = self.client.post(
            "/api/v1/commits",
            json={"state": {"memory": {"step": 1}, "world_state": {}}, "message": "test"},
            headers=self.headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "hash" in data

        # List commits
        resp = self.client.get("/api/v1/commits", headers=self.headers)
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_branches(self):
        # Create some state first
        self.client.post(
            "/api/v1/commits",
            json={"state": {"memory": {}, "world_state": {}}, "message": "init"},
            headers=self.headers,
        )

        # Create branch
        resp = self.client.post(
            "/api/v1/branches",
            json={"name": "test-branch"},
            headers=self.headers,
        )
        assert resp.status_code == 200

        # List branches
        resp = self.client.get("/api/v1/branches", headers=self.headers)
        assert resp.status_code == 200
        assert "test-branch" in resp.json()["branches"]

    def test_search(self):
        self.client.post(
            "/api/v1/commits",
            json={"state": {"memory": {}, "world_state": {}}, "message": "searchable test"},
            headers=self.headers,
        )
        resp = self.client.get(
            "/api/v1/search?q=searchable",
            headers=self.headers,
        )
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_audit(self):
        resp = self.client.get("/api/v1/audit", headers=self.headers)
        assert resp.status_code == 200
        assert "entries" in resp.json()

    def test_invalid_api_key(self):
        resp = self.client.get(
            "/api/v1/commits",
            headers={"X-API-Key": "invalid-key"},
        )
        assert resp.status_code == 401
