"""MCP tool implementations for Kanka operations."""

import logging
from typing import Any

from .operations import get_operations
from .types import (
    CheckEntityUpdatesResult,
    CreateAttributeResult,
    CreateCalendarWeatherResult,
    CreateEntityAbilityResult,
    CreateEntityResult,
    CreateInventoryResult,
    CreateOrganisationMemberResult,
    CreatePostResult,
    CreateQuestElementResult,
    CreateRelationResult,
    CreateTimelineElementResult,
    CreateTimelineEraResult,
    DeleteAttributeResult,
    DeleteCalendarWeatherResult,
    DeleteEntityAbilityResult,
    DeleteEntityResult,
    DeleteInventoryResult,
    DeleteOrganisationMemberResult,
    DeletePostResult,
    DeleteQuestElementResult,
    DeleteRelationResult,
    DeleteTimelineElementResult,
    DeleteTimelineEraResult,
    GetEntityResult,
    ListAttributesResult,
    ListCalendarWeatherResult,
    ListEntityAbilitiesResult,
    ListInventoryResult,
    ListOrganisationMembersResult,
    ListQuestElementsResult,
    ListRelationsResult,
    ListTimelineElementsResult,
    ListTimelineErasResult,
    UpdateAttributeResult,
    UpdateCalendarWeatherResult,
    UpdateEntityAbilityResult,
    UpdateEntityResult,
    UpdateInventoryResult,
    UpdateOrganisationMemberResult,
    UpdatePostResult,
    UpdateQuestElementResult,
    UpdateRelationResult,
    UpdateTimelineElementResult,
    UpdateTimelineEraResult,
)

logger = logging.getLogger(__name__)


async def handle_find_entities(**params: Any) -> dict[str, Any]:
    """
    Find entities by search and/or filtering.

    Args:
        **params: Parameters from FindEntitiesParams

    Returns:
        Dictionary with entities and sync_info
    """
    operations = get_operations()

    # Delegate to operations layer
    return await operations.find_entities(
        query=params.get("query"),
        entity_type=params.get("entity_type"),
        name=params.get("name"),
        name_exact=params.get("name_exact", False),
        name_fuzzy=params.get("name_fuzzy", False),
        type=params.get("type"),
        tags=params.get("tags", []),
        date_range=params.get("date_range"),
        include_full=params.get("include_full", True),
        page=params.get("page", 1),
        limit=params.get("limit", 25),
        last_synced=params.get("last_synced"),
    )


async def handle_create_entities(**params: Any) -> list[CreateEntityResult]:
    """
    Create one or more entities.

    Args:
        **params: Parameters from CreateEntitiesParams

    Returns:
        List of creation results
    """
    entities = params.get("entities", [])
    operations = get_operations()

    # Delegate to operations layer
    return await operations.create_entities(entities)


async def handle_update_entities(**params: Any) -> list[UpdateEntityResult]:
    """
    Update one or more entities.

    Args:
        **params: Parameters from UpdateEntitiesParams

    Returns:
        List of update results
    """
    updates = params.get("updates", [])
    operations = get_operations()

    # Delegate to operations layer
    return await operations.update_entities(updates)


async def handle_get_entities(**params: Any) -> list[GetEntityResult]:
    """
    Retrieve specific entities by ID.

    Args:
        **params: Parameters from GetEntitiesParams

    Returns:
        List of entity results
    """
    entity_ids = params.get("entity_ids", [])
    include_posts = params.get("include_posts", False)
    operations = get_operations()

    # Delegate to operations layer
    return await operations.get_entities(entity_ids, include_posts)


async def handle_delete_entities(**params: Any) -> list[DeleteEntityResult]:
    """
    Delete one or more entities.

    Args:
        **params: Parameters from DeleteEntitiesParams

    Returns:
        List of deletion results
    """
    entity_ids = params.get("entity_ids", [])
    operations = get_operations()

    # Delegate to operations layer
    return await operations.delete_entities(entity_ids)


async def handle_create_posts(**params: Any) -> list[CreatePostResult]:
    """
    Create posts on entities.

    Args:
        **params: Parameters from CreatePostsParams

    Returns:
        List of creation results
    """
    posts = params.get("posts", [])
    operations = get_operations()

    # Delegate to operations layer
    return await operations.create_posts(posts)


async def handle_update_posts(**params: Any) -> list[UpdatePostResult]:
    """
    Update existing posts.

    Args:
        **params: Parameters from UpdatePostsParams

    Returns:
        List of update results
    """
    updates = params.get("updates", [])
    operations = get_operations()

    # Delegate to operations layer
    return await operations.update_posts(updates)


async def handle_delete_posts(**params: Any) -> list[DeletePostResult]:
    """
    Delete posts from entities.

    Args:
        **params: Parameters from DeletePostsParams

    Returns:
        List of deletion results
    """
    deletions = params.get("deletions", [])
    operations = get_operations()

    # Delegate to operations layer
    return await operations.delete_posts(deletions)


async def handle_check_entity_updates(**params: Any) -> CheckEntityUpdatesResult:
    """
    Check which entity_ids have been modified since last sync.

    Args:
        **params: Parameters from CheckEntityUpdatesParams

    Returns:
        Check result with modified and deleted entity IDs
    """
    entity_ids = params.get("entity_ids", [])
    last_synced = params.get("last_synced")

    # Validate last_synced is provided
    if not last_synced:
        raise ValueError("last_synced parameter is required")

    operations = get_operations()

    # Delegate to operations layer
    return await operations.check_entity_updates(entity_ids, last_synced)


# =============================================================================
# Attributes (Phase C)
# =============================================================================


async def handle_list_attributes(**params: Any) -> ListAttributesResult:
    """List all attributes on an entity."""
    entity_id = params.get("entity_id")
    if not entity_id:
        raise ValueError("entity_id parameter is required")
    operations = get_operations()
    return await operations.list_attributes(entity_id)


async def handle_create_attributes(**params: Any) -> list[CreateAttributeResult]:
    """Create one or more attributes on entities."""
    attributes = params.get("attributes", [])
    operations = get_operations()
    return await operations.create_attributes(attributes)


async def handle_update_attributes(**params: Any) -> list[UpdateAttributeResult]:
    """Update existing attributes."""
    updates = params.get("updates", [])
    operations = get_operations()
    return await operations.update_attributes(updates)


async def handle_delete_attributes(**params: Any) -> list[DeleteAttributeResult]:
    """Delete attributes from entities."""
    deletions = params.get("deletions", [])
    operations = get_operations()
    return await operations.delete_attributes(deletions)


# =============================================================================
# Relations (Phase D)
# =============================================================================


async def handle_list_relations(**params: Any) -> ListRelationsResult:
    """List all relations owned by an entity."""
    entity_id = params.get("entity_id")
    if not entity_id:
        raise ValueError("entity_id parameter is required")
    operations = get_operations()
    return await operations.list_relations(entity_id)


async def handle_create_relations(**params: Any) -> list[CreateRelationResult]:
    """Create one or more relations between entities."""
    relations = params.get("relations", [])
    operations = get_operations()
    return await operations.create_relations(relations)


async def handle_update_relations(**params: Any) -> list[UpdateRelationResult]:
    """Update existing relations."""
    updates = params.get("updates", [])
    operations = get_operations()
    return await operations.update_relations(updates)


async def handle_delete_relations(**params: Any) -> list[DeleteRelationResult]:
    """Delete relations from entities."""
    deletions = params.get("deletions", [])
    operations = get_operations()
    return await operations.delete_relations(deletions)


# =============================================================================
# Phase E: entity_abilities
# =============================================================================


async def handle_list_entity_abilities(**params: Any) -> ListEntityAbilitiesResult:
    entity_id = params.get("entity_id")
    if not entity_id:
        raise ValueError("entity_id parameter is required")
    return await get_operations().list_entity_abilities(entity_id)


async def handle_create_entity_abilities(
    **params: Any,
) -> list[CreateEntityAbilityResult]:
    return await get_operations().create_entity_abilities(params.get("items", []))


async def handle_update_entity_abilities(
    **params: Any,
) -> list[UpdateEntityAbilityResult]:
    return await get_operations().update_entity_abilities(
        params.get("updates", [])
    )


async def handle_delete_entity_abilities(
    **params: Any,
) -> list[DeleteEntityAbilityResult]:
    return await get_operations().delete_entity_abilities(
        params.get("deletions", [])
    )


# =============================================================================
# Phase E: inventory
# =============================================================================


async def handle_list_inventory(**params: Any) -> ListInventoryResult:
    entity_id = params.get("entity_id")
    if not entity_id:
        raise ValueError("entity_id parameter is required")
    return await get_operations().list_inventory(entity_id)


async def handle_create_inventory(**params: Any) -> list[CreateInventoryResult]:
    return await get_operations().create_inventory(params.get("items", []))


async def handle_update_inventory(**params: Any) -> list[UpdateInventoryResult]:
    return await get_operations().update_inventory(params.get("updates", []))


async def handle_delete_inventory(**params: Any) -> list[DeleteInventoryResult]:
    return await get_operations().delete_inventory(params.get("deletions", []))


# =============================================================================
# Phase E: organisation_members
# =============================================================================


async def handle_list_organisation_members(
    **params: Any,
) -> ListOrganisationMembersResult:
    org_id = params.get("organisation_id")
    if not org_id:
        raise ValueError("organisation_id parameter is required")
    return await get_operations().list_organisation_members(org_id)


async def handle_create_organisation_members(
    **params: Any,
) -> list[CreateOrganisationMemberResult]:
    return await get_operations().create_organisation_members(
        params.get("items", [])
    )


async def handle_update_organisation_members(
    **params: Any,
) -> list[UpdateOrganisationMemberResult]:
    return await get_operations().update_organisation_members(
        params.get("updates", [])
    )


async def handle_delete_organisation_members(
    **params: Any,
) -> list[DeleteOrganisationMemberResult]:
    return await get_operations().delete_organisation_members(
        params.get("deletions", [])
    )


# =============================================================================
# Phase E: quest_elements
# =============================================================================


async def handle_list_quest_elements(**params: Any) -> ListQuestElementsResult:
    quest_id = params.get("quest_id")
    if not quest_id:
        raise ValueError("quest_id parameter is required")
    return await get_operations().list_quest_elements(quest_id)


async def handle_create_quest_elements(
    **params: Any,
) -> list[CreateQuestElementResult]:
    return await get_operations().create_quest_elements(params.get("items", []))


async def handle_update_quest_elements(
    **params: Any,
) -> list[UpdateQuestElementResult]:
    return await get_operations().update_quest_elements(
        params.get("updates", [])
    )


async def handle_delete_quest_elements(
    **params: Any,
) -> list[DeleteQuestElementResult]:
    return await get_operations().delete_quest_elements(
        params.get("deletions", [])
    )


# =============================================================================
# Phase F: calendar_weather
# =============================================================================


async def handle_list_calendar_weather(**params: Any) -> ListCalendarWeatherResult:
    cal_id = params.get("calendar_id")
    if not cal_id:
        raise ValueError("calendar_id parameter is required")
    return await get_operations().list_calendar_weather(cal_id)


async def handle_create_calendar_weather(
    **params: Any,
) -> list[CreateCalendarWeatherResult]:
    return await get_operations().create_calendar_weather(
        params.get("items", [])
    )


async def handle_update_calendar_weather(
    **params: Any,
) -> list[UpdateCalendarWeatherResult]:
    return await get_operations().update_calendar_weather(
        params.get("updates", [])
    )


async def handle_delete_calendar_weather(
    **params: Any,
) -> list[DeleteCalendarWeatherResult]:
    return await get_operations().delete_calendar_weather(
        params.get("deletions", [])
    )


# =============================================================================
# Phase F: timeline_eras
# =============================================================================


async def handle_list_timeline_eras(**params: Any) -> ListTimelineErasResult:
    tl_id = params.get("timeline_id")
    if not tl_id:
        raise ValueError("timeline_id parameter is required")
    return await get_operations().list_timeline_eras(tl_id)


async def handle_create_timeline_eras(
    **params: Any,
) -> list[CreateTimelineEraResult]:
    return await get_operations().create_timeline_eras(params.get("items", []))


async def handle_update_timeline_eras(
    **params: Any,
) -> list[UpdateTimelineEraResult]:
    return await get_operations().update_timeline_eras(params.get("updates", []))


async def handle_delete_timeline_eras(
    **params: Any,
) -> list[DeleteTimelineEraResult]:
    return await get_operations().delete_timeline_eras(
        params.get("deletions", [])
    )


# =============================================================================
# Phase F: timeline_elements
# =============================================================================


async def handle_list_timeline_elements(
    **params: Any,
) -> ListTimelineElementsResult:
    tl_id = params.get("timeline_id")
    if not tl_id:
        raise ValueError("timeline_id parameter is required")
    return await get_operations().list_timeline_elements(tl_id)


async def handle_create_timeline_elements(
    **params: Any,
) -> list[CreateTimelineElementResult]:
    return await get_operations().create_timeline_elements(
        params.get("items", [])
    )


async def handle_update_timeline_elements(
    **params: Any,
) -> list[UpdateTimelineElementResult]:
    return await get_operations().update_timeline_elements(
        params.get("updates", [])
    )


async def handle_delete_timeline_elements(
    **params: Any,
) -> list[DeleteTimelineElementResult]:
    return await get_operations().delete_timeline_elements(
        params.get("deletions", [])
    )
