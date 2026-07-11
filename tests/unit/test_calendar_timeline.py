"""Unit tests for Phase F calendar and timeline sub-resources."""

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
# Calendar current-date field on update_entities
# =============================================================================


class TestCalendarDateField:
    def test_date_forwarded_for_calendar(self):
        svc = _make_service()
        svc.client = MagicMock()
        svc.get_entity_by_id = MagicMock(
            return_value={"id": 100, "entity_type": "calendar"}
        )
        mock_manager = MagicMock()
        svc._get_manager = MagicMock(return_value=mock_manager)
        svc.update_entity(entity_id=999, name="Test", date="741-6-1")
        kwargs = mock_manager.update.call_args.kwargs
        assert kwargs["date"] == "741-6-1"

    def test_date_ignored_on_non_calendar(self):
        svc = _make_service()
        svc.client = MagicMock()
        svc.get_entity_by_id = MagicMock(
            return_value={"id": 100, "entity_type": "character"}
        )
        mock_manager = MagicMock()
        svc._get_manager = MagicMock(return_value=mock_manager)
        svc.update_entity(entity_id=999, name="Test", date="741-6-1")
        kwargs = mock_manager.update.call_args.kwargs
        assert "date" not in kwargs


# =============================================================================
# Calendar weather
# =============================================================================


class TestCalendarWeatherService:
    def test_list_endpoint(self):
        svc = _svc({"data": [{"id": 1, "day": 1, "month": 1, "year": 100, "weather": "Rain"}]})
        result = svc.list_calendar_weather(33979)
        svc.client._request.assert_called_once_with(
            "GET", "calendars/33979/calendar_weather"
        )
        assert result[0]["weather"] == "Rain"

    def test_create_sends_required_fields(self):
        svc = _svc({"data": {"id": 7, "day": 1, "month": 6, "year": 741, "weather": "Snow"}})
        svc.create_calendar_weather(
            calendar_id=33979, day=1, month=6, year=741, weather="Snow"
        )
        method, url = svc.client._request.call_args.args
        payload = svc.client._request.call_args.kwargs["json"]
        assert method == "POST"
        assert url == "calendars/33979/calendar_weather"
        assert payload == {
            "day": 1,
            "month": 6,
            "year": 741,
            "weather": "Snow",
        }

    def test_visibility_translation(self):
        svc = _svc({"data": {"id": 7}})
        svc.create_calendar_weather(
            calendar_id=33979, day=1, month=1, year=1, is_hidden=True
        )
        payload = svc.client._request.call_args.kwargs["json"]
        assert payload["visibility_id"] == 2

    def test_update_partial_fetches_current(self):
        # PATCH needs day/month/year/weather; auto-fetch fills them.
        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            side_effect=[
                {"data": [{"id": 55, "day": 1, "month": 6, "year": 741, "weather": "Rain"}]},
                {"data": {"id": 55, "temperature": "Cold"}},
            ]
        )
        svc.update_calendar_weather(
            calendar_id=33979, weather_id=55, temperature="Cold"
        )
        payload = svc.client._request.call_args.kwargs["json"]
        assert payload["day"] == 1
        assert payload["month"] == 6
        assert payload["year"] == 741
        assert payload["weather"] == "Rain"
        assert payload["temperature"] == "Cold"

    def test_update_raises_when_row_not_found(self):
        svc = _svc({"data": []})
        with pytest.raises(ValueError, match="not found"):
            svc.update_calendar_weather(
                calendar_id=33979, weather_id=999, temperature="Cold"
            )

    def test_delete(self):
        svc = _svc({})
        assert svc.delete_calendar_weather(33979, 55) is True
        svc.client._request.assert_called_once_with(
            "DELETE", "calendars/33979/calendar_weather/55"
        )


# =============================================================================
# Timeline eras
# =============================================================================


class TestTimelineErasService:
    def test_list_endpoint(self):
        svc = _svc({"data": [{"id": 1, "name": "First Age", "start_year": 0}]})
        result = svc.list_timeline_eras(100)
        svc.client._request.assert_called_once_with(
            "GET", "timelines/100/timeline_eras"
        )
        assert result[0]["name"] == "First Age"

    def test_create_sends_fields(self):
        svc = _svc({"data": {"id": 7, "name": "FA"}})
        svc.create_timeline_era(
            timeline_id=100,
            name="First Age",
            abbreviation="FA",
            start_year=0,
            end_year=100,
        )
        payload = svc.client._request.call_args.kwargs["json"]
        assert payload["name"] == "First Age"
        assert payload["abbreviation"] == "FA"
        assert payload["start_year"] == 0
        assert payload["end_year"] == 100

    def test_create_converts_entry_markdown(self):
        svc = _svc({"data": {"id": 7}})
        svc.create_timeline_era(
            timeline_id=100, name="FA", entry="**bold**"
        )
        payload = svc.client._request.call_args.kwargs["json"]
        assert "<" in payload["entry"]

    def test_update_partial_fetches_name(self):
        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            side_effect=[
                {"data": [{"id": 55, "name": "First Age"}]},
                {"data": {"id": 55, "end_year": 200}},
            ]
        )
        svc.update_timeline_era(timeline_id=100, era_id=55, end_year=200)
        payload = svc.client._request.call_args.kwargs["json"]
        assert payload["name"] == "First Age"
        assert payload["end_year"] == 200

    def test_delete(self):
        svc = _svc({})
        assert svc.delete_timeline_era(100, 55) is True
        svc.client._request.assert_called_once_with(
            "DELETE", "timelines/100/timeline_eras/55"
        )


# =============================================================================
# Timeline elements
# =============================================================================


class TestTimelineElementsService:
    def test_list_endpoint(self):
        svc = _svc({"data": [{"id": 1, "name": "Founding", "era_id": 42}]})
        result = svc.list_timeline_elements(100)
        svc.client._request.assert_called_once_with(
            "GET", "timelines/100/timeline_elements"
        )
        assert result[0]["name"] == "Founding"

    def test_create_requires_entity_or_name(self):
        svc = _svc({})
        with pytest.raises(ValueError, match="entity_id or name"):
            svc.create_timeline_element(timeline_id=100, era_id=42)

    def test_create_sends_era_id(self):
        svc = _svc({"data": {"id": 7, "era_id": 42}})
        svc.create_timeline_element(
            timeline_id=100,
            era_id=42,
            name="The Founding",
            date="Year 1",
        )
        payload = svc.client._request.call_args.kwargs["json"]
        assert payload["era_id"] == 42
        assert payload["name"] == "The Founding"
        assert payload["date"] == "Year 1"

    def test_visibility_translation(self):
        svc = _svc({"data": {"id": 7}})
        svc.create_timeline_element(
            timeline_id=100, era_id=42, name="X", is_hidden=True
        )
        payload = svc.client._request.call_args.kwargs["json"]
        assert payload["visibility_id"] == 2

    def test_update_partial_fetches_era_and_identity(self):
        # Neither era_id nor name/entity_id supplied — auto-fetch both.
        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            side_effect=[
                {
                    "data": [
                        {
                            "id": 55,
                            "era_id": 42,
                            "name": "The Founding",
                            "entity_id": None,
                        }
                    ]
                },
                {"data": {"id": 55, "date": "Year 2"}},
            ]
        )
        svc.update_timeline_element(
            timeline_id=100, element_id=55, date="Year 2"
        )
        payload = svc.client._request.call_args.kwargs["json"]
        assert payload["era_id"] == 42
        assert payload["name"] == "The Founding"
        assert payload["date"] == "Year 2"

    def test_update_partial_prefers_entity_id_when_present(self):
        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            side_effect=[
                {
                    "data": [
                        {"id": 55, "era_id": 42, "entity_id": 9999, "name": None}
                    ]
                },
                {"data": {"id": 55}},
            ]
        )
        svc.update_timeline_element(
            timeline_id=100, element_id=55, colour="#ff0000"
        )
        payload = svc.client._request.call_args.kwargs["json"]
        assert payload["entity_id"] == 9999
        assert "name" not in payload

    def test_delete(self):
        svc = _svc({})
        assert svc.delete_timeline_element(100, 55) is True
        svc.client._request.assert_called_once_with(
            "DELETE", "timelines/100/timeline_elements/55"
        )


# =============================================================================
# Batch operations
# =============================================================================


class TestBatchCalendarTimeline:
    @pytest.mark.asyncio
    async def test_create_calendar_weather_batch(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            side_effect=[
                {"data": {"id": 1, "day": 1, "month": 1, "year": 100, "weather": "R"}},
                Exception("bad"),
            ]
        )
        ops = KankaOperations(service=svc)
        result = await ops.create_calendar_weather(
            [
                {"calendar_id": 33979, "day": 1, "month": 1, "year": 100, "weather": "R"},
                {"calendar_id": 33979, "day": 2, "month": 1, "year": 100, "weather": "S"},
                {"calendar_id": 33979},  # missing day/month/year
            ]
        )
        assert [r["success"] for r in result] == [True, False, False]

    @pytest.mark.asyncio
    async def test_create_timeline_eras_batch(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(
            side_effect=[{"data": {"id": 7, "name": "FA"}}, Exception("bad")]
        )
        ops = KankaOperations(service=svc)
        result = await ops.create_timeline_eras(
            [
                {"timeline_id": 100, "name": "FA"},
                {"timeline_id": 100, "name": "SA"},
                {"timeline_id": 100},  # missing name
            ]
        )
        assert [r["success"] for r in result] == [True, False, False]

    @pytest.mark.asyncio
    async def test_create_timeline_elements_requires_era_id(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock()
        ops = KankaOperations(service=svc)
        result = await ops.create_timeline_elements(
            [
                {"timeline_id": 100, "name": "X"},  # missing era_id
                {"era_id": 42, "name": "Y"},  # missing timeline_id
                {"timeline_id": 100, "era_id": 42},  # missing identity
            ]
        )
        assert all(not r["success"] for r in result)
        svc.client._request.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_calendar_weather_batch(self):
        from mcp_kanka.operations import KankaOperations

        svc = _make_service()
        svc.client = MagicMock()
        svc.client._request = MagicMock(side_effect=[{}, Exception("gone")])
        ops = KankaOperations(service=svc)
        result = await ops.delete_calendar_weather(
            [
                {"calendar_id": 33979, "weather_id": 1},
                {"calendar_id": 33979, "weather_id": 2},
            ]
        )
        assert result[0]["success"] is True
        assert result[1]["success"] is False
