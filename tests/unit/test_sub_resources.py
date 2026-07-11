"""Unit tests for Phase E character sub-resources.

Covers entity_abilities, inventory, organisation_members, and quest_elements
across the service and operations layers.
"""

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


# =============================================================================
# entity_abilities
# =============================================================================


class TestEntityAbilitiesService:
    def test_list_hits_correct_endpoint(self):
        svc = _svc({"data": [{"id": 1, "ability_id": 100, "charges": 3}]})
        result = svc.list_entity_abilities(42)
        svc.client._request.assert_called_once_with(
            "GET", "entities/42/entity_abilities"
        )
        assert result[0]["ability_id"] == 100
        assert result[0]["charges"] == 3

    def test_create_sends_abilities_array(self):
        # Kanka's POST accepts ``abilities: [id]`` — the service standardizes
        # on one row per call.
        svc = _svc({"data": {"id": 7, "ability_id": 100, "charges": 3}})
        result = svc.create_entity_ability(
            entity_id=42, ability_id=100, charges=3, note="hi"
        )
        method, url = svc.client._request.call_args.args
        payload = svc.client._request.call_args.kwargs["json"]
        assert method == "POST"
        assert url == "entities/42/entity_abilities"
        assert payload == {"abilities": [100], "charges": 3, "note": "hi"}
        assert result["id"] == 7

    def test_create_handles_list_response(self):
        # Some responses return data as a list; we take the last item.
        svc = _svc({"data": [{"id": 1}, {"id": 99}]})
        result = svc.create_entity_ability(entity_id=42, ability_id=100)
        assert result["id"] == 99

    def test_create_visibility_translation(self):
        svc = _svc({"data": {"id": 1}})
        svc.create_entity_ability(entity_id=42, ability_id=100, is_hidden=True)
        payload = svc.client._request.call_args.kwargs["json"]
        assert payload["visibility_id"] == 2

    def test_update_partial_fetches_current_ability_id(self):
        # PATCH requires ``abilities`` in payload. When the caller omits
        # ability_id, we fetch the row and reuse its current ability_id.
        svc = _svc({"data": []})  # will be replaced per-call
        svc.client._request.side_effect = [
            # First call: list rows (from update's fetch)
            {"data": [{"id": 55, "ability_id": 200, "charges": 3}]},
            # Second call: the PATCH itself
            {"data": {"id": 55, "ability_id": 200, "charges": 9}},
        ]
        result = svc.update_entity_ability(
            entity_id=42, entity_ability_id=55, charges=9
        )
        # PATCH payload should include abilities=[200] from the fetched row.
        _method, url = svc.client._request.call_args.args
        payload = svc.client._request.call_args.kwargs["json"]
        assert url == "entities/42/entity_abilities/55"
        assert payload["abilities"] == [200]
        assert payload["charges"] == 9
        assert result["ability_id"] == 200

    def test_update_raises_when_row_not_found(self):
        svc = _svc({"data": []})
        with pytest.raises(ValueError, match="not found"):
            svc.update_entity_ability(
                entity_id=42, entity_ability_id=999, charges=1
            )

    def test_delete_uses_delete(self):
        svc = _svc({})
        assert svc.delete_entity_ability(42, 55) is True
        svc.client._request.assert_called_once_with(
            "DELETE", "entities/42/entity_abilities/55"
        )


# =============================================================================
# inventory
# =============================================================================


class TestInventoryService:
    def test_list_endpoint(self):
        svc = _svc({"data": [{"id": 1, "amount": 2, "item_id": 10}]})
        result = svc.list_inventory(42)
        svc.client._request.assert_called_once_with("GET", "entities/42/inventory")
        assert result[0]["item_id"] == 10

    def test_create_requires_item_id_or_name(self):
        svc = _svc({})
        with pytest.raises(ValueError, match="item_id or name"):
            svc.create_inventory(entity_id=42)

    def test_create_puts_entity_id_in_body(self):
        # Kanka needs entity_id BOTH in URL and body.
        svc = _svc({"data": {"id": 7, "item_id": 100}})
        svc.create_inventory(entity_id=42, item_id=100, amount=3)
        payload = svc.client._request.call_args.kwargs["json"]
        assert payload["entity_id"] == 42
        assert payload["item_id"] == 100

    def test_update_partial_fetches_current_item_id(self):
        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            side_effect=[
                # list current
                {
                    "data": [
                        {"id": 55, "item_id": 100, "name": None, "amount": 2}
                    ]
                },
                # patch
                {"data": {"id": 55, "item_id": 100, "is_equipped": True}},
            ]
        )
        svc.update_inventory(entity_id=42, inventory_id=55, is_equipped=True)
        payload = svc.client._request.call_args.kwargs["json"]
        assert payload["item_id"] == 100
        assert payload["is_equipped"] is True

    def test_update_partial_falls_back_to_name_when_no_item(self):
        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            side_effect=[
                {"data": [{"id": 55, "item_id": None, "name": "Rope"}]},
                {"data": {"id": 55}},
            ]
        )
        svc.update_inventory(entity_id=42, inventory_id=55, amount=99)
        payload = svc.client._request.call_args.kwargs["json"]
        assert payload["name"] == "Rope"
        assert "item_id" not in payload

    def test_delete(self):
        svc = _svc({})
        assert svc.delete_inventory(42, 55) is True
        svc.client._request.assert_called_once_with(
            "DELETE", "entities/42/inventory/55"
        )


# =============================================================================
# organisation_members
# =============================================================================


class TestOrganisationMembersService:
    def test_list_endpoint(self):
        svc = _svc({"data": [{"id": 1, "organisation_id": 10, "character_id": 20}]})
        result = svc.list_organisation_members(10)
        svc.client._request.assert_called_once_with(
            "GET", "organisations/10/organisation_members"
        )
        assert result[0]["organisation_id"] == 10

    def test_create_requires_ids_in_body_and_url(self):
        svc = _svc({"data": {"id": 7, "organisation_id": 10, "character_id": 20}})
        svc.create_organisation_member(
            organisation_id=10, character_id=20, role="Leader"
        )
        method, url = svc.client._request.call_args.args
        payload = svc.client._request.call_args.kwargs["json"]
        assert method == "POST"
        assert url == "organisations/10/organisation_members"
        assert payload["organisation_id"] == 10
        assert payload["character_id"] == 20
        assert payload["role"] == "Leader"

    def test_is_hidden_translates_to_is_private(self):
        svc = _svc({"data": {"id": 7}})
        svc.create_organisation_member(
            organisation_id=10, character_id=20, is_hidden=True
        )
        payload = svc.client._request.call_args.kwargs["json"]
        assert payload["is_private"] is True

    def test_update_hits_row_endpoint(self):
        svc = _svc({"data": {"id": 55, "role": "Elder"}})
        svc.update_organisation_member(
            organisation_id=10, member_id=55, role="Elder"
        )
        method, url = svc.client._request.call_args.args
        assert method == "PATCH"
        assert url == "organisations/10/organisation_members/55"


# =============================================================================
# quest_elements
# =============================================================================


class TestQuestElementsService:
    def test_list_endpoint(self):
        svc = _svc({"data": [{"id": 1, "entity_id": 42, "role": "Hero"}]})
        result = svc.list_quest_elements(quest_id=100)
        svc.client._request.assert_called_once_with(
            "GET", "quests/100/quest_elements"
        )
        assert result[0]["role"] == "Hero"

    def test_create_requires_entity_or_name(self):
        svc = _svc({})
        with pytest.raises(ValueError, match="entity_id or name"):
            svc.create_quest_element(quest_id=100)

    def test_create_converts_entry_markdown_to_html(self):
        svc = _svc({"data": {"id": 7}})
        svc.create_quest_element(quest_id=100, entity_id=42, entry="**bold**")
        payload = svc.client._request.call_args.kwargs["json"]
        # ContentConverter output should be HTML-ish.
        assert "<" in payload["entry"]

    def test_update_partial_fetches_current_entity_id(self):
        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            side_effect=[
                {"data": [{"id": 55, "entity_id": 42, "name": None}]},
                {"data": {"id": 55, "entity_id": 42, "role": "Antihero"}},
            ]
        )
        svc.update_quest_element(quest_id=100, element_id=55, role="Antihero")
        payload = svc.client._request.call_args.kwargs["json"]
        assert payload["entity_id"] == 42
        assert payload["role"] == "Antihero"

    def test_delete(self):
        svc = _svc({})
        assert svc.delete_quest_element(100, 55) is True
        svc.client._request.assert_called_once_with(
            "DELETE", "quests/100/quest_elements/55"
        )


# =============================================================================
# Operations layer batch behavior
# =============================================================================


class TestBatchSubResources:
    @pytest.mark.asyncio
    async def test_create_entity_abilities_reports_per_item_failure(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            side_effect=[
                {"data": {"id": 1, "ability_id": 100}},
                Exception("bad ability"),
            ]
        )
        ops = KankaOperations(service=svc)
        result = await ops.create_entity_abilities(
            [
                {"entity_id": 42, "ability_id": 100},
                {"entity_id": 42, "ability_id": 999},
                {"entity_id": 42},  # missing ability_id
            ]
        )
        assert [r["success"] for r in result] == [True, False, False]
        assert result[0]["entity_ability_id"] == 1

    @pytest.mark.asyncio
    async def test_create_inventory_validation_rejects_missing_ident(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock()
        ops = KankaOperations(service=svc)
        result = await ops.create_inventory(
            [
                {"entity_id": 42},  # missing both item_id and name
            ]
        )
        assert result[0]["success"] is False
        # Malformed items never hit HTTP.
        svc.client._request.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_organisation_members_batch(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            side_effect=[
                {"data": {"id": 7, "organisation_id": 10, "character_id": 20}},
                Exception("dupe"),
            ]
        )
        ops = KankaOperations(service=svc)
        result = await ops.create_organisation_members(
            [
                {"organisation_id": 10, "character_id": 20},
                {"organisation_id": 10, "character_id": 30},
                {"character_id": 40},  # missing org
            ]
        )
        assert [r["success"] for r in result] == [True, False, False]

    @pytest.mark.asyncio
    async def test_delete_quest_elements_batch(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(side_effect=[{}, Exception("gone")])
        ops = KankaOperations(service=svc)
        result = await ops.delete_quest_elements(
            [
                {"quest_id": 100, "element_id": 55},
                {"quest_id": 100, "element_id": 56},
            ]
        )
        assert result[0]["success"] is True
        assert result[1]["success"] is False


# =============================================================================
# Character title + races field extensions on update_entities
# =============================================================================


class TestCharacterFieldExtensions:
    """Non-character types should NOT get title/race_ids in the payload."""

    def test_title_only_on_character(self):
        svc = _make_service()
        svc.client = MagicMock()
        # Mock get_entity_by_id to return a non-character type.
        svc.get_entity_by_id = MagicMock(
            return_value={"id": 100, "entity_type": "location"}
        )
        mock_manager = MagicMock()
        svc._get_manager = MagicMock(return_value=mock_manager)

        svc.update_entity(
            entity_id=999, name="Test", title="Ignored on location"
        )
        kwargs = mock_manager.update.call_args.kwargs
        # Non-character type: title must not be forwarded.
        assert "title" not in kwargs

    def test_title_forwarded_for_character(self):
        svc = _make_service()
        svc.client = MagicMock()
        svc.get_entity_by_id = MagicMock(
            return_value={"id": 100, "entity_type": "character"}
        )
        mock_manager = MagicMock()
        svc._get_manager = MagicMock(return_value=mock_manager)

        svc.update_entity(entity_id=999, name="Test", title="The Wise")
        kwargs = mock_manager.update.call_args.kwargs
        assert kwargs["title"] == "The Wise"

    def test_race_ids_forwarded_for_character(self):
        svc = _make_service()
        svc.client = MagicMock()
        svc.get_entity_by_id = MagicMock(
            return_value={"id": 100, "entity_type": "character"}
        )
        mock_manager = MagicMock()
        svc._get_manager = MagicMock(return_value=mock_manager)

        svc.update_entity(entity_id=999, name="Test", race_ids=[123, 456])
        kwargs = mock_manager.update.call_args.kwargs
        assert kwargs["races"] == [123, 456]

    def test_race_ids_ignored_on_non_character(self):
        svc = _make_service()
        svc.client = MagicMock()
        svc.get_entity_by_id = MagicMock(
            return_value={"id": 100, "entity_type": "location"}
        )
        mock_manager = MagicMock()
        svc._get_manager = MagicMock(return_value=mock_manager)

        svc.update_entity(entity_id=999, name="Test", race_ids=[123])
        kwargs = mock_manager.update.call_args.kwargs
        assert "races" not in kwargs
