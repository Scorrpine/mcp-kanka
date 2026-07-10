"""Unit tests for Phase B entity-type additions in the Scorrpine fork.

These tests cover the additive extensions this fork makes over upstream 1.1.x:
extended EntityType union (adds calendar, event, family, item, ability,
timeline, tag as first-class), the HTTP-backed manager shim, and the
_HttpEntityFacade attribute/datetime proxy.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from mcp_kanka.service import (
    KANKA_TYPE_TO_OUR,
    _HttpEntityFacade,
    _HttpEntityShim,
    _parse_dt,
    KankaService,
)
from mcp_kanka.types import (
    HTTP_BACKED_TYPES,
    MANAGER_BACKED_TYPES,
    VALID_ENTITY_TYPES,
)

# The set of entity types this fork adds over upstream 1.1.x. Kept explicit so
# a regression that silently drops one is obvious.
NEW_TYPES = frozenset(
    {"ability", "calendar", "event", "family", "item", "tag", "timeline"}
)

# Types that upstream 1.1.x already supported. Kept for the completeness check.
UPSTREAM_TYPES = frozenset(
    {
        "character",
        "creature",
        "journal",
        "location",
        "note",
        "organization",
        "quest",
        "race",
    }
)


class TestValidEntityTypes:
    """VALID_ENTITY_TYPES and its partition invariants."""

    def test_valid_entity_types_contains_all_new_types(self):
        assert NEW_TYPES.issubset(set(VALID_ENTITY_TYPES))

    def test_valid_entity_types_still_contains_upstream_types(self):
        assert UPSTREAM_TYPES.issubset(set(VALID_ENTITY_TYPES))

    def test_valid_entity_types_size_matches_union(self):
        assert set(VALID_ENTITY_TYPES) == UPSTREAM_TYPES | NEW_TYPES

    def test_partition_is_disjoint(self):
        assert MANAGER_BACKED_TYPES.isdisjoint(HTTP_BACKED_TYPES)

    def test_partition_covers_all_valid_types(self):
        assert set(VALID_ENTITY_TYPES) == MANAGER_BACKED_TYPES | HTTP_BACKED_TYPES

    def test_calendar_is_http_backed_due_to_upstream_bug(self):
        # python-kanka 2.6.2 has a Calendar model bug; we route around it.
        assert "calendar" in HTTP_BACKED_TYPES

    def test_kanka_type_to_our_covers_every_valid_type(self):
        # KANKA_TYPE_TO_OUR is the reverse lookup used by get_entity_by_id.
        our_types = set(KANKA_TYPE_TO_OUR.values())
        assert set(VALID_ENTITY_TYPES) == our_types


class TestParseDt:
    """_parse_dt helper for ISO 8601 timestamp strings."""

    def test_parses_utc_z_suffix(self):
        result = _parse_dt("2026-04-01T12:34:56.000000Z")
        assert result is not None
        assert result.year == 2026 and result.month == 4 and result.day == 1
        assert result.tzinfo is not None

    def test_parses_offset(self):
        result = _parse_dt("2026-04-01T12:34:56+00:00")
        assert result is not None

    def test_returns_none_for_none(self):
        assert _parse_dt(None) is None

    def test_returns_none_for_bad_input(self):
        assert _parse_dt("not-a-datetime") is None

    def test_passes_through_datetime(self):
        dt = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
        assert _parse_dt(dt) is dt


class TestHttpEntityFacade:
    """_HttpEntityFacade wraps a raw dict with attribute access."""

    def test_basic_attribute_lookup(self):
        f = _HttpEntityFacade({"id": 7, "name": "Sword"})
        assert f.id == 7
        assert f.name == "Sword"

    def test_missing_attribute_raises(self):
        f = _HttpEntityFacade({"id": 7})
        with pytest.raises(AttributeError):
            _ = f.nonexistent  # noqa: F841

    def test_created_at_parses_to_datetime(self):
        f = _HttpEntityFacade({"created_at": "2026-04-01T12:34:56.000000Z"})
        dt = f.created_at
        assert isinstance(dt, datetime)
        # And it survives .isoformat() the way _entity_to_dict expects.
        assert "2026" in dt.isoformat()

    def test_updated_at_parses_to_datetime(self):
        f = _HttpEntityFacade({"updated_at": "2026-05-15T00:00:00Z"})
        assert isinstance(f.updated_at, datetime)

    def test_created_at_none_returns_none(self):
        f = _HttpEntityFacade({"created_at": None})
        assert f.created_at is None

    def test_nested_list_of_dicts_is_wrapped(self):
        # e.g. posts when related=True
        f = _HttpEntityFacade(
            {"posts": [{"id": 1, "name": "First"}, {"id": 2, "name": "Second"}]}
        )
        posts = f.posts
        assert len(posts) == 2
        assert isinstance(posts[0], _HttpEntityFacade)
        assert posts[0].id == 1 and posts[1].name == "Second"

    def test_list_of_ints_not_wrapped(self):
        # e.g. tags as list of tag IDs
        f = _HttpEntityFacade({"tags": [1, 2, 3]})
        assert f.tags == [1, 2, 3]

    def test_hasattr_works(self):
        f = _HttpEntityFacade({"id": 5})
        assert hasattr(f, "id")
        assert not hasattr(f, "nonexistent")

    def test_immutable_via_shallow_copy(self):
        original = {"id": 1}
        f = _HttpEntityFacade(original)
        original["id"] = 999
        # Facade holds its own copy of the top-level dict.
        assert f.id == 1


class TestHttpEntityShim:
    """_HttpEntityShim speaks the EntityManager interface via raw HTTP."""

    def _make_shim(self, response=None):
        client = Mock()
        client._request = MagicMock(
            return_value=response if response is not None else {"data": []}
        )
        return _HttpEntityShim(client, "abilities"), client

    def test_list_hits_correct_endpoint(self):
        shim, client = self._make_shim({"data": [{"id": 1, "name": "Fireball"}]})
        results = shim.list(page=2)
        client._request.assert_called_once_with(
            "GET", "abilities", params={"page": 2}
        )
        assert len(results) == 1
        assert isinstance(results[0], _HttpEntityFacade)
        assert results[0].name == "Fireball"

    def test_list_tracks_has_next_page(self):
        shim, _ = self._make_shim(
            {"data": [], "links": {"next": "https://.../abilities?page=3"}}
        )
        shim.list(page=2)
        assert shim.has_next_page is True

    def test_list_no_next_page(self):
        shim, _ = self._make_shim({"data": [], "links": {"next": None}})
        shim.list()
        assert shim.has_next_page is False

    def test_list_passes_related_flag(self):
        shim, client = self._make_shim()
        shim.list(page=1, related=True)
        params = client._request.call_args.kwargs["params"]
        assert params["related"] == 1

    def test_list_passes_extra_filters(self):
        shim, client = self._make_shim()
        shim.list(page=1, lastSync="2026-01-01T00:00:00Z", name="test")
        params = client._request.call_args.kwargs["params"]
        assert params["lastSync"] == "2026-01-01T00:00:00Z"
        assert params["name"] == "test"

    def test_list_drops_none_filters(self):
        shim, client = self._make_shim()
        shim.list(page=1, lastSync=None)
        params = client._request.call_args.kwargs["params"]
        assert "lastSync" not in params

    def test_get_hits_correct_endpoint(self):
        shim, client = self._make_shim({"data": {"id": 42, "name": "Cleave"}})
        result = shim.get(42)
        client._request.assert_called_once_with("GET", "abilities/42")
        assert result.id == 42

    def test_create_sends_json_body(self):
        shim, client = self._make_shim({"data": {"id": 99, "name": "New"}})
        result = shim.create(name="New", entry="body")
        client._request.assert_called_once_with(
            "POST", "abilities", json={"name": "New", "entry": "body"}
        )
        assert result.id == 99

    def test_update_uses_put(self):
        shim, client = self._make_shim({"data": {"id": 5, "name": "Renamed"}})
        shim.update(5, name="Renamed")
        client._request.assert_called_once_with(
            "PUT", "abilities/5", json={"name": "Renamed"}
        )

    def test_delete_uses_delete(self):
        shim, client = self._make_shim({})
        shim.delete(7)
        client._request.assert_called_once_with("DELETE", "abilities/7")

    def test_create_post_uses_entities_endpoint(self):
        # Posts are always at /entities/<entity_id>/posts, not
        # /abilities/<id>/posts.
        shim, client = self._make_shim({"data": {"id": 1, "name": "Post"}})
        shim.create_post(entity_id=555, name="Post", entry="body")
        client._request.assert_called_once_with(
            "POST",
            "entities/555/posts",
            json={"name": "Post", "entry": "body", "visibility_id": 1},
        )

    def test_delete_post_uses_entities_endpoint(self):
        shim, client = self._make_shim({})
        shim.delete_post(entity_id=555, post_id=99)
        client._request.assert_called_once_with(
            "DELETE", "entities/555/posts/99"
        )


class TestServiceGetManager:
    """KankaService._get_manager routes to the right implementation."""

    @patch("os.getenv")
    def setup_method(self, method, mock_getenv):
        mock_getenv.side_effect = lambda key: {
            "KANKA_TOKEN": "test",
            "KANKA_CAMPAIGN_ID": "1",
        }.get(key)
        with patch("mcp_kanka.service.KankaClient"):
            self.service = KankaService()

    def test_returns_shim_for_http_backed_types(self):
        for et in HTTP_BACKED_TYPES:
            mgr = self.service._get_manager(et)
            assert isinstance(mgr, _HttpEntityShim), (
                f"{et} should route through the shim"
            )

    def test_returns_client_attr_for_manager_backed_types(self):
        # For a manager-backed type, _get_manager returns the client's manager
        # attribute (real python-kanka managers). We only verify the code path
        # returns *something* since the client is mocked; the important thing
        # is it doesn't hit the shim branch.
        for et in MANAGER_BACKED_TYPES:
            mgr = self.service._get_manager(et)
            assert not isinstance(mgr, _HttpEntityShim), (
                f"{et} should NOT route through the shim"
            )

    def test_shim_is_cached_per_type(self):
        # Same type twice should return the same shim (has_next_page state
        # would be wrong otherwise).
        first = self.service._get_manager("ability")
        second = self.service._get_manager("ability")
        assert first is second

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown entity type"):
            self.service._get_manager("gnome_king")


class TestEntityToDictOnFacade:
    """_entity_to_dict handles facade-wrapped HTTP entities."""

    @patch("os.getenv")
    def setup_method(self, method, mock_getenv):
        mock_getenv.side_effect = lambda key: {
            "KANKA_TOKEN": "test",
            "KANKA_CAMPAIGN_ID": "1",
        }.get(key)
        with patch("mcp_kanka.service.KankaClient"):
            self.service = KankaService()

    def test_converts_http_backed_ability_to_our_dict_shape(self):
        raw = {
            "id": 42,
            "entity_id": 987,
            "name": "Cleave",
            "type": "Combat",
            "entry": "<p>Whirlwind attack.</p>",
            "is_private": False,
            "tags": [],
            "created_at": "2026-01-01T00:00:00.000000Z",
            "updated_at": "2026-01-02T00:00:00.000000Z",
        }
        facade = _HttpEntityFacade(raw)
        result = self.service._entity_to_dict(facade, "ability")
        assert result["id"] == 42
        assert result["entity_id"] == 987
        assert result["name"] == "Cleave"
        assert result["entity_type"] == "ability"
        assert result["type"] == "Combat"
        assert result["is_hidden"] is False
        assert result["created_at"].startswith("2026-01-01")
        assert result["updated_at"].startswith("2026-01-02")
        # Image fields are populated with None when absent.
        assert result["image_uuid"] is None
        assert result["header_uuid"] is None

    def test_facade_missing_entry_returns_none(self):
        facade = _HttpEntityFacade(
            {
                "id": 1,
                "entity_id": 2,
                "name": "Empty",
                "tags": [],
            }
        )
        result = self.service._entity_to_dict(facade, "item")
        assert result["entry"] is None
        assert result["entity_type"] == "item"
