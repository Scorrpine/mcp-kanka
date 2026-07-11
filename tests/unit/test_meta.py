"""Unit tests for Phase I meta endpoints (campaign, roles, users)."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_kanka.service import KankaService


def _make_service():
    with patch("os.getenv") as mock_getenv, patch("mcp_kanka.service.KankaClient"):
        mock_getenv.side_effect = lambda key: {
            "KANKA_TOKEN": "test",
            "KANKA_CAMPAIGN_ID": "1",
        }.get(key)
        return KankaService()


def _svc(response):
    svc = _make_service()
    svc.client = MagicMock()
    svc.client._request = MagicMock(return_value=response)
    return svc


class TestGetCampaign:
    def test_hits_root_endpoint(self):
        svc = _svc(
            {
                "data": {
                    "id": 42,
                    "name": "Ethringdal",
                    "slug": "ethringdal",
                    "visibility_id": 1,
                }
            }
        )
        result = svc.get_campaign()
        # ``GET ""`` maps to the campaign endpoint at the API root.
        svc.client._request.assert_called_once_with("GET", "")
        assert result["name"] == "Ethringdal"
        assert result["slug"] == "ethringdal"
        assert result["is_hidden"] is False

    def test_visibility_id_2_marks_hidden(self):
        svc = _svc({"data": {"id": 1, "visibility_id": 2}})
        assert svc.get_campaign()["is_hidden"] is True

    def test_description_converts_html_to_markdown(self):
        svc = _svc({"data": {"id": 1, "description_raw": "<p><b>Hello</b></p>"}})
        result = svc.get_campaign()
        # Markdown output should contain some form of bold marker.
        assert result["description"] is not None
        assert "Hello" in result["description"]

    def test_missing_settings_defaults_to_empty_dict(self):
        svc = _svc({"data": {"id": 1}})
        result = svc.get_campaign()
        assert result["settings"] == {}
        assert result["ui_settings"] == {}


class TestListRoles:
    def test_hits_roles_endpoint(self):
        svc = _svc(
            {
                "data": [
                    {"id": 1, "name": "Admin", "is_admin": True},
                    {"id": 2, "name": "Player", "is_admin": False},
                ]
            }
        )
        result = svc.list_roles()
        svc.client._request.assert_called_once_with("GET", "roles")
        assert len(result) == 2
        assert result[0]["is_admin"] is True
        assert result[1]["is_admin"] is False

    def test_coerces_is_admin_to_bool(self):
        svc = _svc({"data": [{"id": 1, "name": "A", "is_admin": 1}]})
        assert svc.list_roles()[0]["is_admin"] is True


class TestListCampaignUsers:
    def test_hits_users_endpoint(self):
        svc = _svc(
            {
                "data": [
                    {
                        "id": 100,
                        "name": "scorrpine",
                        "avatar": None,
                        "role": [
                            {"id": 1, "name": "Admin", "is_admin": True}
                        ],
                    }
                ]
            }
        )
        result = svc.list_campaign_users()
        svc.client._request.assert_called_once_with("GET", "users")
        assert result[0]["name"] == "scorrpine"
        assert len(result[0]["roles"]) == 1
        assert result[0]["roles"][0]["name"] == "Admin"

    def test_single_role_dict_normalizes_to_list(self):
        svc = _svc(
            {
                "data": [
                    {
                        "id": 100,
                        "name": "user",
                        "role": {"id": 1, "name": "Player", "is_admin": False},
                    }
                ]
            }
        )
        result = svc.list_campaign_users()
        assert isinstance(result[0]["roles"], list)
        assert result[0]["roles"][0]["name"] == "Player"

    def test_missing_role_yields_empty_list(self):
        svc = _svc({"data": [{"id": 100, "name": "user"}]})
        assert svc.list_campaign_users()[0]["roles"] == []


class TestMetaOperations:
    @pytest.mark.asyncio
    async def test_get_campaign_wraps_result(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            return_value={"data": {"id": 1, "name": "Ethringdal"}}
        )
        ops = KankaOperations(service=svc)
        r = await ops.get_campaign()
        assert r["success"] is True
        assert r["campaign"]["name"] == "Ethringdal"

    @pytest.mark.asyncio
    async def test_get_campaign_catches_error(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(side_effect=Exception("network"))
        ops = KankaOperations(service=svc)
        r = await ops.get_campaign()
        assert r["success"] is False
        assert "network" in (r["error"] or "")
        assert r["campaign"] == {}

    @pytest.mark.asyncio
    async def test_list_roles_catches_error(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(side_effect=Exception("boom"))
        ops = KankaOperations(service=svc)
        r = await ops.list_roles()
        assert r["success"] is False
        assert r["roles"] == []

    @pytest.mark.asyncio
    async def test_list_campaign_users_catches_error(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(side_effect=Exception("boom"))
        ops = KankaOperations(service=svc)
        r = await ops.list_campaign_users()
        assert r["success"] is False
        assert r["users"] == []
