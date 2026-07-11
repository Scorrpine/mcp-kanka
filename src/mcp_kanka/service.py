"""Service layer for Kanka API operations."""

# mypy: warn_return_any=False

import logging
import os
from datetime import datetime
from typing import Any

from kanka import KankaClient
from kanka.exceptions import KankaException
from kanka.models import (
    Character,
    Creature,
    Entity,
    Event,
    Family,
    Journal,
    Location,
    Note,
    Organisation,
    Quest,
    Race,
    Tag,
)

from .converter import ContentConverter
from .types import (
    ATTRIBUTE_ID_TO_TYPE,
    ATTRIBUTE_TYPE_TO_ID,
    HTTP_BACKED_TYPES,
    MANAGER_BACKED_TYPES,
    VALID_ATTRIBUTE_TYPES,
    AttributeData,
    AttributeType,
    CalendarWeatherData,
    CampaignData,
    CampaignUserData,
    EntityAbilityData,
    EntityType,
    InventoryData,
    OrganisationMemberData,
    QuestElementData,
    RelationData,
    RoleData,
    TimelineElementData,
    TimelineEraData,
)

logger = logging.getLogger(__name__)


# Reverse map: Kanka API's `type` field (as returned by /entities/<id>) to our
# internal entity_type. British → American spelling for organisation.
KANKA_TYPE_TO_OUR: dict[str, str] = {
    "ability": "ability",
    "calendar": "calendar",
    "character": "character",
    "creature": "creature",
    "event": "event",
    "family": "family",
    "item": "item",
    "journal": "journal",
    "location": "location",
    "note": "note",
    "organisation": "organization",
    "quest": "quest",
    "race": "race",
    "tag": "tag",
    "timeline": "timeline",
}


def _parse_dt(value: Any) -> datetime | None:
    """Parse an ISO 8601 datetime string into a datetime (or return None).

    Kanka returns timestamps like ``2023-04-01T12:34:56.000000Z``. Python's
    ``fromisoformat`` accepts the ``Z`` suffix from 3.11+, but we normalize
    to ``+00:00`` just in case a later runtime narrows behavior.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


class _HttpEntityFacade:
    """Attribute-access façade over a raw Kanka API dict.

    Used for HTTP-backed entity types (ability, item, timeline) so the existing
    ``_entity_to_dict`` code path (which expects pydantic-model-like objects
    with ``.id``, ``.entity_id``, ``.name``, ``.created_at``, etc.) works
    without a branch.

    The façade parses timestamp strings into datetimes so that
    ``entity.created_at.isoformat()`` still works.
    """

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]):
        # Store a shallow copy so upstream code can't mutate the API response.
        self._data = dict(data)

    def __getattr__(self, name: str) -> Any:
        # Called only if normal attribute lookup fails.
        if name in ("created_at", "updated_at"):
            return _parse_dt(self._data.get(name))
        if name in self._data:
            val = self._data[name]
            # Auto-wrap lists of dicts (e.g. nested posts when related=True)
            # so downstream code that uses attribute access (``post.id``,
            # ``post.name``) works transparently.
            if (
                isinstance(val, list)
                and val
                and all(isinstance(x, dict) for x in val)
            ):
                return [_HttpEntityFacade(x) for x in val]
            return val
        # Match pydantic behavior: raise AttributeError for missing.
        raise AttributeError(name)

    def __hasattr__(self, name: str) -> bool:  # pragma: no cover - not used
        return name in self._data

    # hasattr() falls through to __getattr__ and treats AttributeError as
    # "no such attribute", so the above is sufficient.


class _HttpEntityShim:
    """Duck-typed EntityManager for HTTP-backed types.

    Implements the subset of the python-kanka ``EntityManager`` interface that
    ``KankaService`` uses: ``list``, ``get``, ``create``, ``update``,
    ``delete``, ``list_posts``, ``create_post``, ``update_post``,
    ``delete_post``, and the ``has_next_page`` property.
    """

    def __init__(self, client: KankaClient, endpoint: str) -> None:
        self.client = client
        self.endpoint = endpoint
        self._last_has_next: bool = False

    @property
    def has_next_page(self) -> bool:
        return self._last_has_next

    def list(
        self,
        page: int = 1,
        related: bool = False,
        **filters: Any,
    ) -> list[_HttpEntityFacade]:
        params: dict[str, Any] = {"page": page}
        if related:
            params["related"] = 1
        # python-kanka uses ``lastSync``. Kanka accepts it on all list endpoints.
        for k, v in filters.items():
            if v is not None:
                params[k] = v
        resp = self.client._request("GET", self.endpoint, params=params)
        self._last_has_next = bool((resp.get("links") or {}).get("next"))
        return [_HttpEntityFacade(item) for item in resp.get("data", [])]

    def get(self, id: int) -> _HttpEntityFacade:
        resp = self.client._request("GET", f"{self.endpoint}/{id}")
        return _HttpEntityFacade(resp.get("data") or {})

    def create(self, **data: Any) -> _HttpEntityFacade:
        resp = self.client._request("POST", self.endpoint, json=data)
        return _HttpEntityFacade(resp.get("data") or {})

    def update(self, id: int, **data: Any) -> _HttpEntityFacade:
        resp = self.client._request("PUT", f"{self.endpoint}/{id}", json=data)
        return _HttpEntityFacade(resp.get("data") or {})

    def delete(self, id: int) -> None:
        self.client._request("DELETE", f"{self.endpoint}/{id}")

    def list_posts(
        self, entity_id: int, page: int = 1, limit: int = 100
    ) -> list[_HttpEntityFacade]:
        params: dict[str, Any] = {"page": page}
        resp = self.client._request(
            "GET", f"entities/{entity_id}/posts", params=params
        )
        return [_HttpEntityFacade(item) for item in resp.get("data", [])][:limit]

    def create_post(
        self,
        entity_id: int,
        *,
        name: str,
        entry: str = "",
        visibility_id: int = 1,
        **extra: Any,
    ) -> _HttpEntityFacade:
        data = {
            "name": name,
            "entry": entry,
            "visibility_id": visibility_id,
        }
        data.update({k: v for k, v in extra.items() if v is not None})
        resp = self.client._request(
            "POST", f"entities/{entity_id}/posts", json=data
        )
        return _HttpEntityFacade(resp.get("data") or {})

    def update_post(
        self,
        entity_id: int,
        post_id: int,
        *,
        visibility_id: int | None = None,
        **fields: Any,
    ) -> _HttpEntityFacade:
        data = {k: v for k, v in fields.items() if v is not None}
        if visibility_id is not None:
            data["visibility_id"] = visibility_id
        resp = self.client._request(
            "PATCH", f"entities/{entity_id}/posts/{post_id}", json=data
        )
        return _HttpEntityFacade(resp.get("data") or {})

    def delete_post(self, entity_id: int, post_id: int) -> None:
        self.client._request("DELETE", f"entities/{entity_id}/posts/{post_id}")


class KankaService:
    """Service layer wrapping the python-kanka client.

    Manager-backed entity types (those with a python-kanka EntityManager) route
    through ``getattr(self.client, endpoint)`` and use pydantic models. HTTP-
    backed types (ability, item, timeline) go through
    ``self.client._request(...)`` and return raw dicts, which are then normalized
    by ``_http_data_to_dict`` into the same result shape.
    """

    # Map entity types to their pydantic model classes. Only manager-backed
    # types appear here. HTTP-backed types (ability, item, timeline) have no
    # python-kanka model.
    ENTITY_TYPE_MAP = {
        "character": Character,
        "creature": Creature,
        "event": Event,
        "family": Family,
        "journal": Journal,
        "location": Location,
        "note": Note,
        "organization": Organisation,  # British spelling in API
        "quest": Quest,
        "race": Race,
        "tag": Tag,
    }

    # Map entity types to their Kanka API endpoint paths.
    # Covers both manager-backed and HTTP-backed types.
    API_ENDPOINT_MAP = {
        # manager-backed
        "calendar": "calendars",
        "character": "characters",
        "creature": "creatures",
        "event": "events",
        "family": "families",
        "journal": "journals",
        "location": "locations",
        "note": "notes",
        "organization": "organisations",  # British spelling in API
        "quest": "quests",
        "race": "races",
        "tag": "tags",
        # HTTP-backed (no python-kanka manager)
        "ability": "abilities",
        "item": "items",
        "timeline": "timelines",
    }

    def __init__(self) -> None:
        """Initialize the service with Kanka client."""
        token = os.getenv("KANKA_TOKEN")
        campaign_id = os.getenv("KANKA_CAMPAIGN_ID")

        if not token or not campaign_id:
            raise ValueError(
                "KANKA_TOKEN and KANKA_CAMPAIGN_ID environment variables are required"
            )

        self.client = KankaClient(token=token, campaign_id=int(campaign_id))
        self.converter = ContentConverter()
        self._tag_cache: dict[str, Tag] = {}
        # Cache HTTP shims by entity type so ``has_next_page`` stays consistent
        # across paginated calls for the same type (mirroring how python-kanka's
        # managers keep their ``_last_links`` state).
        self._http_shims: dict[str, _HttpEntityShim] = {}

    def _get_manager(self, entity_type: str) -> Any:
        """Return an object that quacks like ``EntityManager`` for this type.

        For manager-backed types this is the real ``python-kanka`` manager.
        For HTTP-backed types (ability, item, timeline) it's an
        ``_HttpEntityShim`` that speaks the same interface via raw HTTP.
        """
        endpoint = self.API_ENDPOINT_MAP.get(entity_type)
        if endpoint is None:
            raise ValueError(f"Unknown entity type: {entity_type!r}")
        if entity_type in HTTP_BACKED_TYPES:
            shim = self._http_shims.get(entity_type)
            if shim is None:
                shim = _HttpEntityShim(self.client, endpoint)
                self._http_shims[entity_type] = shim
            return shim
        # Manager-backed
        return getattr(self.client, endpoint)

    def search_entities(
        self,
        query: str,
        entity_type: EntityType | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Search for entities by name using list endpoints with filtering.

        This uses the list endpoints with name filtering instead of the search API,
        as they provide the same partial matching capability but with more control.

        Args:
            query: Search query (matches partial names)
            entity_type: Optional entity type filter
            limit: Maximum results

        Returns:
            List of minimal entity data
        """
        try:
            entities = []

            if entity_type:
                # Search specific entity type
                manager = self._get_manager(entity_type)

                # Use name filter to search - it does partial matching!
                results = manager.list(name=query, limit=limit)

                for entity in results:
                    entities.append(
                        {
                            "entity_id": entity.entity_id,
                            "name": entity.name,
                            "entity_type": entity_type,
                        }
                    )
            else:
                # Search across all entity types
                # We'll need to query each type separately
                remaining_limit = limit

                for our_type in self.API_ENDPOINT_MAP:
                    if remaining_limit <= 0:
                        break

                    manager = self._get_manager(our_type)

                    # Get up to remaining_limit results from this type
                    type_limit = min(remaining_limit, 100)  # API max is 100

                    try:
                        results = manager.list(name=query, limit=type_limit)

                        for entity in results:
                            entities.append(
                                {
                                    "entity_id": entity.entity_id,
                                    "name": entity.name,
                                    "entity_type": our_type,
                                }
                            )

                        remaining_limit -= len(results)

                    except Exception as e:
                        # Some entity types might not be available in the campaign
                        logger.debug(f"Could not search {our_type}: {e}")
                        continue

            return entities

        except KankaException as e:
            logger.error(f"Search failed: {e}")
            raise

    def list_entities(
        self,
        entity_type: EntityType,
        page: int = 1,
        limit: int = 100,
        last_sync: str | None = None,
        related: bool = False,
    ) -> list[Entity]:
        """
        List entities of a specific type.

        Args:
            entity_type: Entity type to list
            page: Page number
            limit: Results per page (0 for all)
            last_sync: ISO 8601 timestamp to get only entities modified after this time
            related: Include related data (posts, attributes, etc.)

        Returns:
            List of entity objects
        """
        try:
            manager = self._get_manager(entity_type)

            # Build filters
            filters = {}
            if last_sync:
                filters["lastSync"] = last_sync

            if limit == 0:
                # Get all results by paginating through all API pages
                # Use the proper pagination info from the SDK
                all_entities = []
                current_page = 1
                logger.debug(
                    f"Starting pagination for {entity_type} with related={related}"
                )

                while True:
                    logger.debug(f"Fetching page {current_page}")
                    try:
                        batch = manager.list(
                            page=current_page, related=related, **filters
                        )
                        logger.debug(
                            f"Page {current_page} returned {len(batch)} entities"
                        )

                        # Add current page results
                        all_entities.extend(batch)

                        # Check if there's a next page using SDK pagination info
                        if not manager.has_next_page:
                            logger.debug("No more pages, stopping pagination")
                            break

                        current_page += 1

                        # Safety limit to prevent infinite loops
                        if current_page > 50:
                            logger.warning(
                                f"Hit safety limit of 50 pages for {entity_type}"
                            )
                            break

                    except Exception as e:
                        logger.error(
                            f"Error fetching page {current_page} for {entity_type}: {e}"
                        )
                        break

                logger.debug(
                    f"Pagination complete for {entity_type}: {len(all_entities)} total entities"
                )
                entities = all_entities
            else:
                # Get limited results (client-side limiting)
                # Fetch pages until we have enough entities
                all_entities = []
                current_page = page  # Start from requested page
                logger.debug(
                    f"Fetching for client-side limit of {limit} {entity_type}s starting from page {page}"
                )

                while len(all_entities) < limit:
                    try:
                        batch = manager.list(
                            page=current_page, related=related, **filters
                        )

                        all_entities.extend(batch)

                        # Stop if no more pages or we have enough
                        if not manager.has_next_page or len(all_entities) >= limit:
                            break

                        current_page += 1

                        # Safety limit
                        if current_page > 50:
                            logger.warning(
                                f"Hit safety limit of 50 pages for {entity_type}"
                            )
                            break

                    except Exception as e:
                        logger.error(
                            f"Error fetching page {current_page} for {entity_type}: {e}"
                        )
                        break

                # Apply client-side limit
                entities = all_entities[:limit]

            return list(entities)

        except KankaException as e:
            logger.error(f"List entities failed: {e}")
            raise

    def get_entity_by_id(
        self, entity_id: int, include_posts: bool = False
    ) -> dict[str, Any] | None:
        """
        Get a specific entity by its entity_id.

        Args:
            entity_id: Entity ID
            include_posts: Whether to include posts

        Returns:
            Entity data with converted content
        """
        try:
            # Use the direct entity endpoint
            found_entity = self.client.entity(entity_id)

            if not found_entity:
                # Entity not found
                return None

            # Get entity type - it's in the 'type' field
            entity_type = found_entity.get("type")

            # Map to our internal type
            # Map the Kanka API's ``type`` field to our internal entity_type.
            # This includes both manager-backed and HTTP-backed types.
            our_type = KANKA_TYPE_TO_OUR.get(entity_type or "")
            if our_type is None:
                return None

            # The entity endpoint returns the data in 'child' field
            child_data = found_entity.get("child")
            if not child_data:
                return None

            # Get the type-specific ID
            type_id = child_data.get("id")
            if not type_id:
                return None

            # Now use the type-specific manager to get a proper entity object
            # This gives us consistent data format with datetime objects
            manager = self._get_manager(our_type)
            entity = manager.get(type_id)

            # Use _entity_to_dict to handle all conversions consistently
            result = self._entity_to_dict(entity, our_type)

            # Get posts if requested
            if include_posts:
                try:
                    # Get the manager for this entity type
                    manager = self._get_manager(our_type)
                    # Use entity_id, not the type-specific id
                    posts = manager.list_posts(entity_id, limit=100)
                    result["posts"] = [self._post_to_dict(post) for post in posts]
                except Exception as e:
                    logger.warning(f"Failed to get posts for entity {entity_id}: {e}")
                    result["posts"] = []

            return result

        except Exception as e:
            logger.error(f"Get entity failed for {entity_id}: {e}")
            return None

    def create_entity(
        self,
        entity_type: EntityType,
        name: str,
        type: str | None = None,
        entry: str | None = None,
        tags: list[str] | None = None,
        is_hidden: bool | None = None,
        is_completed: bool | None = None,
        image_uuid: str | None = None,
        header_uuid: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new entity.

        Args:
            entity_type: Type of entity
            name: Entity name
            type: Entity subtype
            entry: Description in Markdown
            tags: List of tag names
            is_hidden: Whether entity should be hidden from players (admin-only)
            is_completed: Whether quest is completed (quests only)
            image_uuid: Image gallery UUID for entity image
            header_uuid: Image gallery UUID for entity header

        Returns:
            Created entity data
        """
        try:
            manager = self._get_manager(entity_type)

            # Prepare data
            data: dict[str, Any] = {"name": name}

            if type is not None:
                data["type"] = type

            if entry is not None:
                # Convert markdown to HTML
                data["entry"] = self.converter.markdown_to_html(entry)

            # Set privacy based on is_hidden
            # For entities, use is_private (not visibility_id)
            if is_hidden is not None:
                data["is_private"] = is_hidden
            elif entity_type == "note":
                # Notes default to private
                data["is_private"] = True
            else:
                # Default to public
                data["is_private"] = False

            # Handle tags
            if tags:
                tag_ids = self._get_or_create_tag_ids(tags)
                data["tags"] = tag_ids

            # Handle quest-specific field
            if entity_type == "quest" and is_completed is not None:
                data["is_completed"] = is_completed

            # Handle image fields
            if image_uuid is not None:
                data["image_uuid"] = image_uuid
            if header_uuid is not None:
                data["header_uuid"] = header_uuid

            # Create entity
            entity = manager.create(**data)

            # Convert to our format
            result = self._entity_to_dict(entity, entity_type)
            result["mention"] = f"[entity:{entity.entity_id}]"

            # If we explicitly set privacy, ensure it's reflected in the result
            # The API might not return is_private in the create response
            if "is_private" in data:
                result["is_hidden"] = data["is_private"]

            return result

        except KankaException as e:
            logger.error(f"Create entity failed: {e}")
            raise

    def update_entity(
        self,
        entity_id: int,
        name: str,
        type: str | None = None,
        entry: str | None = None,
        tags: list[str] | None = None,
        is_hidden: bool | None = None,
        is_completed: bool | None = None,
        image_uuid: str | None = None,
        header_uuid: str | None = None,
        title: str | None = None,
        race_ids: list[int] | None = None,
        date: str | None = None,
    ) -> bool:
        """
        Update an existing entity.

        Args:
            entity_id: Entity ID
            name: Entity name (required by API)
            type: Entity subtype
            entry: Description in Markdown
            tags: List of tag names
            is_hidden: Whether entity should be hidden from players (admin-only)
            is_completed: Whether quest is completed (quests only)
            image_uuid: Image gallery UUID for entity image
            header_uuid: Image gallery UUID for entity header
            title: Character's title field (characters only, e.g. "The Wise").
            race_ids: List of race TYPE-SPECIFIC ids the character belongs to.
                (Characters only. Use ``get_entities`` to look up type_ids.)
            date: Calendar's current date, e.g. "741-5-27" (calendars only).
                Great for advancing the campaign clock.

        Returns:
            True if successful
        """
        try:
            # First get the entity to find its type
            entity_data = self.get_entity_by_id(entity_id)
            if not entity_data:
                raise ValueError(f"Entity {entity_id} not found")

            entity_type = entity_data["entity_type"]
            manager = self._get_manager(entity_type)

            # Prepare update data
            data: dict[str, Any] = {"name": name}

            if type is not None:
                data["type"] = type

            if entry is not None:
                # Convert markdown to HTML
                data["entry"] = self.converter.markdown_to_html(entry)

            # Handle privacy
            # For entities, use is_private (not visibility_id)
            if is_hidden is not None:
                data["is_private"] = is_hidden

            # Handle tags
            if tags is not None:
                tag_ids = self._get_or_create_tag_ids(tags)
                data["tags"] = tag_ids

            # Handle quest-specific field
            if entity_type == "quest" and is_completed is not None:
                data["is_completed"] = is_completed

            # Handle character-specific fields (title, races).
            if entity_type == "character":
                if title is not None:
                    data["title"] = title
                if race_ids is not None:
                    data["races"] = race_ids

            # Handle calendar-specific field (current date).
            if entity_type == "calendar" and date is not None:
                data["date"] = date

            # Handle image fields
            if image_uuid is not None:
                data["image_uuid"] = image_uuid
            if header_uuid is not None:
                data["header_uuid"] = header_uuid

            # Update entity
            manager.update(entity_data["id"], **data)
            return True

        except Exception as e:
            logger.error(f"Update entity failed for {entity_id}: {e}")
            raise

    def delete_entity(self, entity_id: int) -> bool:
        """
        Delete an entity.

        Args:
            entity_id: Entity ID

        Returns:
            True if successful
        """
        try:
            # First get the entity to find its type
            entity_data = self.get_entity_by_id(entity_id)
            if not entity_data:
                raise ValueError(f"Entity {entity_id} not found")

            entity_type = entity_data["entity_type"]
            manager = self._get_manager(entity_type)

            # Delete entity
            manager.delete(entity_data["id"])
            return True

        except Exception as e:
            logger.error(f"Delete entity failed for {entity_id}: {e}")
            raise

    def create_post(
        self,
        entity_id: int,
        name: str,
        entry: str | None = None,
        is_hidden: bool = False,
    ) -> dict[str, Any]:
        """
        Create a post on an entity.

        Args:
            entity_id: Entity ID
            name: Post title
            entry: Post content in Markdown
            is_hidden: Whether post should be hidden from players (admin-only)

        Returns:
            Created post data
        """
        try:
            # Get entity to find its type
            entity_data = self.get_entity_by_id(entity_id)
            if not entity_data:
                raise ValueError(f"Entity {entity_id} not found")

            entity_type = entity_data["entity_type"]
            manager = self._get_manager(entity_type)

            # Convert markdown to HTML if entry provided
            html_entry = self.converter.markdown_to_html(entry) if entry else None

            # Set visibility based on is_hidden
            visibility_id = 2 if is_hidden else 1

            # Create post - use entity_id, not the type-specific id
            post = manager.create_post(
                entity_id,
                name=name,
                entry=html_entry or "",
                visibility_id=visibility_id,
            )

            return {
                "post_id": post.id,
                "entity_id": entity_id,
            }

        except Exception as e:
            logger.error(f"Create post failed: {e}")
            raise

    def update_post(
        self,
        entity_id: int,
        post_id: int,
        name: str,
        entry: str | None = None,
        is_hidden: bool | None = None,
    ) -> bool:
        """
        Update a post.

        Args:
            entity_id: Entity ID
            post_id: Post ID
            name: Post title (required by API)
            entry: Post content in Markdown
            is_hidden: Whether post should be hidden from players (admin-only)

        Returns:
            True if successful
        """
        try:
            # Get entity to find its type
            entity_data = self.get_entity_by_id(entity_id)
            if not entity_data:
                raise ValueError(f"Entity {entity_id} not found")

            entity_type = entity_data["entity_type"]
            manager = self._get_manager(entity_type)

            # Prepare update data
            kwargs: dict[str, Any] = {"name": name}

            if entry is not None:
                kwargs["entry"] = self.converter.markdown_to_html(entry)

            # Handle visibility
            # For posts, use visibility_id
            visibility_id = None
            if is_hidden is not None:
                visibility_id = 2 if is_hidden else 1

            # Update post - use entity_id, not the type-specific id
            manager.update_post(
                entity_id, post_id, visibility_id=visibility_id, **kwargs
            )
            return True

        except Exception as e:
            logger.error(f"Update post failed: {e}")
            raise

    def delete_post(self, entity_id: int, post_id: int) -> bool:
        """
        Delete a post.

        Args:
            entity_id: Entity ID
            post_id: Post ID

        Returns:
            True if successful
        """
        try:
            # Get entity to find its type
            entity_data = self.get_entity_by_id(entity_id)
            if not entity_data:
                raise ValueError(f"Entity {entity_id} not found")

            entity_type = entity_data["entity_type"]
            manager = self._get_manager(entity_type)

            # Delete post - use entity_id, not the type-specific id
            manager.delete_post(entity_id, post_id)
            return True

        except Exception as e:
            logger.error(f"Delete post failed: {e}")
            raise

    def _get_or_create_tag_ids(self, tag_names: list[str]) -> list[int]:
        """
        Get or create tags by name.

        Args:
            tag_names: List of tag names

        Returns:
            List of tag IDs
        """
        # Load tag cache if needed
        if not self._tag_cache:
            self._load_tag_cache()

        tag_ids = []
        for name in tag_names:
            name_lower = name.lower()

            # Check cache
            if name_lower in self._tag_cache:
                tag_ids.append(self._tag_cache[name_lower].id)
            else:
                # Create new tag
                try:
                    tag = self.client.tags.create(name=name)
                    self._tag_cache[name_lower] = tag
                    tag_ids.append(tag.id)
                except Exception as e:
                    logger.warning(f"Failed to create tag '{name}': {e}")

        return tag_ids

    def _load_tag_cache(self) -> None:
        """Load all tags into cache."""
        self._tag_cache = {}
        try:
            # Get all tags by paginating through them
            current_page = 1
            while True:
                batch = self.client.tags.list(page=current_page, limit=100)
                if not batch:
                    break
                for tag in batch:
                    self._tag_cache[tag.name.lower()] = tag
                if len(batch) < 100:
                    break
                current_page += 1
        except Exception as e:
            logger.warning(f"Failed to load tag cache: {e}")

    def _resolve_tag_names(self, raw_tags: list[Any]) -> list[str]:
        """
        Resolve tag IDs to tag names.

        Args:
            raw_tags: List of tag IDs or tag objects

        Returns:
            List of tag names
        """
        if not raw_tags or not isinstance(raw_tags, list):
            return []

        # Ensure tag cache is loaded
        if not self._tag_cache:
            self._load_tag_cache()

        tag_names = []
        for tag_item in raw_tags:
            if isinstance(tag_item, int | str):
                # It's a tag ID, need to look it up
                tag_id = int(tag_item) if isinstance(tag_item, str) else tag_item

                # Check cache first
                tag_name = None
                for _cached_name, cached_tag in self._tag_cache.items():
                    if cached_tag.id == tag_id:
                        tag_name = cached_tag.name
                        break

                if tag_name:
                    tag_names.append(tag_name)
                else:
                    # Not in cache, try to fetch it
                    try:
                        tag = self.client.tags.get(tag_id)
                        tag_names.append(tag.name)
                        # Add to cache for future lookups
                        self._tag_cache[tag.name.lower()] = tag
                    except Exception as e:
                        logger.warning(f"Failed to resolve tag ID {tag_id}: {e}")
                        # If we can't resolve it, keep the ID as string
                        tag_names.append(str(tag_id))
            elif hasattr(tag_item, "name"):
                # It's a tag object
                tag_names.append(tag_item.name)
            else:
                # Unknown format, keep as string
                tag_names.append(str(tag_item))

        return tag_names

    def _entity_to_dict(self, entity: Entity, entity_type: str) -> dict[str, Any]:
        """
        Convert entity object to dictionary.

        Args:
            entity: Entity object
            entity_type: Our entity type string

        Returns:
            Dictionary representation
        """
        result: dict[str, Any] = {
            "id": entity.id,
            "entity_id": entity.entity_id,
            "name": entity.name,
            "entity_type": entity_type,
            "type": getattr(entity, "type", None),
            "tags": [],
            "created_at": (
                entity.created_at.isoformat()
                if hasattr(entity, "created_at") and entity.created_at
                else None
            ),
            "updated_at": (
                entity.updated_at.isoformat()
                if hasattr(entity, "updated_at") and entity.updated_at
                else None
            ),
        }

        # Handle visibility - translate is_private to is_hidden
        # Entities use is_private field
        is_private = getattr(entity, "is_private", None)
        if is_private is not None:
            result["is_hidden"] = is_private
        else:
            # Default to visible if no is_private field
            result["is_hidden"] = False

        # Convert HTML entry to Markdown
        if hasattr(entity, "entry") and entity.entry:
            result["entry"] = self.converter.html_to_markdown(entity.entry)
        else:
            result["entry"] = None

        # Extract tag names using helper method
        if hasattr(entity, "tags"):
            result["tags"] = self._resolve_tag_names(entity.tags)

        # Handle posts if present (when related=True)
        if hasattr(entity, "posts") and entity.posts is not None:
            result["posts"] = [self._post_to_dict(post) for post in entity.posts]

        # Handle quest-specific fields
        if entity_type == "quest":
            result["is_completed"] = getattr(entity, "is_completed", None)

        # Handle image fields - always include all 5 fields
        result["image"] = getattr(entity, "image", None)
        result["image_full"] = getattr(entity, "image_full", None)
        result["image_thumb"] = getattr(entity, "image_thumb", None)
        result["image_uuid"] = getattr(entity, "image_uuid", None)
        result["header_uuid"] = getattr(entity, "header_uuid", None)

        return result

    def _post_to_dict(self, post: Any) -> dict[str, Any]:
        """
        Convert post object to dictionary.

        Args:
            post: Post object

        Returns:
            Dictionary representation
        """
        result = {
            "id": post.id,
            "name": post.name,
        }

        # Handle visibility - translate visibility_id to is_hidden
        # Posts use visibility_id field
        visibility_id = getattr(post, "visibility_id", None)
        if visibility_id is not None:
            # visibility_id 2 = admin only (hidden from players)
            result["is_hidden"] = visibility_id == 2
        else:
            # Default to visible if no visibility_id
            result["is_hidden"] = False

        # Convert HTML entry to Markdown
        if hasattr(post, "entry") and post.entry:
            result["entry"] = self.converter.html_to_markdown(post.entry)
        else:
            result["entry"] = None

        return result

    # =========================================================================
    # Attributes (Phase C)
    # =========================================================================

    def list_attributes(self, entity_id: int) -> list[AttributeData]:
        """List all attributes on an entity.

        Args:
            entity_id: The entity_id (not the type-specific id).

        Returns:
            List of normalized attribute dicts.
        """
        try:
            resp = self.client._request(
                "GET", f"entities/{entity_id}/attributes"
            )
            return [self._attribute_to_dict(a) for a in resp.get("data", [])]
        except Exception as e:
            logger.error(f"list_attributes failed for entity {entity_id}: {e}")
            raise

    def create_attribute(
        self,
        entity_id: int,
        name: str,
        value: str | None = None,
        type: AttributeType | None = None,
        is_pinned: bool | None = None,
        is_private: bool | None = None,
        is_star: bool | None = None,
        default_order: int | None = None,
        api_key: str | None = None,
    ) -> AttributeData:
        """Create an attribute on an entity.

        Args:
            entity_id: The entity to attach the attribute to.
            name: Attribute name (required).
            value: Attribute value. For ``checkbox`` supply ``"1"``/``"0"``
                or truthy string; for ``section`` leave as ``None``.
            type: One of ``standard`` (default), ``number``, ``checkbox``,
                ``section``, ``random``.
            is_pinned: Pin to the top of the entity's attribute list.
            is_private: Hidden from players (admin-only).
            is_star: Mark as important (starred).
            default_order: Numeric sort order.
            api_key: Optional stable key for programmatic lookup.

        Returns:
            The created attribute (normalized).
        """
        payload = self._attribute_payload(
            name=name,
            value=value,
            type=type,
            is_pinned=is_pinned,
            is_private=is_private,
            is_star=is_star,
            default_order=default_order,
            api_key=api_key,
        )
        # ``name`` is required by the Kanka API.
        payload["name"] = name
        try:
            resp = self.client._request(
                "POST", f"entities/{entity_id}/attributes", json=payload
            )
            return self._attribute_to_dict(resp.get("data") or {})
        except Exception as e:
            logger.error(
                f"create_attribute failed for entity {entity_id} ({name!r}): {e}"
            )
            raise

    def update_attribute(
        self,
        entity_id: int,
        attribute_id: int,
        name: str | None = None,
        value: str | None = None,
        type: AttributeType | None = None,
        is_pinned: bool | None = None,
        is_private: bool | None = None,
        is_star: bool | None = None,
        default_order: int | None = None,
        api_key: str | None = None,
    ) -> AttributeData:
        """Update an attribute on an entity."""
        payload = self._attribute_payload(
            name=name,
            value=value,
            type=type,
            is_pinned=is_pinned,
            is_private=is_private,
            is_star=is_star,
            default_order=default_order,
            api_key=api_key,
        )
        if not payload:
            raise ValueError(
                "update_attribute needs at least one field to update"
            )
        try:
            resp = self.client._request(
                "PATCH",
                f"entities/{entity_id}/attributes/{attribute_id}",
                json=payload,
            )
            return self._attribute_to_dict(resp.get("data") or {})
        except Exception as e:
            logger.error(
                f"update_attribute failed for entity {entity_id} "
                f"attribute {attribute_id}: {e}"
            )
            raise

    def delete_attribute(self, entity_id: int, attribute_id: int) -> bool:
        """Delete an attribute from an entity."""
        try:
            self.client._request(
                "DELETE", f"entities/{entity_id}/attributes/{attribute_id}"
            )
            return True
        except Exception as e:
            logger.error(
                f"delete_attribute failed for entity {entity_id} "
                f"attribute {attribute_id}: {e}"
            )
            raise

    def _attribute_payload(
        self,
        name: str | None,
        value: str | None,
        type: AttributeType | None,
        is_pinned: bool | None,
        is_private: bool | None,
        is_star: bool | None,
        default_order: int | None,
        api_key: str | None,
    ) -> dict[str, Any]:
        """Build a POST/PATCH payload for an attribute.

        Only sends fields the caller explicitly set. Translates the
        user-facing ``type`` string into Kanka's numeric ``type_id``.
        """
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if value is not None:
            payload["value"] = value
        if type is not None:
            if type not in VALID_ATTRIBUTE_TYPES:
                raise ValueError(
                    f"Invalid attribute type {type!r}. "
                    f"Must be one of: {', '.join(VALID_ATTRIBUTE_TYPES)}"
                )
            payload["type_id"] = ATTRIBUTE_TYPE_TO_ID[type]
        if is_pinned is not None:
            payload["is_pinned"] = is_pinned
        if is_private is not None:
            payload["is_private"] = is_private
        if is_star is not None:
            payload["is_star"] = is_star
        if default_order is not None:
            payload["default_order"] = default_order
        if api_key is not None:
            payload["api_key"] = api_key
        return payload

    @staticmethod
    def _attribute_to_dict(raw: dict[str, Any]) -> AttributeData:
        """Convert a raw Kanka attribute dict to our normalized shape.

        Translates numeric ``type_id`` back to the user-friendly ``type``
        string and preserves the raw ``type_id`` alongside for debugging.
        """
        type_id = raw.get("type_id")
        type_str = ATTRIBUTE_ID_TO_TYPE.get(type_id, "standard") if type_id else "standard"
        return {
            "id": raw.get("id"),
            "entity_id": raw.get("entity_id"),
            "name": raw.get("name", ""),
            "value": raw.get("value"),
            "type": type_str,  # type: ignore[typeddict-item]
            "type_id": type_id or ATTRIBUTE_TYPE_TO_ID["standard"],
            "is_pinned": bool(raw.get("is_pinned", False)),
            "is_private": bool(raw.get("is_private", False)),
            "is_star": bool(raw.get("is_star", False)),
            "default_order": raw.get("default_order", 0),
            "api_key": raw.get("api_key"),
            "parsed": raw.get("parsed"),
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
        }

    # =========================================================================
    # Relations (Phase D)
    # =========================================================================

    def list_relations(self, entity_id: int) -> list[RelationData]:
        """List all relations owned by an entity.

        Args:
            entity_id: The owner entity_id.

        Returns:
            List of normalized relation dicts.
        """
        try:
            resp = self.client._request(
                "GET", f"entities/{entity_id}/relations"
            )
            return [self._relation_to_dict(r) for r in resp.get("data", [])]
        except Exception as e:
            logger.error(f"list_relations failed for entity {entity_id}: {e}")
            raise

    def create_relation(
        self,
        owner_id: int,
        target_id: int,
        relation: str,
        attitude: int | None = None,
        colour: str | None = None,
        is_star: bool | None = None,
        is_pinned: bool | None = None,
        is_hidden: bool | None = None,
        two_way: bool | None = None,
    ) -> RelationData:
        """Create a relation from ``owner_id`` to ``target_id``.

        When ``two_way`` is true, Kanka also creates a mirror on the target
        entity's side and cross-links via ``mirror_id``.

        Returns:
            The newly-created (owner-side) relation, normalized. If two_way
            was true, ``mirror_id`` on the result points at the mirror.
        """
        payload = self._relation_payload(
            owner_id=owner_id,
            target_id=target_id,
            relation=relation,
            attitude=attitude,
            colour=colour,
            is_star=is_star,
            is_pinned=is_pinned,
            is_hidden=is_hidden,
            two_way=two_way,
        )
        # ``owner_id``, ``target_id``, and ``relation`` are all required.
        payload["owner_id"] = owner_id
        payload["target_id"] = target_id
        payload["relation"] = relation
        try:
            resp = self.client._request(
                "POST", f"entities/{owner_id}/relations", json=payload
            )
            # Kanka's POST /relations returns ``data`` as a list. Pick the
            # highest-id item (auto-increment; the just-created row is the
            # newest even when pre-existing relations show up in the list).
            data = resp.get("data") or []
            if not isinstance(data, list) or not data:
                raise ValueError("Unexpected empty response from create_relation")
            newest = max(data, key=lambda d: d.get("id") or 0)
            return self._relation_to_dict(newest)
        except Exception as e:
            logger.error(
                f"create_relation failed ({owner_id} -> {target_id}): {e}"
            )
            raise

    def update_relation(
        self,
        entity_id: int,
        relation_id: int,
        owner_id: int | None = None,
        target_id: int | None = None,
        relation: str | None = None,
        attitude: int | None = None,
        colour: str | None = None,
        is_star: bool | None = None,
        is_pinned: bool | None = None,
        is_hidden: bool | None = None,
    ) -> RelationData:
        """Update an existing relation.

        Args:
            entity_id: The owner entity_id (used to build the URL path).
            relation_id: The relation ID (not entity_id) to update.
        """
        payload = self._relation_payload(
            owner_id=owner_id,
            target_id=target_id,
            relation=relation,
            attitude=attitude,
            colour=colour,
            is_star=is_star,
            is_pinned=is_pinned,
            is_hidden=is_hidden,
            two_way=None,  # two_way flips at creation; not editable via PATCH.
        )
        if not payload:
            raise ValueError(
                "update_relation needs at least one field to update"
            )
        try:
            resp = self.client._request(
                "PATCH",
                f"entities/{entity_id}/relations/{relation_id}",
                json=payload,
            )
            data = resp.get("data") or {}
            return self._relation_to_dict(data)
        except Exception as e:
            logger.error(
                f"update_relation failed (entity={entity_id}, rel={relation_id}): {e}"
            )
            raise

    def delete_relation(self, entity_id: int, relation_id: int) -> bool:
        """Delete a relation.

        Note: Kanka's DELETE on a two-way relation only removes the row on the
        specified owner's side. The mirror row on the target entity survives.
        If you want both sides gone, delete both relation IDs explicitly.
        Confirmed via live probe against campaign 396026 on 2026-07-10.
        """
        try:
            self.client._request(
                "DELETE", f"entities/{entity_id}/relations/{relation_id}"
            )
            return True
        except Exception as e:
            logger.error(
                f"delete_relation failed (entity={entity_id}, rel={relation_id}): {e}"
            )
            raise

    @staticmethod
    def _relation_payload(
        owner_id: int | None,
        target_id: int | None,
        relation: str | None,
        attitude: int | None,
        colour: str | None,
        is_star: bool | None,
        is_pinned: bool | None,
        is_hidden: bool | None,
        two_way: bool | None,
    ) -> dict[str, Any]:
        """Build a POST/PATCH payload for a relation, omitting None fields.

        Translates our ``is_hidden`` bool into Kanka's ``visibility_id`` (1
        for visible, 2 for admin-only).
        """
        payload: dict[str, Any] = {}
        if owner_id is not None:
            payload["owner_id"] = owner_id
        if target_id is not None:
            payload["target_id"] = target_id
        if relation is not None:
            payload["relation"] = relation
        if attitude is not None:
            payload["attitude"] = attitude
        if colour is not None:
            payload["colour"] = colour
        if is_star is not None:
            payload["is_star"] = is_star
        if is_pinned is not None:
            payload["is_pinned"] = is_pinned
        if is_hidden is not None:
            payload["visibility_id"] = 2 if is_hidden else 1
        if two_way is not None:
            payload["two_way"] = two_way
        return payload

    @staticmethod
    def _relation_to_dict(raw: dict[str, Any]) -> RelationData:
        """Normalize a raw Kanka relation dict.

        Translates ``visibility_id`` back to ``is_hidden`` and derives
        ``is_two_way`` from ``mirror_id``.
        """
        visibility_id = raw.get("visibility_id")
        return {
            "id": raw.get("id"),
            "owner_id": raw.get("owner_id"),
            "target_id": raw.get("target_id"),
            "relation": raw.get("relation", ""),
            "attitude": raw.get("attitude"),
            "colour": raw.get("colour", "") or "",
            "is_star": bool(raw.get("is_star", False)),
            "is_pinned": bool(raw.get("is_pinned", False)),
            "is_hidden": visibility_id == 2,
            "is_two_way": raw.get("mirror_id") is not None,
            "mirror_id": raw.get("mirror_id"),
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
        }

    # =========================================================================
    # Entity abilities (Phase E)
    # =========================================================================

    def list_entity_abilities(self, entity_id: int) -> list[EntityAbilityData]:
        """List all ability attachments on an entity."""
        try:
            resp = self.client._request(
                "GET", f"entities/{entity_id}/entity_abilities"
            )
            return [
                self._entity_ability_to_dict(r) for r in resp.get("data", [])
            ]
        except Exception as e:
            logger.error(
                f"list_entity_abilities failed for entity {entity_id}: {e}"
            )
            raise

    def create_entity_ability(
        self,
        entity_id: int,
        ability_id: int,
        charges: int | None = None,
        note: str | None = None,
        position: int | None = None,
        is_hidden: bool | None = None,
    ) -> EntityAbilityData:
        """Attach an ability entity to an entity.

        Args:
            entity_id: The entity gaining the ability.
            ability_id: The ability's TYPE-specific id (not entity_id).
                Get it from ``get_entities`` result's ``id`` field.
        """
        # Kanka's POST accepts an ``abilities: [id]`` array. A single call can
        # attach multiple; we standardize on one-per-call and return the
        # newly-created row.
        payload: dict[str, Any] = {"abilities": [ability_id]}
        if charges is not None:
            payload["charges"] = charges
        if note is not None:
            payload["note"] = note
        if position is not None:
            payload["position"] = position
        if is_hidden is not None:
            payload["visibility_id"] = 2 if is_hidden else 1
        try:
            resp = self.client._request(
                "POST",
                f"entities/{entity_id}/entity_abilities",
                json=payload,
            )
            data = resp.get("data")
            if isinstance(data, list) and data:
                data = data[-1]  # newest
            elif not isinstance(data, dict):
                raise ValueError(
                    "Unexpected empty response from create_entity_ability"
                )
            result = self._entity_ability_to_dict(data)
            # The API doesn't echo entity_id back in the ability row; inject.
            result["entity_id"] = entity_id
            return result
        except Exception as e:
            logger.error(
                f"create_entity_ability failed (entity={entity_id}, "
                f"ability={ability_id}): {e}"
            )
            raise

    def update_entity_ability(
        self,
        entity_id: int,
        entity_ability_id: int,
        ability_id: int | None = None,
        charges: int | None = None,
        note: str | None = None,
        position: int | None = None,
        is_hidden: bool | None = None,
    ) -> EntityAbilityData:
        """Update an existing entity_ability row.

        Kanka's PATCH requires ``abilities`` to be present. If the caller
        doesn't supply ``ability_id``, we fetch the current row and reuse
        its ability_id so partial updates work as expected.
        """
        payload: dict[str, Any] = {}
        if ability_id is None:
            # Fetch current row to pick up its ability_id.
            current = next(
                (
                    r
                    for r in self.list_entity_abilities(entity_id)
                    if r.get("id") == entity_ability_id
                ),
                None,
            )
            if current is None:
                raise ValueError(
                    f"entity_ability {entity_ability_id} not found on "
                    f"entity {entity_id}"
                )
            ability_id = current.get("ability_id")
        payload["abilities"] = [ability_id]
        if charges is not None:
            payload["charges"] = charges
        if note is not None:
            payload["note"] = note
        if position is not None:
            payload["position"] = position
        if is_hidden is not None:
            payload["visibility_id"] = 2 if is_hidden else 1
        try:
            resp = self.client._request(
                "PATCH",
                f"entities/{entity_id}/entity_abilities/{entity_ability_id}",
                json=payload,
            )
            data = resp.get("data") or {}
            result = self._entity_ability_to_dict(data)
            result.setdefault("entity_id", entity_id)
            return result
        except Exception as e:
            logger.error(
                f"update_entity_ability failed (entity={entity_id}, "
                f"row={entity_ability_id}): {e}"
            )
            raise

    def delete_entity_ability(
        self, entity_id: int, entity_ability_id: int
    ) -> bool:
        """Remove an ability attachment from an entity."""
        try:
            self.client._request(
                "DELETE",
                f"entities/{entity_id}/entity_abilities/{entity_ability_id}",
            )
            return True
        except Exception as e:
            logger.error(
                f"delete_entity_ability failed (entity={entity_id}, "
                f"row={entity_ability_id}): {e}"
            )
            raise

    @staticmethod
    def _entity_ability_to_dict(raw: dict[str, Any]) -> EntityAbilityData:
        visibility_id = raw.get("visibility_id")
        return {
            "id": raw.get("id"),
            "entity_id": raw.get("entity_id"),
            "ability_id": raw.get("ability_id"),
            "charges": raw.get("charges"),
            "note": raw.get("note"),
            "position": raw.get("position", 0) or 0,
            "is_hidden": visibility_id == 2,
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
        }

    # =========================================================================
    # Inventory (Phase E)
    # =========================================================================

    def list_inventory(self, entity_id: int) -> list[InventoryData]:
        """List all inventory rows for an entity."""
        try:
            resp = self.client._request(
                "GET", f"entities/{entity_id}/inventory"
            )
            return [self._inventory_to_dict(r) for r in resp.get("data", [])]
        except Exception as e:
            logger.error(
                f"list_inventory failed for entity {entity_id}: {e}"
            )
            raise

    def create_inventory(
        self,
        entity_id: int,
        item_id: int | None = None,
        name: str | None = None,
        amount: int | None = None,
        description: str | None = None,
        position: str | None = None,
        is_equipped: bool | None = None,
        is_hidden: bool | None = None,
        copy_item_entry: bool | None = None,
    ) -> InventoryData:
        """Add an inventory row.

        Either ``item_id`` (Kanka Item type-specific id) or ``name`` (freeform
        string) should be provided. Both is allowed but redundant.
        """
        if item_id is None and not name:
            raise ValueError(
                "create_inventory needs either item_id or name (or both)"
            )
        # Kanka requires ``entity_id`` in the JSON body as well as in the URL.
        payload: dict[str, Any] = {"entity_id": entity_id}
        if item_id is not None:
            payload["item_id"] = item_id
        if name is not None:
            payload["name"] = name
        if amount is not None:
            payload["amount"] = amount
        if description is not None:
            payload["description"] = description
        if position is not None:
            payload["position"] = position
        if is_equipped is not None:
            payload["is_equipped"] = is_equipped
        if is_hidden is not None:
            payload["visibility_id"] = 2 if is_hidden else 1
        if copy_item_entry is not None:
            payload["copy_item_entry"] = copy_item_entry
        try:
            resp = self.client._request(
                "POST", f"entities/{entity_id}/inventory", json=payload
            )
            return self._inventory_to_dict(resp.get("data") or {})
        except Exception as e:
            logger.error(f"create_inventory failed for entity {entity_id}: {e}")
            raise

    def update_inventory(
        self,
        entity_id: int,
        inventory_id: int,
        item_id: int | None = None,
        name: str | None = None,
        amount: int | None = None,
        description: str | None = None,
        position: str | None = None,
        is_equipped: bool | None = None,
        is_hidden: bool | None = None,
    ) -> InventoryData:
        """Update an inventory row.

        Kanka's PATCH requires at least one of ``item_id`` or ``name``. If
        neither is supplied we fetch the current row so partial updates work.
        """
        payload: dict[str, Any] = {}
        if item_id is None and name is None:
            current = next(
                (
                    r
                    for r in self.list_inventory(entity_id)
                    if r.get("id") == inventory_id
                ),
                None,
            )
            if current is None:
                raise ValueError(
                    f"inventory row {inventory_id} not found on entity {entity_id}"
                )
            if current.get("item_id") is not None:
                payload["item_id"] = current["item_id"]
            elif current.get("name"):
                payload["name"] = current["name"]
        if item_id is not None:
            payload["item_id"] = item_id
        if name is not None:
            payload["name"] = name
        if amount is not None:
            payload["amount"] = amount
        if description is not None:
            payload["description"] = description
        if position is not None:
            payload["position"] = position
        if is_equipped is not None:
            payload["is_equipped"] = is_equipped
        if is_hidden is not None:
            payload["visibility_id"] = 2 if is_hidden else 1
        try:
            resp = self.client._request(
                "PATCH",
                f"entities/{entity_id}/inventory/{inventory_id}",
                json=payload,
            )
            return self._inventory_to_dict(resp.get("data") or {})
        except Exception as e:
            logger.error(
                f"update_inventory failed (entity={entity_id}, "
                f"row={inventory_id}): {e}"
            )
            raise

    def delete_inventory(self, entity_id: int, inventory_id: int) -> bool:
        try:
            self.client._request(
                "DELETE", f"entities/{entity_id}/inventory/{inventory_id}"
            )
            return True
        except Exception as e:
            logger.error(
                f"delete_inventory failed (entity={entity_id}, "
                f"row={inventory_id}): {e}"
            )
            raise

    @staticmethod
    def _inventory_to_dict(raw: dict[str, Any]) -> InventoryData:
        visibility_id = raw.get("visibility_id")
        return {
            "id": raw.get("id"),
            "entity_id": raw.get("entity_id"),
            "item_id": raw.get("item_id"),
            "name": raw.get("name"),
            "amount": raw.get("amount", 1) or 1,
            "description": raw.get("description"),
            "position": raw.get("position"),
            "is_equipped": bool(raw.get("is_equipped", False)),
            "is_hidden": visibility_id == 2,
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
        }

    # =========================================================================
    # Organisation members (Phase E)
    # =========================================================================
    #
    # Note: the URL uses the organisation's TYPE-specific id, and both
    # organisation_id and character_id in the payload are type-specific IDs.

    def list_organisation_members(
        self, organisation_id: int
    ) -> list[OrganisationMemberData]:
        try:
            resp = self.client._request(
                "GET",
                f"organisations/{organisation_id}/organisation_members",
            )
            return [
                self._org_member_to_dict(r) for r in resp.get("data", [])
            ]
        except Exception as e:
            logger.error(
                f"list_organisation_members failed for org "
                f"{organisation_id}: {e}"
            )
            raise

    def create_organisation_member(
        self,
        organisation_id: int,
        character_id: int,
        role: str | None = None,
        is_hidden: bool | None = None,
        parent_id: int | None = None,
        status_id: int | None = None,
        pin_id: int | None = None,
    ) -> OrganisationMemberData:
        payload: dict[str, Any] = {
            "organisation_id": organisation_id,
            "character_id": character_id,
        }
        if role is not None:
            payload["role"] = role
        if is_hidden is not None:
            payload["is_private"] = is_hidden
        if parent_id is not None:
            payload["parent_id"] = parent_id
        if status_id is not None:
            payload["status_id"] = status_id
        if pin_id is not None:
            payload["pin_id"] = pin_id
        try:
            resp = self.client._request(
                "POST",
                f"organisations/{organisation_id}/organisation_members",
                json=payload,
            )
            return self._org_member_to_dict(resp.get("data") or {})
        except Exception as e:
            logger.error(
                f"create_organisation_member failed (org={organisation_id}, "
                f"char={character_id}): {e}"
            )
            raise

    def update_organisation_member(
        self,
        organisation_id: int,
        member_id: int,
        character_id: int | None = None,
        role: str | None = None,
        is_hidden: bool | None = None,
        parent_id: int | None = None,
        status_id: int | None = None,
        pin_id: int | None = None,
    ) -> OrganisationMemberData:
        payload: dict[str, Any] = {}
        if character_id is not None:
            payload["character_id"] = character_id
        if role is not None:
            payload["role"] = role
        if is_hidden is not None:
            payload["is_private"] = is_hidden
        if parent_id is not None:
            payload["parent_id"] = parent_id
        if status_id is not None:
            payload["status_id"] = status_id
        if pin_id is not None:
            payload["pin_id"] = pin_id
        if not payload:
            raise ValueError(
                "update_organisation_member needs at least one field to update"
            )
        try:
            resp = self.client._request(
                "PATCH",
                f"organisations/{organisation_id}/organisation_members/{member_id}",
                json=payload,
            )
            return self._org_member_to_dict(resp.get("data") or {})
        except Exception as e:
            logger.error(
                f"update_organisation_member failed (org={organisation_id}, "
                f"row={member_id}): {e}"
            )
            raise

    def delete_organisation_member(
        self, organisation_id: int, member_id: int
    ) -> bool:
        try:
            self.client._request(
                "DELETE",
                f"organisations/{organisation_id}/organisation_members/{member_id}",
            )
            return True
        except Exception as e:
            logger.error(
                f"delete_organisation_member failed (org={organisation_id}, "
                f"row={member_id}): {e}"
            )
            raise

    @staticmethod
    def _org_member_to_dict(raw: dict[str, Any]) -> OrganisationMemberData:
        return {
            "id": raw.get("id"),
            "organisation_id": raw.get("organisation_id"),
            "character_id": raw.get("character_id"),
            "role": raw.get("role"),
            "is_hidden": bool(raw.get("is_private", False)),
            "parent_id": raw.get("parent_id"),
            "status_id": raw.get("status_id"),
            "pin_id": raw.get("pin_id"),
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
        }

    # =========================================================================
    # Quest elements (Phase E)
    # =========================================================================
    #
    # The URL uses the quest's TYPE-specific id.

    def list_quest_elements(self, quest_id: int) -> list[QuestElementData]:
        try:
            resp = self.client._request(
                "GET", f"quests/{quest_id}/quest_elements"
            )
            return [
                self._quest_element_to_dict(r) for r in resp.get("data", [])
            ]
        except Exception as e:
            logger.error(
                f"list_quest_elements failed for quest {quest_id}: {e}"
            )
            raise

    def create_quest_element(
        self,
        quest_id: int,
        entity_id: int | None = None,
        name: str | None = None,
        role: str | None = None,
        entry: str | None = None,
        colour: str | None = None,
        is_hidden: bool | None = None,
    ) -> QuestElementData:
        if entity_id is None and not name:
            raise ValueError(
                "create_quest_element needs either entity_id or name"
            )
        payload: dict[str, Any] = {}
        if entity_id is not None:
            payload["entity_id"] = entity_id
        if name is not None:
            payload["name"] = name
        if role is not None:
            payload["role"] = role
        if entry is not None:
            payload["entry"] = self.converter.markdown_to_html(entry)
        if colour is not None:
            payload["colour"] = colour
        if is_hidden is not None:
            payload["visibility_id"] = 2 if is_hidden else 1
        try:
            resp = self.client._request(
                "POST", f"quests/{quest_id}/quest_elements", json=payload
            )
            return self._quest_element_to_dict(resp.get("data") or {})
        except Exception as e:
            logger.error(
                f"create_quest_element failed for quest {quest_id}: {e}"
            )
            raise

    def update_quest_element(
        self,
        quest_id: int,
        element_id: int,
        entity_id: int | None = None,
        name: str | None = None,
        role: str | None = None,
        entry: str | None = None,
        colour: str | None = None,
        is_hidden: bool | None = None,
    ) -> QuestElementData:
        """Update a quest_element.

        Kanka's PATCH requires at least one of ``entity_id`` or ``name``. If
        neither is supplied we fetch the current row so partial updates work.
        """
        payload: dict[str, Any] = {}
        if entity_id is None and name is None:
            current = next(
                (
                    r
                    for r in self.list_quest_elements(quest_id)
                    if r.get("id") == element_id
                ),
                None,
            )
            if current is None:
                raise ValueError(
                    f"quest_element {element_id} not found on quest {quest_id}"
                )
            if current.get("entity_id") is not None:
                payload["entity_id"] = current["entity_id"]
            elif current.get("name"):
                payload["name"] = current["name"]
        if entity_id is not None:
            payload["entity_id"] = entity_id
        if name is not None:
            payload["name"] = name
        if role is not None:
            payload["role"] = role
        if entry is not None:
            payload["entry"] = self.converter.markdown_to_html(entry)
        if colour is not None:
            payload["colour"] = colour
        if is_hidden is not None:
            payload["visibility_id"] = 2 if is_hidden else 1
        try:
            resp = self.client._request(
                "PATCH",
                f"quests/{quest_id}/quest_elements/{element_id}",
                json=payload,
            )
            return self._quest_element_to_dict(resp.get("data") or {})
        except Exception as e:
            logger.error(
                f"update_quest_element failed (quest={quest_id}, "
                f"element={element_id}): {e}"
            )
            raise

    def delete_quest_element(self, quest_id: int, element_id: int) -> bool:
        try:
            self.client._request(
                "DELETE", f"quests/{quest_id}/quest_elements/{element_id}"
            )
            return True
        except Exception as e:
            logger.error(
                f"delete_quest_element failed (quest={quest_id}, "
                f"element={element_id}): {e}"
            )
            raise

    def _quest_element_to_dict(self, raw: dict[str, Any]) -> QuestElementData:
        visibility_id = raw.get("visibility_id")
        entry_html = raw.get("entry")
        return {
            "id": raw.get("id"),
            "entity_id": raw.get("entity_id"),
            "name": raw.get("name"),
            "role": raw.get("role"),
            "entry": (
                self.converter.html_to_markdown(entry_html)
                if entry_html
                else None
            ),
            "colour": raw.get("colour"),
            "is_hidden": visibility_id == 2,
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
        }

    # =========================================================================
    # Calendar weather (Phase F)
    # =========================================================================
    #
    # Endpoint URL uses the calendar's TYPE-specific id.

    def list_calendar_weather(
        self, calendar_id: int
    ) -> list[CalendarWeatherData]:
        try:
            resp = self.client._request(
                "GET", f"calendars/{calendar_id}/calendar_weather"
            )
            return [
                self._calendar_weather_to_dict(r)
                for r in resp.get("data", [])
            ]
        except Exception as e:
            logger.error(
                f"list_calendar_weather failed for calendar {calendar_id}: {e}"
            )
            raise

    def create_calendar_weather(
        self,
        calendar_id: int,
        day: int,
        month: int,
        year: int,
        weather: str | None = None,
        temperature: str | None = None,
        is_hidden: bool | None = None,
    ) -> CalendarWeatherData:
        payload: dict[str, Any] = {
            "day": day,
            "month": month,
            "year": year,
        }
        if weather is not None:
            payload["weather"] = weather
        if temperature is not None:
            payload["temperature"] = temperature
        if is_hidden is not None:
            payload["visibility_id"] = 2 if is_hidden else 1
        try:
            resp = self.client._request(
                "POST",
                f"calendars/{calendar_id}/calendar_weather",
                json=payload,
            )
            return self._calendar_weather_to_dict(resp.get("data") or {})
        except Exception as e:
            logger.error(
                f"create_calendar_weather failed (calendar={calendar_id}): {e}"
            )
            raise

    def update_calendar_weather(
        self,
        calendar_id: int,
        weather_id: int,
        day: int | None = None,
        month: int | None = None,
        year: int | None = None,
        weather: str | None = None,
        temperature: str | None = None,
        is_hidden: bool | None = None,
    ) -> CalendarWeatherData:
        """Update a calendar weather entry.

        Kanka's PATCH requires ``day``, ``month``, ``year``, and ``weather``
        to be present. We auto-fetch missing identity fields from the current
        row so partial updates work.
        """
        need_fetch = (
            day is None
            or month is None
            or year is None
            or weather is None
        )
        current: CalendarWeatherData | None = None
        if need_fetch:
            current = next(
                (
                    r
                    for r in self.list_calendar_weather(calendar_id)
                    if r.get("id") == weather_id
                ),
                None,
            )
            if current is None:
                raise ValueError(
                    f"calendar_weather {weather_id} not found on calendar "
                    f"{calendar_id}"
                )
        payload: dict[str, Any] = {}
        payload["day"] = day if day is not None else current["day"]  # type: ignore[index]
        payload["month"] = month if month is not None else current["month"]  # type: ignore[index]
        payload["year"] = year if year is not None else current["year"]  # type: ignore[index]
        payload["weather"] = (
            weather if weather is not None else current.get("weather") or ""  # type: ignore[union-attr]
        )
        if temperature is not None:
            payload["temperature"] = temperature
        if is_hidden is not None:
            payload["visibility_id"] = 2 if is_hidden else 1
        try:
            resp = self.client._request(
                "PATCH",
                f"calendars/{calendar_id}/calendar_weather/{weather_id}",
                json=payload,
            )
            return self._calendar_weather_to_dict(resp.get("data") or {})
        except Exception as e:
            logger.error(
                f"update_calendar_weather failed (calendar={calendar_id}, "
                f"row={weather_id}): {e}"
            )
            raise

    def delete_calendar_weather(
        self, calendar_id: int, weather_id: int
    ) -> bool:
        try:
            self.client._request(
                "DELETE",
                f"calendars/{calendar_id}/calendar_weather/{weather_id}",
            )
            return True
        except Exception as e:
            logger.error(
                f"delete_calendar_weather failed (calendar={calendar_id}, "
                f"row={weather_id}): {e}"
            )
            raise

    @staticmethod
    def _calendar_weather_to_dict(raw: dict[str, Any]) -> CalendarWeatherData:
        visibility_id = raw.get("visibility_id")
        return {
            "id": raw.get("id"),
            "calendar_id": raw.get("calendar_id"),
            "day": raw.get("day", 0) or 0,
            "month": raw.get("month", 0) or 0,
            "year": raw.get("year", 0) or 0,
            "weather": raw.get("weather"),
            "temperature": raw.get("temperature"),
            "is_hidden": visibility_id == 2,
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
        }

    # =========================================================================
    # Timeline eras (Phase F)
    # =========================================================================
    #
    # URL uses the timeline's TYPE-specific id.

    def list_timeline_eras(self, timeline_id: int) -> list[TimelineEraData]:
        try:
            resp = self.client._request(
                "GET", f"timelines/{timeline_id}/timeline_eras"
            )
            return [
                self._timeline_era_to_dict(r) for r in resp.get("data", [])
            ]
        except Exception as e:
            logger.error(
                f"list_timeline_eras failed for timeline {timeline_id}: {e}"
            )
            raise

    def create_timeline_era(
        self,
        timeline_id: int,
        name: str,
        abbreviation: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
        entry: str | None = None,
        position: int | None = None,
        is_collapsed: bool | None = None,
    ) -> TimelineEraData:
        payload: dict[str, Any] = {"name": name}
        if abbreviation is not None:
            payload["abbreviation"] = abbreviation
        if start_year is not None:
            payload["start_year"] = start_year
        if end_year is not None:
            payload["end_year"] = end_year
        if entry is not None:
            payload["entry"] = self.converter.markdown_to_html(entry)
        if position is not None:
            payload["position"] = position
        if is_collapsed is not None:
            payload["is_collapsed"] = is_collapsed
        try:
            resp = self.client._request(
                "POST",
                f"timelines/{timeline_id}/timeline_eras",
                json=payload,
            )
            return self._timeline_era_to_dict(resp.get("data") or {})
        except Exception as e:
            logger.error(
                f"create_timeline_era failed (timeline={timeline_id}): {e}"
            )
            raise

    def update_timeline_era(
        self,
        timeline_id: int,
        era_id: int,
        name: str | None = None,
        abbreviation: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
        entry: str | None = None,
        position: int | None = None,
        is_collapsed: bool | None = None,
    ) -> TimelineEraData:
        """Update a timeline era.

        Kanka's PATCH requires ``name`` — if the caller doesn't supply it,
        we fetch the current era so partial updates work.
        """
        payload: dict[str, Any] = {}
        if name is None:
            current = next(
                (
                    r
                    for r in self.list_timeline_eras(timeline_id)
                    if r.get("id") == era_id
                ),
                None,
            )
            if current is None:
                raise ValueError(
                    f"timeline era {era_id} not found on timeline {timeline_id}"
                )
            payload["name"] = current.get("name") or ""
        else:
            payload["name"] = name
        if abbreviation is not None:
            payload["abbreviation"] = abbreviation
        if start_year is not None:
            payload["start_year"] = start_year
        if end_year is not None:
            payload["end_year"] = end_year
        if entry is not None:
            payload["entry"] = self.converter.markdown_to_html(entry)
        if position is not None:
            payload["position"] = position
        if is_collapsed is not None:
            payload["is_collapsed"] = is_collapsed
        try:
            resp = self.client._request(
                "PATCH",
                f"timelines/{timeline_id}/timeline_eras/{era_id}",
                json=payload,
            )
            return self._timeline_era_to_dict(resp.get("data") or {})
        except Exception as e:
            logger.error(
                f"update_timeline_era failed (timeline={timeline_id}, "
                f"era={era_id}): {e}"
            )
            raise

    def delete_timeline_era(self, timeline_id: int, era_id: int) -> bool:
        try:
            self.client._request(
                "DELETE", f"timelines/{timeline_id}/timeline_eras/{era_id}"
            )
            return True
        except Exception as e:
            logger.error(
                f"delete_timeline_era failed (timeline={timeline_id}, "
                f"era={era_id}): {e}"
            )
            raise

    def _timeline_era_to_dict(self, raw: dict[str, Any]) -> TimelineEraData:
        entry_html = raw.get("entry")
        return {
            "id": raw.get("id"),
            "name": raw.get("name", ""),
            "abbreviation": raw.get("abbreviation"),
            "start_year": raw.get("start_year"),
            "end_year": raw.get("end_year"),
            "entry": (
                self.converter.html_to_markdown(entry_html)
                if entry_html
                else None
            ),
            "position": raw.get("position", 0) or 0,
            "is_collapsed": bool(raw.get("is_collapsed", False)),
            "elements": raw.get("elements", []),
        }

    # =========================================================================
    # Timeline elements (Phase F)
    # =========================================================================
    #
    # URL uses the timeline's TYPE-specific id.

    def list_timeline_elements(
        self, timeline_id: int
    ) -> list[TimelineElementData]:
        try:
            resp = self.client._request(
                "GET", f"timelines/{timeline_id}/timeline_elements"
            )
            return [
                self._timeline_element_to_dict(r)
                for r in resp.get("data", [])
            ]
        except Exception as e:
            logger.error(
                f"list_timeline_elements failed for timeline "
                f"{timeline_id}: {e}"
            )
            raise

    def create_timeline_element(
        self,
        timeline_id: int,
        era_id: int,
        name: str | None = None,
        entity_id: int | None = None,
        date: str | None = None,
        entry: str | None = None,
        colour: str | None = None,
        position: int | None = None,
        icon: str | None = None,
        is_collapsed: bool | None = None,
        is_hidden: bool | None = None,
        use_entity_entry: bool | None = None,
    ) -> TimelineElementData:
        if entity_id is None and not name:
            raise ValueError(
                "create_timeline_element needs entity_id or name"
            )
        payload: dict[str, Any] = {"era_id": era_id}
        if entity_id is not None:
            payload["entity_id"] = entity_id
        if name is not None:
            payload["name"] = name
        if date is not None:
            payload["date"] = date
        if entry is not None:
            payload["entry"] = self.converter.markdown_to_html(entry)
        if colour is not None:
            payload["colour"] = colour
        if position is not None:
            payload["position"] = position
        if icon is not None:
            payload["icon"] = icon
        if is_collapsed is not None:
            payload["is_collapsed"] = is_collapsed
        if is_hidden is not None:
            payload["visibility_id"] = 2 if is_hidden else 1
        if use_entity_entry is not None:
            payload["use_entity_entry"] = use_entity_entry
        try:
            resp = self.client._request(
                "POST",
                f"timelines/{timeline_id}/timeline_elements",
                json=payload,
            )
            return self._timeline_element_to_dict(resp.get("data") or {})
        except Exception as e:
            logger.error(
                f"create_timeline_element failed (timeline={timeline_id}, "
                f"era={era_id}): {e}"
            )
            raise

    def update_timeline_element(
        self,
        timeline_id: int,
        element_id: int,
        era_id: int | None = None,
        entity_id: int | None = None,
        name: str | None = None,
        date: str | None = None,
        entry: str | None = None,
        colour: str | None = None,
        position: int | None = None,
        icon: str | None = None,
        is_collapsed: bool | None = None,
        is_hidden: bool | None = None,
        use_entity_entry: bool | None = None,
    ) -> TimelineElementData:
        """Update a timeline element.

        Kanka's PATCH requires ``era_id`` AND one of ``entity_id`` / ``name``.
        The service auto-fetches the current row for any missing identity
        field so partial updates work.
        """
        need_fetch = (
            era_id is None or (entity_id is None and not name)
        )
        current: TimelineElementData | None = None
        if need_fetch:
            current = next(
                (
                    r
                    for r in self.list_timeline_elements(timeline_id)
                    if r.get("id") == element_id
                ),
                None,
            )
            if current is None:
                raise ValueError(
                    f"timeline element {element_id} not found on timeline "
                    f"{timeline_id}"
                )
        payload: dict[str, Any] = {}
        payload["era_id"] = (
            era_id if era_id is not None else current["era_id"]  # type: ignore[index]
        )
        if entity_id is not None:
            payload["entity_id"] = entity_id
        elif name is None and current is not None:
            # Fill in whichever identity field the row currently has.
            if current.get("entity_id") is not None:
                payload["entity_id"] = current["entity_id"]
            elif current.get("name"):
                payload["name"] = current["name"]
        if name is not None:
            payload["name"] = name
        if date is not None:
            payload["date"] = date
        if entry is not None:
            payload["entry"] = self.converter.markdown_to_html(entry)
        if colour is not None:
            payload["colour"] = colour
        if position is not None:
            payload["position"] = position
        if icon is not None:
            payload["icon"] = icon
        if is_collapsed is not None:
            payload["is_collapsed"] = is_collapsed
        if is_hidden is not None:
            payload["visibility_id"] = 2 if is_hidden else 1
        if use_entity_entry is not None:
            payload["use_entity_entry"] = use_entity_entry
        try:
            resp = self.client._request(
                "PATCH",
                f"timelines/{timeline_id}/timeline_elements/{element_id}",
                json=payload,
            )
            return self._timeline_element_to_dict(resp.get("data") or {})
        except Exception as e:
            logger.error(
                f"update_timeline_element failed (timeline={timeline_id}, "
                f"element={element_id}): {e}"
            )
            raise

    def delete_timeline_element(
        self, timeline_id: int, element_id: int
    ) -> bool:
        try:
            self.client._request(
                "DELETE",
                f"timelines/{timeline_id}/timeline_elements/{element_id}",
            )
            return True
        except Exception as e:
            logger.error(
                f"delete_timeline_element failed (timeline={timeline_id}, "
                f"element={element_id}): {e}"
            )
            raise

    # =========================================================================
    # Meta: campaign, roles, users (Phase I)
    # =========================================================================

    def get_campaign(self) -> CampaignData:
        """Fetch the campaign's metadata.

        The Kanka API roots this at ``campaigns/{campaign_id}``. The
        ``_request`` helper is scoped to that root, so we call ``GET ""``.
        """
        try:
            resp = self.client._request("GET", "")
            return self._campaign_to_dict(resp.get("data") or {})
        except Exception as e:
            logger.error(f"get_campaign failed: {e}")
            raise

    def list_roles(self) -> list[RoleData]:
        """List roles configured on this campaign."""
        try:
            resp = self.client._request("GET", "roles")
            return [self._role_to_dict(r) for r in resp.get("data", [])]
        except Exception as e:
            logger.error(f"list_roles failed: {e}")
            raise

    def list_campaign_users(self) -> list[CampaignUserData]:
        """List users (players + GMs) with access to this campaign."""
        try:
            resp = self.client._request("GET", "users")
            return [self._campaign_user_to_dict(u) for u in resp.get("data", [])]
        except Exception as e:
            logger.error(f"list_campaign_users failed: {e}")
            raise

    def _campaign_to_dict(self, raw: dict[str, Any]) -> CampaignData:
        visibility_id = raw.get("visibility_id")
        raw_desc = raw.get("description_raw") or raw.get("entry")
        return {
            "id": raw.get("id"),
            "name": raw.get("name", ""),
            "slug": raw.get("slug", ""),
            "locale": raw.get("locale"),
            "description": (
                self.converter.html_to_markdown(raw_desc) if raw_desc else None
            ),
            "image": raw.get("image"),
            "image_full": raw.get("image_full"),
            "image_thumb": raw.get("image_thumb"),
            "visibility": raw.get("visibility"),
            "visibility_id": visibility_id,
            "is_hidden": visibility_id == 2,
            "settings": raw.get("settings") or {},
            "ui_settings": raw.get("ui_settings") or {},
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
        }

    @staticmethod
    def _role_to_dict(raw: dict[str, Any]) -> RoleData:
        return {
            "id": raw.get("id"),
            "name": raw.get("name", ""),
            "is_admin": bool(raw.get("is_admin", False)),
        }

    def _campaign_user_to_dict(self, raw: dict[str, Any]) -> CampaignUserData:
        # ``role`` is a list of role dicts on the users endpoint. Normalize
        # both a single dict and a list into ``roles: [...]``.
        role_field = raw.get("role")
        if isinstance(role_field, list):
            roles = [self._role_to_dict(r) for r in role_field]
        elif isinstance(role_field, dict):
            roles = [self._role_to_dict(role_field)]
        else:
            roles = []
        return {
            "id": raw.get("id"),
            "name": raw.get("name", ""),
            "avatar": raw.get("avatar"),
            "roles": roles,
        }

    def _timeline_element_to_dict(
        self, raw: dict[str, Any]
    ) -> TimelineElementData:
        visibility_id = raw.get("visibility_id")
        entry_html = raw.get("entry")
        return {
            "id": raw.get("id"),
            "era_id": raw.get("era_id"),
            "timeline_id": raw.get("timeline_id"),
            "entity_id": raw.get("entity_id"),
            "name": raw.get("name"),
            "entry": (
                self.converter.html_to_markdown(entry_html)
                if entry_html
                else None
            ),
            "date": raw.get("date"),
            "colour": raw.get("colour", "") or "",
            "position": raw.get("position", 0) or 0,
            "icon": raw.get("icon"),
            "is_collapsed": bool(raw.get("is_collapsed", False)),
            "is_hidden": visibility_id == 2,
            "use_entity_entry": bool(raw.get("use_entity_entry", False)),
        }


# Global service instance (initialized on first use)
_service: KankaService | None = None


def get_service() -> KankaService:
    """Get or create the Kanka service instance."""
    global _service
    if _service is None:
        _service = KankaService()
    return _service
