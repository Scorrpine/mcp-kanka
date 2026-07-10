"""Unit tests for Phase C attribute CRUD."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_kanka.service import KankaService
from mcp_kanka.types import (
    ATTRIBUTE_ID_TO_TYPE,
    ATTRIBUTE_TYPE_TO_ID,
    VALID_ATTRIBUTE_TYPES,
)


def _make_service():
    with patch("os.getenv") as mock_getenv, patch("mcp_kanka.service.KankaClient"):
        mock_getenv.side_effect = lambda key: {
            "KANKA_TOKEN": "test",
            "KANKA_CAMPAIGN_ID": "1",
        }.get(key)
        return KankaService()


class TestAttributeTypeConstants:
    """The type-name <-> type_id round trip."""

    def test_valid_attribute_types_matches_mapping(self):
        assert set(VALID_ATTRIBUTE_TYPES) == set(ATTRIBUTE_TYPE_TO_ID.keys())

    def test_id_to_type_is_reverse_of_type_to_id(self):
        for name, tid in ATTRIBUTE_TYPE_TO_ID.items():
            assert ATTRIBUTE_ID_TO_TYPE[tid] == name

    def test_expected_ids_confirmed_by_live_probe(self):
        # Values verified against a live Kanka campaign on 2026-07-10.
        assert ATTRIBUTE_TYPE_TO_ID["standard"] == 1
        assert ATTRIBUTE_TYPE_TO_ID["number"] == 2
        assert ATTRIBUTE_TYPE_TO_ID["checkbox"] == 3
        assert ATTRIBUTE_TYPE_TO_ID["section"] == 4
        assert ATTRIBUTE_TYPE_TO_ID["random"] == 5


class TestAttributePayload:
    """_attribute_payload only sends fields the caller explicitly set."""

    def test_empty_payload_when_all_none(self):
        svc = _make_service()
        payload = svc._attribute_payload(
            name=None,
            value=None,
            type=None,
            is_pinned=None,
            is_private=None,
            is_star=None,
            default_order=None,
            api_key=None,
        )
        assert payload == {}

    def test_type_string_translated_to_type_id(self):
        svc = _make_service()
        payload = svc._attribute_payload(
            name="HP",
            value="25",
            type="number",
            is_pinned=None,
            is_private=None,
            is_star=None,
            default_order=None,
            api_key=None,
        )
        assert payload == {"name": "HP", "value": "25", "type_id": 2}

    def test_invalid_type_raises(self):
        svc = _make_service()
        with pytest.raises(ValueError, match="Invalid attribute type"):
            svc._attribute_payload(
                name="X",
                value=None,
                type="broken",  # type: ignore[arg-type]
                is_pinned=None,
                is_private=None,
                is_star=None,
                default_order=None,
                api_key=None,
            )

    def test_all_optional_flags_pass_through(self):
        svc = _make_service()
        payload = svc._attribute_payload(
            name=None,
            value=None,
            type=None,
            is_pinned=True,
            is_private=False,
            is_star=True,
            default_order=5,
            api_key="hp_current",
        )
        assert payload == {
            "is_pinned": True,
            "is_private": False,
            "is_star": True,
            "default_order": 5,
            "api_key": "hp_current",
        }


class TestAttributeToDict:
    """Normalizing a raw Kanka attribute dict to our shape."""

    def test_type_id_translates_to_type_string(self):
        raw = {"id": 1, "entity_id": 2, "name": "HP", "type_id": 2, "value": "25"}
        result = KankaService._attribute_to_dict(raw)
        assert result["type"] == "number"
        assert result["type_id"] == 2

    def test_null_type_id_defaults_to_standard(self):
        raw = {"id": 1, "entity_id": 2, "name": "HP", "type_id": None}
        result = KankaService._attribute_to_dict(raw)
        assert result["type"] == "standard"
        assert result["type_id"] == 1

    def test_unknown_type_id_defaults_to_standard(self):
        raw = {"id": 1, "entity_id": 2, "name": "HP", "type_id": 99}
        result = KankaService._attribute_to_dict(raw)
        assert result["type"] == "standard"

    def test_missing_name_becomes_empty_string(self):
        result = KankaService._attribute_to_dict({"id": 1, "entity_id": 2})
        assert result["name"] == ""

    def test_boolean_flags_are_coerced(self):
        # Kanka may return 0/1 or true/false; our shape is always bool.
        raw = {
            "id": 1,
            "entity_id": 2,
            "is_pinned": 1,
            "is_private": 0,
            "is_star": True,
        }
        result = KankaService._attribute_to_dict(raw)
        assert result["is_pinned"] is True
        assert result["is_private"] is False
        assert result["is_star"] is True

    def test_preserves_checkbox_bool_value(self):
        # For a checkbox attribute Kanka returns value as a bool.
        raw = {"id": 1, "entity_id": 2, "type_id": 3, "value": True}
        result = KankaService._attribute_to_dict(raw)
        assert result["value"] is True
        assert result["type"] == "checkbox"


class TestServiceHttpVerbs:
    """The service layer hits the right endpoints and verbs."""

    def _make_svc_with_client(self, request_return=None):
        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            return_value=request_return if request_return is not None else {"data": {}}
        )
        return svc

    def test_list_attributes_hits_get(self):
        svc = self._make_svc_with_client(
            {"data": [{"id": 1, "entity_id": 42, "name": "HP", "type_id": 1}]}
        )
        result = svc.list_attributes(42)
        svc.client._request.assert_called_once_with(
            "GET", "entities/42/attributes"
        )
        assert len(result) == 1
        assert result[0]["name"] == "HP"

    def test_create_attribute_posts_with_translated_type(self):
        svc = self._make_svc_with_client(
            {"data": {"id": 7, "entity_id": 42, "name": "HP", "type_id": 2}}
        )
        result = svc.create_attribute(
            entity_id=42, name="HP", value="25", type="number", is_pinned=True
        )
        method, url = svc.client._request.call_args.args
        payload = svc.client._request.call_args.kwargs["json"]
        assert method == "POST"
        assert url == "entities/42/attributes"
        assert payload == {
            "name": "HP",
            "value": "25",
            "type_id": 2,
            "is_pinned": True,
        }
        assert result["id"] == 7

    def test_create_attribute_defaults_omits_type_id(self):
        # When type is not provided, we shouldn't fabricate a type_id.
        svc = self._make_svc_with_client({"data": {"id": 1, "entity_id": 42}})
        svc.create_attribute(entity_id=42, name="Notes")
        payload = svc.client._request.call_args.kwargs["json"]
        assert "type_id" not in payload
        assert payload == {"name": "Notes"}

    def test_update_attribute_patches_with_partial_body(self):
        svc = self._make_svc_with_client({"data": {"id": 7, "entity_id": 42}})
        svc.update_attribute(entity_id=42, attribute_id=7, value="99")
        method, url = svc.client._request.call_args.args
        payload = svc.client._request.call_args.kwargs["json"]
        assert method == "PATCH"
        assert url == "entities/42/attributes/7"
        assert payload == {"value": "99"}

    def test_update_attribute_rejects_empty_payload(self):
        svc = self._make_svc_with_client()
        with pytest.raises(
            ValueError, match="needs at least one field to update"
        ):
            svc.update_attribute(entity_id=42, attribute_id=7)

    def test_delete_attribute_hits_delete(self):
        svc = self._make_svc_with_client({})
        assert svc.delete_attribute(entity_id=42, attribute_id=7) is True
        svc.client._request.assert_called_once_with(
            "DELETE", "entities/42/attributes/7"
        )


class TestBatchOperations:
    """Batch operations aggregate per-item results without short-circuiting."""

    @pytest.mark.asyncio
    async def test_create_attributes_reports_per_item_success(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        # Alternate success/failure on each call
        seq = [{"data": {"id": 100 + i, "entity_id": 1, "name": f"A{i}"}} for i in range(2)]
        seq.append(Exception("boom"))
        svc.client = MagicMock()
        svc.client._request = MagicMock(side_effect=seq)
        ops = KankaOperations(service=svc)

        result = await ops.create_attributes(
            [
                {"entity_id": 1, "name": "A0"},
                {"entity_id": 1, "name": "A1"},
                {"entity_id": 1, "name": "A2"},
            ]
        )
        assert [r["success"] for r in result] == [True, True, False]
        assert result[0]["attribute_id"] == 100
        assert result[1]["attribute_id"] == 101
        assert result[2]["attribute_id"] is None
        assert "boom" in (result[2]["error"] or "")

    @pytest.mark.asyncio
    async def test_create_attributes_rejects_missing_required(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock()
        ops = KankaOperations(service=svc)

        result = await ops.create_attributes(
            [
                {"name": "OrphanNoEntity"},
                {"entity_id": 1},  # missing name
            ]
        )
        assert all(not r["success"] for r in result)
        # And the HTTP layer was never hit for these malformed items.
        svc.client._request.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_attributes_reports_per_item_failure(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            side_effect=[{"data": {"id": 7}}, Exception("nope")]
        )
        ops = KankaOperations(service=svc)

        result = await ops.update_attributes(
            [
                {"entity_id": 1, "attribute_id": 7, "value": "x"},
                {"entity_id": 1, "attribute_id": 8, "value": "y"},
            ]
        )
        assert result[0]["success"] is True
        assert result[1]["success"] is False
        assert "nope" in (result[1]["error"] or "")

    @pytest.mark.asyncio
    async def test_delete_attributes_reports_per_item(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(side_effect=[{}, Exception("gone")])
        ops = KankaOperations(service=svc)

        result = await ops.delete_attributes(
            [
                {"entity_id": 1, "attribute_id": 7},
                {"entity_id": 1, "attribute_id": 8},
            ]
        )
        assert result[0]["success"] is True
        assert result[1]["success"] is False
