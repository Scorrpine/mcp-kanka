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
    EntityType,
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


# Global service instance (initialized on first use)
_service: KankaService | None = None


def get_service() -> KankaService:
    """Get or create the Kanka service instance."""
    global _service
    if _service is None:
        _service = KankaService()
    return _service
