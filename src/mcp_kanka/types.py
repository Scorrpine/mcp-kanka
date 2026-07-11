"""Type definitions for the Kanka MCP server."""

from typing import Any, Literal, TypedDict

# Supported entity types.
#
# The upstream mcp-kanka (1.x) supported 8: character, creature, location,
# organization, race, note, journal, quest.
#
# This Scorrpine fork extends coverage with 7 more Kanka API entity types:
# calendar, event, family, item, ability, timeline, and tag (as a first-class
# entity, in addition to still being usable as a filter parameter on other
# entities).
EntityType = Literal[
    "ability",
    "calendar",
    "character",
    "creature",
    "event",
    "family",
    "item",
    "journal",
    "location",
    "note",
    "organization",
    "quest",
    "race",
    "tag",
    "timeline",
]

# Shared runtime constant for validation / schema generation.
# Kept in tuple form so it's ordered and hashable.
VALID_ENTITY_TYPES: tuple[str, ...] = (
    "ability",
    "calendar",
    "character",
    "creature",
    "event",
    "family",
    "item",
    "journal",
    "location",
    "note",
    "organization",
    "quest",
    "race",
    "tag",
    "timeline",
)

# Types where python-kanka has a Manager class we can use for CRUD.
#
# Note: `calendar` is intentionally *not* here even though python-kanka 2.6.2
# ships a Calendar manager. The upstream Calendar pydantic model declares
# ``parameters: str | None`` but the API returns a dict (e.g. ``{"layout": null}``),
# causing a validation error. We route calendars through raw HTTP instead until
# upstream fixes the model.
MANAGER_BACKED_TYPES: frozenset[str] = frozenset(
    {
        "character",
        "creature",
        "event",
        "family",
        "journal",
        "location",
        "note",
        "organization",  # maps to python-kanka's "organisations" manager
        "quest",
        "race",
        "tag",
    }
)

# Types where python-kanka does NOT have a working Manager class. For these we
# go through KankaClient._request(...) directly.
HTTP_BACKED_TYPES: frozenset[str] = frozenset(
    {"ability", "calendar", "item", "timeline"}
)

assert MANAGER_BACKED_TYPES.isdisjoint(HTTP_BACKED_TYPES), (
    "Entity type must be either manager-backed or HTTP-backed, not both"
)
assert set(VALID_ENTITY_TYPES) == MANAGER_BACKED_TYPES | HTTP_BACKED_TYPES, (
    "VALID_ENTITY_TYPES must equal the union of manager-backed and HTTP-backed sets"
)


# =============================================================================
# Attribute types (Phase C)
# =============================================================================

# User-facing attribute type names. The Kanka API stores these as a numeric
# ``type_id`` field but the string form is friendlier for AI callers. This fork
# translates one to the other transparently.
AttributeType = Literal[
    "standard",
    "number",
    "checkbox",
    "section",
    "random",
]

VALID_ATTRIBUTE_TYPES: tuple[str, ...] = (
    "standard",
    "number",
    "checkbox",
    "section",
    "random",
)

# Kanka's numeric ``type_id`` for each attribute type, verified against a live
# campaign on 2026-07-10.
ATTRIBUTE_TYPE_TO_ID: dict[str, int] = {
    "standard": 1,
    "number": 2,
    "checkbox": 3,
    "section": 4,
    "random": 5,
}
ATTRIBUTE_ID_TO_TYPE: dict[int, str] = {v: k for k, v in ATTRIBUTE_TYPE_TO_ID.items()}

assert set(VALID_ATTRIBUTE_TYPES) == set(ATTRIBUTE_TYPE_TO_ID.keys())


# Request types
class DateRange(TypedDict):
    """Date range for filtering."""

    start: str
    end: str


class FindEntitiesParams(TypedDict, total=False):
    """Parameters for find_entities tool."""

    query: str | None
    entity_type: EntityType | None
    name: str | None
    name_exact: bool | None
    name_fuzzy: bool | None
    type: str | None
    tags: list[str] | None
    date_range: DateRange | None
    include_full: bool | None
    page: int | None
    limit: int | None
    last_synced: str | None  # ISO 8601 timestamp


class EntityInput(TypedDict):
    """Input for creating an entity."""

    entity_type: EntityType
    name: str
    type: str | None
    entry: str | None
    tags: list[str] | None
    is_hidden: bool | None


class CreateEntitiesParams(TypedDict):
    """Parameters for create_entities tool."""

    entities: list[EntityInput]


class EntityUpdate(TypedDict):
    """Update for an entity."""

    entity_id: int
    name: str
    type: str | None
    entry: str | None
    tags: list[str] | None
    is_hidden: bool | None


class UpdateEntitiesParams(TypedDict):
    """Parameters for update_entities tool."""

    updates: list[EntityUpdate]


class GetEntitiesParams(TypedDict):
    """Parameters for get_entities tool."""

    entity_ids: list[int]
    include_posts: bool | None


class DeleteEntitiesParams(TypedDict):
    """Parameters for delete_entities tool."""

    entity_ids: list[int]


class PostInput(TypedDict):
    """Input for creating a post."""

    entity_id: int
    name: str
    entry: str | None
    is_hidden: bool | None


class CreatePostsParams(TypedDict):
    """Parameters for create_posts tool."""

    posts: list[PostInput]


class PostUpdate(TypedDict):
    """Update for a post."""

    entity_id: int
    post_id: int
    name: str
    entry: str | None
    is_hidden: bool | None


class UpdatePostsParams(TypedDict):
    """Parameters for update_posts tool."""

    updates: list[PostUpdate]


class PostDeletion(TypedDict):
    """Deletion for a post."""

    entity_id: int
    post_id: int


class DeletePostsParams(TypedDict):
    """Parameters for delete_posts tool."""

    deletions: list[PostDeletion]


# Response types
class EntityMinimal(TypedDict):
    """Minimal entity data returned when include_full=false."""

    entity_id: int
    name: str
    entity_type: EntityType


class EntityFull(TypedDict, total=False):
    """Full entity data returned when include_full=true."""

    id: int
    entity_id: int
    name: str
    entity_type: EntityType
    type: str | None
    entry: str | None
    tags: list[str]
    is_hidden: bool
    created_at: str  # ISO 8601 timestamp
    updated_at: str  # ISO 8601 timestamp
    match_score: float | None  # Only when name_fuzzy=true
    is_completed: bool | None  # For quests only
    image: str | None  # Local path to the picture
    image_full: str | None  # URL to the full picture
    image_thumb: str | None  # URL to the thumbnail
    image_uuid: str | None  # Image gallery UUID
    header_uuid: str | None  # Header image gallery UUID


class PostData(TypedDict):
    """Post data structure."""

    id: int
    name: str
    entry: str | None
    is_hidden: bool


class EntityWithPosts(EntityFull):
    """Entity with posts included."""

    posts: list[PostData] | None


# Sync metadata structure
class SyncInfo(TypedDict):
    """Metadata about synchronization results."""

    request_timestamp: str  # When this request was made
    newest_updated_at: str | None  # Latest updated_at from returned entities
    total_count: int  # Total matching entities (for pagination)
    returned_count: int  # Number returned in this response


class FindEntitiesResponse(TypedDict):
    """Response structure for find_entities with sync metadata."""

    entities: list[EntityMinimal | EntityFull]
    sync_info: SyncInfo


class CreateEntityResult(TypedDict):
    """Result of creating an entity."""

    id: int | None
    entity_id: int | None
    name: str
    mention: str | None
    success: bool
    error: str | None


class UpdateEntityResult(TypedDict):
    """Result of updating an entity."""

    entity_id: int
    success: bool
    error: str | None


class GetEntityResult(TypedDict, total=False):
    """Result of getting an entity."""

    id: int | None
    entity_id: int
    name: str | None
    entity_type: EntityType | None
    type: str | None
    entry: str | None
    tags: list[str] | None
    is_hidden: bool | None
    created_at: str | None  # ISO 8601 timestamp
    updated_at: str | None  # ISO 8601 timestamp
    posts: list[PostData] | None
    success: bool
    error: str | None
    is_completed: bool | None  # For quests only
    image: str | None  # Local path to the picture
    image_full: str | None  # URL to the full picture
    image_thumb: str | None  # URL to the thumbnail
    image_uuid: str | None  # Image gallery UUID
    header_uuid: str | None  # Header image gallery UUID


class DeleteEntityResult(TypedDict):
    """Result of deleting an entity."""

    entity_id: int
    success: bool
    error: str | None


class CreatePostResult(TypedDict):
    """Result of creating a post."""

    post_id: int | None
    entity_id: int
    success: bool
    error: str | None


class UpdatePostResult(TypedDict):
    """Result of updating a post."""

    entity_id: int
    post_id: int
    success: bool
    error: str | None


class DeletePostResult(TypedDict):
    """Result of deleting a post."""

    entity_id: int
    post_id: int
    success: bool
    error: str | None


# Kanka context resource structure
class KankaContextFields(TypedDict):
    """Core fields description."""

    name: str
    type: str
    entry: str
    tags: str
    is_hidden: str  # This stores the description of the is_hidden field


class KankaContextTerminology(TypedDict):
    """Terminology description."""

    entity_type: str
    type: str


class KankaContextMentions(TypedDict):
    """Mentions description."""

    description: str
    examples: list[str]
    note: str


class KankaContext(TypedDict):
    """Kanka context resource structure."""

    description: str
    supported_entities: dict[str, str]
    core_fields: KankaContextFields
    terminology: KankaContextTerminology
    posts: str
    mentions: KankaContextMentions
    limitations: str


# Check updates request/response
class CheckEntityUpdatesParams(TypedDict):
    """Parameters for check_entity_updates tool."""

    entity_ids: list[int]
    last_synced: str  # ISO 8601 timestamp


class CheckEntityUpdatesResult(TypedDict):
    """Result of checking entity updates."""

    modified_entity_ids: list[int]
    deleted_entity_ids: list[int]  # If API provides this
    check_timestamp: str  # ISO 8601 timestamp


# =============================================================================
# Attribute request / response types (Phase C)
# =============================================================================


class AttributeInput(TypedDict, total=False):
    """Input for creating an attribute on an entity.

    ``entity_id``, ``name`` are required. ``type`` defaults to ``"standard"``.
    """

    entity_id: int
    name: str
    value: str | None  # For checkbox: "1"/"0" or true/false; None for section.
    type: AttributeType | None
    is_pinned: bool | None  # Show at top of entity's attribute list.
    is_private: bool | None  # Hidden from players (admin-only).
    is_star: bool | None  # Marked as important.
    default_order: int | None  # Sort order among the entity's attributes.
    api_key: str | None  # Optional stable key for programmatic lookup.


class AttributeUpdate(TypedDict, total=False):
    """Update for an existing attribute. ``entity_id`` and ``attribute_id`` required."""

    entity_id: int
    attribute_id: int
    name: str | None
    value: str | None
    type: AttributeType | None
    is_pinned: bool | None
    is_private: bool | None
    is_star: bool | None
    default_order: int | None
    api_key: str | None


class AttributeDeletion(TypedDict):
    """Delete an attribute from an entity."""

    entity_id: int
    attribute_id: int


class AttributeData(TypedDict, total=False):
    """Normalized attribute data returned to callers."""

    id: int
    entity_id: int
    name: str
    value: Any  # str for text/number/random, bool for checkbox, None for section.
    type: AttributeType  # User-friendly type string.
    type_id: int  # Raw Kanka type_id, exposed for debugging.
    is_pinned: bool
    is_private: bool
    is_star: bool
    default_order: int
    api_key: str | None
    parsed: str | None  # Kanka's parsed/rendered form of the value.
    created_at: str | None
    updated_at: str | None


class ListAttributesParams(TypedDict):
    """Parameters for list_attributes tool."""

    entity_id: int


class ListAttributesResult(TypedDict):
    """Result of listing attributes on an entity."""

    entity_id: int
    attributes: list[AttributeData]
    success: bool
    error: str | None


class CreateAttributesParams(TypedDict):
    """Parameters for create_attributes tool."""

    attributes: list[AttributeInput]


class CreateAttributeResult(TypedDict):
    """Per-attribute result of a batch create."""

    entity_id: int
    attribute_id: int | None
    name: str
    success: bool
    error: str | None


class UpdateAttributesParams(TypedDict):
    """Parameters for update_attributes tool."""

    updates: list[AttributeUpdate]


class UpdateAttributeResult(TypedDict):
    """Per-attribute result of a batch update."""

    entity_id: int
    attribute_id: int
    success: bool
    error: str | None


class DeleteAttributesParams(TypedDict):
    """Parameters for delete_attributes tool."""

    deletions: list[AttributeDeletion]


class DeleteAttributeResult(TypedDict):
    """Per-attribute result of a batch delete."""

    entity_id: int
    attribute_id: int
    success: bool
    error: str | None


# =============================================================================
# Relation request / response types (Phase D)
# =============================================================================


class RelationInput(TypedDict, total=False):
    """Input for creating a relation between two entities.

    ``owner_id``, ``target_id``, and ``relation`` are required. If ``two_way``
    is true, Kanka creates a mirror relation on the target entity's side and
    cross-links the two via ``mirror_id``.
    """

    owner_id: int
    target_id: int
    relation: str  # Free-text label like "friend", "father", "rival".
    attitude: int | None  # -100 to 100 (attitude/disposition score).
    colour: str | None  # Hex colour or empty string.
    is_star: bool | None  # Marked as important.
    is_pinned: bool | None  # Pin to top of the entity's relation list.
    is_hidden: bool | None  # Admin-only visibility. Maps to visibility_id=2.
    two_way: bool | None  # Also create the mirror on the target's side.


class RelationUpdate(TypedDict, total=False):
    """Update for an existing relation. ``entity_id`` and ``relation_id`` required."""

    entity_id: int  # Owner entity_id (URL path).
    relation_id: int  # The Kanka relation ID.
    owner_id: int | None
    target_id: int | None
    relation: str | None
    attitude: int | None
    colour: str | None
    is_star: bool | None
    is_pinned: bool | None
    is_hidden: bool | None


class RelationDeletion(TypedDict):
    """Delete a relation. Deleting a two-way relation removes both sides."""

    entity_id: int  # Owner entity_id (URL path).
    relation_id: int


class RelationData(TypedDict, total=False):
    """Normalized relation data returned to callers."""

    id: int
    owner_id: int
    target_id: int
    relation: str
    attitude: int | None
    colour: str
    is_star: bool
    is_pinned: bool
    is_hidden: bool
    is_two_way: bool  # Derived from mirror_id being non-null.
    mirror_id: int | None
    created_at: str | None
    updated_at: str | None


class ListRelationsParams(TypedDict):
    """Parameters for list_relations tool."""

    entity_id: int


class ListRelationsResult(TypedDict):
    """Result of listing relations on an entity."""

    entity_id: int
    relations: list[RelationData]
    success: bool
    error: str | None


class CreateRelationsParams(TypedDict):
    """Parameters for create_relations tool."""

    relations: list[RelationInput]


class CreateRelationResult(TypedDict):
    """Per-relation result of a batch create."""

    owner_id: int
    target_id: int
    relation_id: int | None
    mirror_id: int | None  # Populated when two_way=true.
    success: bool
    error: str | None


class UpdateRelationsParams(TypedDict):
    """Parameters for update_relations tool."""

    updates: list[RelationUpdate]


class UpdateRelationResult(TypedDict):
    """Per-relation result of a batch update."""

    entity_id: int
    relation_id: int
    success: bool
    error: str | None


class DeleteRelationsParams(TypedDict):
    """Parameters for delete_relations tool."""

    deletions: list[RelationDeletion]


class DeleteRelationResult(TypedDict):
    """Per-relation result of a batch delete."""

    entity_id: int
    relation_id: int
    success: bool
    error: str | None


# =============================================================================
# Phase E: entity_abilities (attach ability entities to a character/creature)
# =============================================================================
#
# Endpoint: /entities/{entity_id}/entity_abilities
# Note: ``ability_id`` is the ability's TYPE-specific id (from
# ``get_entities`` result's ``id`` field), NOT the entity_id.


class EntityAbilityInput(TypedDict, total=False):
    """Input for attaching an ability to an entity."""

    entity_id: int  # Character/creature (or any entity) that gains the ability.
    ability_id: int  # Type-specific ID of the ability entity.
    charges: int | None  # Uses remaining before rest/refresh.
    note: str | None
    position: int | None  # Sort order.
    is_hidden: bool | None  # Admin-only.


class EntityAbilityUpdate(TypedDict, total=False):
    """Update for an existing entity_ability row."""

    entity_id: int
    entity_ability_id: int  # The row's ID (not the ability entity id).
    ability_id: int | None
    charges: int | None
    note: str | None
    position: int | None
    is_hidden: bool | None


class EntityAbilityDeletion(TypedDict):
    """Delete an entity_ability row."""

    entity_id: int
    entity_ability_id: int


class EntityAbilityData(TypedDict, total=False):
    """Normalized entity_ability row returned to callers."""

    id: int
    entity_id: int
    ability_id: int
    charges: int | None
    note: str | None
    position: int
    is_hidden: bool
    created_at: str | None
    updated_at: str | None


class ListEntityAbilitiesParams(TypedDict):
    entity_id: int


class ListEntityAbilitiesResult(TypedDict):
    entity_id: int
    entity_abilities: list[EntityAbilityData]
    success: bool
    error: str | None


class CreateEntityAbilitiesParams(TypedDict):
    items: list[EntityAbilityInput]


class CreateEntityAbilityResult(TypedDict):
    entity_id: int
    ability_id: int
    entity_ability_id: int | None
    success: bool
    error: str | None


class UpdateEntityAbilitiesParams(TypedDict):
    updates: list[EntityAbilityUpdate]


class UpdateEntityAbilityResult(TypedDict):
    entity_id: int
    entity_ability_id: int
    success: bool
    error: str | None


class DeleteEntityAbilitiesParams(TypedDict):
    deletions: list[EntityAbilityDeletion]


class DeleteEntityAbilityResult(TypedDict):
    entity_id: int
    entity_ability_id: int
    success: bool
    error: str | None


# =============================================================================
# Phase E: inventory (items in an entity's inventory)
# =============================================================================
#
# Endpoint: /entities/{entity_id}/inventory
# Each row either links to a real Item entity (``item_id`` is that item's
# type-specific id) OR is a freeform ``name`` string. Not both.


class InventoryInput(TypedDict, total=False):
    """Input for creating an inventory row."""

    entity_id: int
    item_id: int | None  # Type-specific ID of a Kanka Item. Nullable.
    name: str | None  # Freeform name if not linking to an Item entity.
    amount: int | None
    description: str | None
    position: str | None  # "backpack", "belt", "left hand", etc.
    is_equipped: bool | None
    is_hidden: bool | None
    copy_item_entry: bool | None  # Copy the Item entity's entry as description.


class InventoryUpdate(TypedDict, total=False):
    entity_id: int
    inventory_id: int
    item_id: int | None
    name: str | None
    amount: int | None
    description: str | None
    position: str | None
    is_equipped: bool | None
    is_hidden: bool | None


class InventoryDeletion(TypedDict):
    entity_id: int
    inventory_id: int


class InventoryData(TypedDict, total=False):
    id: int
    entity_id: int
    item_id: int | None
    name: str | None
    amount: int
    description: str | None
    position: str | None
    is_equipped: bool
    is_hidden: bool
    created_at: str | None
    updated_at: str | None


class ListInventoryParams(TypedDict):
    entity_id: int


class ListInventoryResult(TypedDict):
    entity_id: int
    inventory: list[InventoryData]
    success: bool
    error: str | None


class CreateInventoryParams(TypedDict):
    items: list[InventoryInput]


class CreateInventoryResult(TypedDict):
    entity_id: int
    inventory_id: int | None
    success: bool
    error: str | None


class UpdateInventoryParams(TypedDict):
    updates: list[InventoryUpdate]


class UpdateInventoryResult(TypedDict):
    entity_id: int
    inventory_id: int
    success: bool
    error: str | None


class DeleteInventoryParams(TypedDict):
    deletions: list[InventoryDeletion]


class DeleteInventoryResult(TypedDict):
    entity_id: int
    inventory_id: int
    success: bool
    error: str | None


# =============================================================================
# Phase E: organisation_members (character-in-organisation memberships)
# =============================================================================
#
# Endpoint: /organisations/{org_type_id}/organisation_members
# Note: ``organisation_id`` and ``character_id`` are TYPE-specific IDs, not
# entity_ids. Get them from the ``id`` field of get_entities results.


class OrganisationMemberInput(TypedDict, total=False):
    """Input for adding a character to an organisation."""

    organisation_id: int  # Organisation's type-specific id.
    character_id: int  # Character's type-specific id.
    role: str | None
    is_hidden: bool | None  # Kanka's is_private for this row.
    parent_id: int | None  # For hierarchical member structures.
    status_id: int | None
    pin_id: int | None


class OrganisationMemberUpdate(TypedDict, total=False):
    organisation_id: int
    member_id: int
    character_id: int | None
    role: str | None
    is_hidden: bool | None
    parent_id: int | None
    status_id: int | None
    pin_id: int | None


class OrganisationMemberDeletion(TypedDict):
    organisation_id: int
    member_id: int


class OrganisationMemberData(TypedDict, total=False):
    id: int
    organisation_id: int
    character_id: int
    role: str | None
    is_hidden: bool
    parent_id: int | None
    status_id: int | None
    pin_id: int | None
    created_at: str | None
    updated_at: str | None


class ListOrganisationMembersParams(TypedDict):
    organisation_id: int


class ListOrganisationMembersResult(TypedDict):
    organisation_id: int
    members: list[OrganisationMemberData]
    success: bool
    error: str | None


class CreateOrganisationMembersParams(TypedDict):
    items: list[OrganisationMemberInput]


class CreateOrganisationMemberResult(TypedDict):
    organisation_id: int
    character_id: int
    member_id: int | None
    success: bool
    error: str | None


class UpdateOrganisationMembersParams(TypedDict):
    updates: list[OrganisationMemberUpdate]


class UpdateOrganisationMemberResult(TypedDict):
    organisation_id: int
    member_id: int
    success: bool
    error: str | None


class DeleteOrganisationMembersParams(TypedDict):
    deletions: list[OrganisationMemberDeletion]


class DeleteOrganisationMemberResult(TypedDict):
    organisation_id: int
    member_id: int
    success: bool
    error: str | None


# =============================================================================
# Phase E: quest_elements (entities referenced from a quest)
# =============================================================================
#
# Endpoint: /quests/{quest_type_id}/quest_elements


class QuestElementInput(TypedDict, total=False):
    """Input for adding an element to a quest."""

    quest_id: int  # Quest's type-specific id.
    entity_id: int | None  # The referenced entity (nullable for freeform).
    name: str | None  # Optional display override.
    role: str | None
    entry: str | None  # Element description.
    colour: str | None
    is_hidden: bool | None


class QuestElementUpdate(TypedDict, total=False):
    quest_id: int
    element_id: int
    entity_id: int | None
    name: str | None
    role: str | None
    entry: str | None
    colour: str | None
    is_hidden: bool | None


class QuestElementDeletion(TypedDict):
    quest_id: int
    element_id: int


class QuestElementData(TypedDict, total=False):
    id: int
    entity_id: int | None
    name: str | None
    role: str | None
    entry: str | None
    colour: str | None
    is_hidden: bool
    created_at: str | None
    updated_at: str | None


class ListQuestElementsParams(TypedDict):
    quest_id: int


class ListQuestElementsResult(TypedDict):
    quest_id: int
    elements: list[QuestElementData]
    success: bool
    error: str | None


class CreateQuestElementsParams(TypedDict):
    items: list[QuestElementInput]


class CreateQuestElementResult(TypedDict):
    quest_id: int
    entity_id: int | None
    element_id: int | None
    success: bool
    error: str | None


class UpdateQuestElementsParams(TypedDict):
    updates: list[QuestElementUpdate]


class UpdateQuestElementResult(TypedDict):
    quest_id: int
    element_id: int
    success: bool
    error: str | None


class DeleteQuestElementsParams(TypedDict):
    deletions: list[QuestElementDeletion]


class DeleteQuestElementResult(TypedDict):
    quest_id: int
    element_id: int
    success: bool
    error: str | None


# =============================================================================
# Phase F: calendar_weather (weather entries on calendar days)
# =============================================================================
#
# Endpoint: /calendars/{calendar_type_id}/calendar_weather


class CalendarWeatherInput(TypedDict, total=False):
    calendar_id: int  # Calendar's type-specific id.
    day: int
    month: int
    year: int
    weather: str | None  # Freeform description (e.g. "Rain", "Blizzard")
    temperature: str | None  # Freeform (e.g. "Cold", "-10°C")
    is_hidden: bool | None


class CalendarWeatherUpdate(TypedDict, total=False):
    calendar_id: int
    weather_id: int
    day: int | None
    month: int | None
    year: int | None
    weather: str | None
    temperature: str | None
    is_hidden: bool | None


class CalendarWeatherDeletion(TypedDict):
    calendar_id: int
    weather_id: int


class CalendarWeatherData(TypedDict, total=False):
    id: int
    calendar_id: int
    day: int
    month: int
    year: int
    weather: str | None
    temperature: str | None
    is_hidden: bool
    created_at: str | None
    updated_at: str | None


class ListCalendarWeatherParams(TypedDict):
    calendar_id: int


class ListCalendarWeatherResult(TypedDict):
    calendar_id: int
    weather: list[CalendarWeatherData]
    success: bool
    error: str | None


class CreateCalendarWeatherParams(TypedDict):
    items: list[CalendarWeatherInput]


class CreateCalendarWeatherResult(TypedDict):
    calendar_id: int
    weather_id: int | None
    success: bool
    error: str | None


class UpdateCalendarWeatherParams(TypedDict):
    updates: list[CalendarWeatherUpdate]


class UpdateCalendarWeatherResult(TypedDict):
    calendar_id: int
    weather_id: int
    success: bool
    error: str | None


class DeleteCalendarWeatherParams(TypedDict):
    deletions: list[CalendarWeatherDeletion]


class DeleteCalendarWeatherResult(TypedDict):
    calendar_id: int
    weather_id: int
    success: bool
    error: str | None


# =============================================================================
# Phase F: timeline_eras
# =============================================================================
#
# Endpoint: /timelines/{timeline_type_id}/timeline_eras


class TimelineEraInput(TypedDict, total=False):
    timeline_id: int  # Timeline's type-specific id.
    name: str
    abbreviation: str | None
    start_year: int | None
    end_year: int | None
    entry: str | None
    position: int | None
    is_collapsed: bool | None


class TimelineEraUpdate(TypedDict, total=False):
    timeline_id: int
    era_id: int
    name: str | None
    abbreviation: str | None
    start_year: int | None
    end_year: int | None
    entry: str | None
    position: int | None
    is_collapsed: bool | None


class TimelineEraDeletion(TypedDict):
    timeline_id: int
    era_id: int


class TimelineEraData(TypedDict, total=False):
    id: int
    name: str
    abbreviation: str | None
    start_year: int | None
    end_year: int | None
    entry: str | None
    position: int
    is_collapsed: bool
    elements: list[Any]  # Nested elements when included


class ListTimelineErasParams(TypedDict):
    timeline_id: int


class ListTimelineErasResult(TypedDict):
    timeline_id: int
    eras: list[TimelineEraData]
    success: bool
    error: str | None


class CreateTimelineErasParams(TypedDict):
    items: list[TimelineEraInput]


class CreateTimelineEraResult(TypedDict):
    timeline_id: int
    era_id: int | None
    success: bool
    error: str | None


class UpdateTimelineErasParams(TypedDict):
    updates: list[TimelineEraUpdate]


class UpdateTimelineEraResult(TypedDict):
    timeline_id: int
    era_id: int
    success: bool
    error: str | None


class DeleteTimelineErasParams(TypedDict):
    deletions: list[TimelineEraDeletion]


class DeleteTimelineEraResult(TypedDict):
    timeline_id: int
    era_id: int
    success: bool
    error: str | None


# =============================================================================
# Phase F: timeline_elements
# =============================================================================
#
# Endpoint: /timelines/{timeline_type_id}/timeline_elements


class TimelineElementInput(TypedDict, total=False):
    timeline_id: int
    era_id: int  # Which era this element belongs to.
    name: str | None
    entity_id: int | None  # Optional link to an entity.
    date: str | None
    entry: str | None
    colour: str | None
    position: int | None
    icon: str | None
    is_collapsed: bool | None
    is_hidden: bool | None
    use_entity_entry: bool | None


class TimelineElementUpdate(TypedDict, total=False):
    timeline_id: int
    element_id: int
    era_id: int | None
    name: str | None
    entity_id: int | None
    date: str | None
    entry: str | None
    colour: str | None
    position: int | None
    icon: str | None
    is_collapsed: bool | None
    is_hidden: bool | None
    use_entity_entry: bool | None


class TimelineElementDeletion(TypedDict):
    timeline_id: int
    element_id: int


class TimelineElementData(TypedDict, total=False):
    id: int
    era_id: int
    timeline_id: int
    entity_id: int | None
    name: str | None
    entry: str | None
    date: str | None
    colour: str
    position: int
    icon: str | None
    is_collapsed: bool
    is_hidden: bool
    use_entity_entry: bool


class ListTimelineElementsParams(TypedDict):
    timeline_id: int


class ListTimelineElementsResult(TypedDict):
    timeline_id: int
    elements: list[TimelineElementData]
    success: bool
    error: str | None


class CreateTimelineElementsParams(TypedDict):
    items: list[TimelineElementInput]


class CreateTimelineElementResult(TypedDict):
    timeline_id: int
    era_id: int
    element_id: int | None
    success: bool
    error: str | None


class UpdateTimelineElementsParams(TypedDict):
    updates: list[TimelineElementUpdate]


class UpdateTimelineElementResult(TypedDict):
    timeline_id: int
    element_id: int
    success: bool
    error: str | None


class DeleteTimelineElementsParams(TypedDict):
    deletions: list[TimelineElementDeletion]


class DeleteTimelineElementResult(TypedDict):
    timeline_id: int
    element_id: int
    success: bool
    error: str | None
