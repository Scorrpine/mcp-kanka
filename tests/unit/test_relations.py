"""Unit tests for Phase D relation CRUD."""

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


def _svc_with_request(response):
    svc = _make_service()
    svc.client = MagicMock()
    svc.client._request = MagicMock(return_value=response)
    return svc


class TestRelationPayload:
    """_relation_payload only sends fields the caller explicitly set."""

    def test_empty_payload_when_all_none(self):
        payload = KankaService._relation_payload(
            owner_id=None,
            target_id=None,
            relation=None,
            attitude=None,
            colour=None,
            is_star=None,
            is_pinned=None,
            is_hidden=None,
            two_way=None,
        )
        assert payload == {}

    def test_is_hidden_translates_to_visibility_id(self):
        hidden = KankaService._relation_payload(
            owner_id=None,
            target_id=None,
            relation=None,
            attitude=None,
            colour=None,
            is_star=None,
            is_pinned=None,
            is_hidden=True,
            two_way=None,
        )
        visible = KankaService._relation_payload(
            owner_id=None,
            target_id=None,
            relation=None,
            attitude=None,
            colour=None,
            is_star=None,
            is_pinned=None,
            is_hidden=False,
            two_way=None,
        )
        assert hidden == {"visibility_id": 2}
        assert visible == {"visibility_id": 1}

    def test_two_way_flag_passes_through(self):
        payload = KankaService._relation_payload(
            owner_id=1,
            target_id=2,
            relation="friend",
            attitude=None,
            colour=None,
            is_star=None,
            is_pinned=None,
            is_hidden=None,
            two_way=True,
        )
        assert payload["two_way"] is True

    def test_all_fields_pass_through(self):
        payload = KankaService._relation_payload(
            owner_id=10,
            target_id=20,
            relation="rival",
            attitude=-50,
            colour="#ff0000",
            is_star=True,
            is_pinned=False,
            is_hidden=None,
            two_way=None,
        )
        assert payload == {
            "owner_id": 10,
            "target_id": 20,
            "relation": "rival",
            "attitude": -50,
            "colour": "#ff0000",
            "is_star": True,
            "is_pinned": False,
        }


class TestRelationToDict:
    """_relation_to_dict normalizes raw Kanka rows to our shape."""

    def test_derives_is_two_way_from_mirror_id(self):
        one_way = KankaService._relation_to_dict({"mirror_id": None})
        two_way = KankaService._relation_to_dict({"mirror_id": 42})
        assert one_way["is_two_way"] is False
        assert two_way["is_two_way"] is True
        assert two_way["mirror_id"] == 42

    def test_visibility_id_translates_to_is_hidden(self):
        visible = KankaService._relation_to_dict({"visibility_id": 1})
        admin_only = KankaService._relation_to_dict({"visibility_id": 2})
        assert visible["is_hidden"] is False
        assert admin_only["is_hidden"] is True

    def test_missing_colour_becomes_empty_string(self):
        assert KankaService._relation_to_dict({"colour": None})["colour"] == ""
        assert KankaService._relation_to_dict({})["colour"] == ""

    def test_boolean_flags_are_coerced(self):
        raw = {"is_star": 1, "is_pinned": 0}
        result = KankaService._relation_to_dict(raw)
        assert result["is_star"] is True
        assert result["is_pinned"] is False


class TestServiceHttpVerbs:
    """The service layer hits the right endpoints and verbs."""

    def test_list_relations_uses_get(self):
        svc = _svc_with_request(
            {
                "data": [
                    {"id": 1, "owner_id": 10, "target_id": 20, "relation": "friend"}
                ]
            }
        )
        result = svc.list_relations(10)
        svc.client._request.assert_called_once_with("GET", "entities/10/relations")
        assert len(result) == 1
        assert result[0]["relation"] == "friend"

    def test_create_relation_posts_with_translated_visibility(self):
        # POST returns data as a list.
        svc = _svc_with_request(
            {
                "data": [
                    {
                        "id": 77,
                        "owner_id": 10,
                        "target_id": 20,
                        "relation": "friend",
                        "attitude": 50,
                        "visibility_id": 2,
                    }
                ]
            }
        )
        result = svc.create_relation(
            owner_id=10,
            target_id=20,
            relation="friend",
            attitude=50,
            is_hidden=True,
        )
        method, url = svc.client._request.call_args.args
        payload = svc.client._request.call_args.kwargs["json"]
        assert method == "POST"
        assert url == "entities/10/relations"
        assert payload == {
            "owner_id": 10,
            "target_id": 20,
            "relation": "friend",
            "attitude": 50,
            "visibility_id": 2,
        }
        assert result["id"] == 77
        assert result["is_hidden"] is True

    def test_create_relation_picks_max_id_from_list_response(self):
        # Kanka's POST /relations returns ``data`` as a cumulative list; the
        # newly-created row is the max-id one.
        svc = _svc_with_request(
            {
                "data": [
                    {"id": 100, "relation": "old"},
                    {"id": 200, "relation": "just-created"},
                    {"id": 150, "relation": "middle"},
                ]
            }
        )
        result = svc.create_relation(owner_id=1, target_id=2, relation="new")
        assert result["id"] == 200
        assert result["relation"] == "just-created"

    def test_create_relation_raises_on_empty_response(self):
        svc = _svc_with_request({"data": []})
        with pytest.raises(ValueError, match="empty response"):
            svc.create_relation(owner_id=1, target_id=2, relation="x")

    def test_update_relation_patches_with_partial_body(self):
        svc = _svc_with_request({"data": {"id": 77, "attitude": 90}})
        svc.update_relation(entity_id=10, relation_id=77, attitude=90)
        method, url = svc.client._request.call_args.args
        payload = svc.client._request.call_args.kwargs["json"]
        assert method == "PATCH"
        assert url == "entities/10/relations/77"
        assert payload == {"attitude": 90}

    def test_update_relation_rejects_empty_payload(self):
        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock()
        with pytest.raises(
            ValueError, match="needs at least one field to update"
        ):
            svc.update_relation(entity_id=10, relation_id=77)

    def test_update_relation_never_sends_two_way(self):
        # two_way flips at creation and can't be edited via PATCH; the payload
        # builder must NEVER include it in an update.
        svc = _svc_with_request({"data": {"id": 77}})
        svc.update_relation(entity_id=10, relation_id=77, attitude=90)
        payload = svc.client._request.call_args.kwargs["json"]
        assert "two_way" not in payload

    def test_delete_relation_uses_delete(self):
        svc = _svc_with_request({})
        assert svc.delete_relation(entity_id=10, relation_id=77) is True
        svc.client._request.assert_called_once_with(
            "DELETE", "entities/10/relations/77"
        )


class TestBatchRelationOperations:
    """Batch operations aggregate per-item results without short-circuiting."""

    @pytest.mark.asyncio
    async def test_create_relations_mixes_success_and_validation_failure(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            side_effect=[
                {"data": [{"id": 100, "owner_id": 1, "target_id": 2, "relation": "a"}]},
                {"data": [{"id": 101, "owner_id": 1, "target_id": 3, "relation": "b"}]},
            ]
        )
        ops = KankaOperations(service=svc)

        result = await ops.create_relations(
            [
                {"owner_id": 1, "target_id": 2, "relation": "a"},
                {"owner_id": 1, "target_id": 3, "relation": "b"},
                {"target_id": 4, "relation": "orphan"},  # missing owner_id
                {"owner_id": 1, "target_id": 5},  # missing relation
            ]
        )
        assert [r["success"] for r in result] == [True, True, False, False]
        assert result[0]["relation_id"] == 100
        assert result[1]["relation_id"] == 101
        # Malformed items never hit HTTP.
        assert svc.client._request.call_count == 2

    @pytest.mark.asyncio
    async def test_create_relations_captures_mirror_id(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            return_value={
                "data": [
                    {
                        "id": 200,
                        "owner_id": 1,
                        "target_id": 2,
                        "relation": "rival",
                        "mirror_id": 201,
                    }
                ]
            }
        )
        ops = KankaOperations(service=svc)

        result = await ops.create_relations(
            [
                {
                    "owner_id": 1,
                    "target_id": 2,
                    "relation": "rival",
                    "two_way": True,
                }
            ]
        )
        assert result[0]["relation_id"] == 200
        assert result[0]["mirror_id"] == 201

    @pytest.mark.asyncio
    async def test_update_relations_reports_per_item_failure(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            side_effect=[{"data": {"id": 77}}, Exception("nope")]
        )
        ops = KankaOperations(service=svc)

        result = await ops.update_relations(
            [
                {"entity_id": 10, "relation_id": 77, "attitude": 100},
                {"entity_id": 10, "relation_id": 88, "attitude": 100},
            ]
        )
        assert result[0]["success"] is True
        assert result[1]["success"] is False
        assert "nope" in (result[1]["error"] or "")

    @pytest.mark.asyncio
    async def test_delete_relations_reports_per_item(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(side_effect=[{}, Exception("gone")])
        ops = KankaOperations(service=svc)

        result = await ops.delete_relations(
            [
                {"entity_id": 10, "relation_id": 77},
                {"entity_id": 10, "relation_id": 88},
            ]
        )
        assert result[0]["success"] is True
        assert result[1]["success"] is False
