#!/usr/bin/env python3
"""
Kanka MCP Server

An MCP server that provides tools for interacting with Kanka campaigns.
"""

import asyncio
import logging
import os
from typing import Any

import mcp.server.stdio
import mcp.types as types
from dotenv import load_dotenv
from mcp.server import Server
from pydantic import AnyUrl

from .resources import get_kanka_context
from .tools import (
    handle_check_entity_updates,
    handle_create_attributes,
    handle_create_entities,
    handle_create_entity_abilities,
    handle_create_inventory,
    handle_create_organisation_members,
    handle_create_posts,
    handle_create_quest_elements,
    handle_create_relations,
    handle_delete_attributes,
    handle_delete_entities,
    handle_delete_entity_abilities,
    handle_delete_inventory,
    handle_delete_organisation_members,
    handle_delete_posts,
    handle_delete_quest_elements,
    handle_delete_relations,
    handle_find_entities,
    handle_get_entities,
    handle_list_attributes,
    handle_list_entity_abilities,
    handle_list_inventory,
    handle_list_organisation_members,
    handle_list_quest_elements,
    handle_list_relations,
    handle_update_attributes,
    handle_update_entities,
    handle_update_entity_abilities,
    handle_update_inventory,
    handle_update_organisation_members,
    handle_update_posts,
    handle_update_quest_elements,
    handle_update_relations,
)
from .types import VALID_ATTRIBUTE_TYPES, VALID_ENTITY_TYPES

# JSON-schema enum shared by every tool that accepts an entity_type.
# Keeping this in one place ensures find_entities and create_entities never drift.
_ENTITY_TYPE_ENUM: list[str] = list(VALID_ENTITY_TYPES)
_ATTRIBUTE_TYPE_ENUM: list[str] = list(VALID_ATTRIBUTE_TYPES)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("MCP_LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create the MCP server instance
app: Server[None] = Server("mcp-kanka")


@app.list_resources()  # type: ignore[no-untyped-call, untyped-decorator]
async def list_resources() -> list[types.Resource]:
    """List available resources."""
    return [
        types.Resource(
            uri=AnyUrl("kanka://context"),
            name="Kanka Context",
            description="Information about Kanka's structure and this MCP server's capabilities",
            mimeType="application/json",
        )
    ]


@app.read_resource()  # type: ignore[no-untyped-call, untyped-decorator]
async def read_resource(uri: str) -> str:
    """Read a resource by URI."""
    if uri == "kanka://context":
        return get_kanka_context()
    raise ValueError(f"Unknown resource: {uri}")


@app.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
async def list_tools() -> list[types.Tool]:
    """List available tools."""
    return [
        types.Tool(
            name="find_entities",
            description="Find entities by search and/or filtering",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term (searches names and content)",
                    },
                    "entity_type": {
                        "type": "string",
                        "enum": _ENTITY_TYPE_ENUM,
                        "description": "Entity type to filter by",
                    },
                    "name": {
                        "type": "string",
                        "description": "Filter by name (partial match by default, e.g. 'Test' matches 'Test Character')",
                    },
                    "name_exact": {
                        "type": "boolean",
                        "description": "Use exact matching on name filter (case-insensitive)",
                        "default": False,
                    },
                    "name_fuzzy": {
                        "type": "boolean",
                        "description": "Use fuzzy matching on name filter (typo-tolerant)",
                        "default": False,
                    },
                    "type": {
                        "type": "string",
                        "description": "Filter by Type field (e.g., 'NPC', 'City')",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags (matches entities having ALL specified tags)",
                    },
                    "date_range": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string", "format": "date"},
                            "end": {"type": "string", "format": "date"},
                        },
                        "description": "For filtering journals by date",
                    },
                    "include_full": {
                        "type": "boolean",
                        "description": "Include full entity details",
                        "default": True,
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number for pagination",
                        "default": 1,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Results per page (default 25, max 100, use 0 for all)",
                        "default": 25,
                    },
                    "last_synced": {
                        "type": "string",
                        "description": "ISO 8601 timestamp to get only entities modified after this time",
                    },
                },
            },
        ),
        types.Tool(
            name="create_entities",
            description="Create one or more entities",
            inputSchema={
                "type": "object",
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_type": {
                                    "type": "string",
                                    "enum": _ENTITY_TYPE_ENUM,
                                    "description": "Entity type",
                                },
                                "name": {
                                    "type": "string",
                                    "description": "Entity name",
                                },
                                "type": {
                                    "type": "string",
                                    "description": "The Type field (e.g., 'NPC', 'Player Character')",
                                },
                                "entry": {
                                    "type": "string",
                                    "description": "Description in Markdown format",
                                },
                                "tags": {"type": "array", "items": {"type": "string"}},
                                "is_hidden": {
                                    "type": "boolean",
                                    "description": "If true, hidden from players (admin-only)",
                                },
                            },
                            "required": ["entity_type", "name"],
                        },
                    }
                },
                "required": ["entities"],
            },
        ),
        types.Tool(
            name="update_entities",
            description="Update one or more entities",
            inputSchema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {
                                    "type": "integer",
                                    "description": "Entity ID",
                                },
                                "name": {
                                    "type": "string",
                                    "description": "Entity name (required by Kanka API even if unchanged)",
                                },
                                "type": {
                                    "type": "string",
                                    "description": "The Type field",
                                },
                                "entry": {
                                    "type": "string",
                                    "description": "Content in Markdown format",
                                },
                                "tags": {"type": "array", "items": {"type": "string"}},
                                "is_hidden": {"type": "boolean"},
                                "title": {
                                    "type": "string",
                                    "description": (
                                        "Character title, e.g. 'The Wise'. "
                                        "Characters only; ignored on other types."
                                    ),
                                },
                                "race_ids": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "description": (
                                        "Race TYPE-specific ids (from "
                                        "get_entities' `id` field). Characters "
                                        "only; sets the character's races."
                                    ),
                                },
                            },
                            "required": ["entity_id", "name"],
                        },
                    }
                },
                "required": ["updates"],
            },
        ),
        types.Tool(
            name="get_entities",
            description="Retrieve specific entities by ID with their posts",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Array of entity IDs to retrieve",
                    },
                    "include_posts": {
                        "type": "boolean",
                        "description": "Include posts for each entity",
                        "default": False,
                    },
                },
                "required": ["entity_ids"],
            },
        ),
        types.Tool(
            name="delete_entities",
            description="Delete one or more entities",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Array of entity IDs to delete",
                    }
                },
                "required": ["entity_ids"],
            },
        ),
        types.Tool(
            name="create_posts",
            description="Create posts on entities",
            inputSchema={
                "type": "object",
                "properties": {
                    "posts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {
                                    "type": "integer",
                                    "description": "The entity ID to attach post to",
                                },
                                "name": {"type": "string", "description": "Post title"},
                                "entry": {
                                    "type": "string",
                                    "description": "Post content in Markdown format",
                                },
                                "is_hidden": {
                                    "type": "boolean",
                                    "description": "If true, hidden from players (admin-only)",
                                },
                            },
                            "required": ["entity_id", "name"],
                        },
                    }
                },
                "required": ["posts"],
            },
        ),
        types.Tool(
            name="update_posts",
            description="Update existing posts",
            inputSchema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {
                                    "type": "integer",
                                    "description": "The entity ID",
                                },
                                "post_id": {
                                    "type": "integer",
                                    "description": "The post ID to update",
                                },
                                "name": {
                                    "type": "string",
                                    "description": "Post title (required by API even if unchanged)",
                                },
                                "entry": {
                                    "type": "string",
                                    "description": "Post content in Markdown format",
                                },
                                "is_hidden": {
                                    "type": "boolean",
                                    "description": "If true, hidden from players (admin-only)",
                                },
                            },
                            "required": ["entity_id", "post_id", "name"],
                        },
                    }
                },
                "required": ["updates"],
            },
        ),
        types.Tool(
            name="delete_posts",
            description="Delete posts from entities",
            inputSchema={
                "type": "object",
                "properties": {
                    "deletions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {
                                    "type": "integer",
                                    "description": "The entity ID",
                                },
                                "post_id": {
                                    "type": "integer",
                                    "description": "The post ID to delete",
                                },
                            },
                            "required": ["entity_id", "post_id"],
                        },
                    }
                },
                "required": ["deletions"],
            },
        ),
        types.Tool(
            name="check_entity_updates",
            description="Check which entity_ids have been modified since last sync",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Array of entity IDs to check",
                    },
                    "last_synced": {
                        "type": "string",
                        "description": "ISO 8601 timestamp to check updates since",
                    },
                },
                "required": ["entity_ids", "last_synced"],
            },
        ),
        types.Tool(
            name="list_attributes",
            description=(
                "List all attributes on an entity. Attributes are the key-value "
                "store on any entity (HP, AC, stats, currency, damage counters, "
                "etc.). Types: standard (text), number, checkbox, section (header), "
                "random (dice expression)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "integer",
                        "description": "The entity_id whose attributes to list",
                    },
                },
                "required": ["entity_id"],
            },
        ),
        types.Tool(
            name="create_attributes",
            description="Create one or more attributes on entities",
            inputSchema={
                "type": "object",
                "properties": {
                    "attributes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {
                                    "type": "integer",
                                    "description": "Entity to attach the attribute to",
                                },
                                "name": {
                                    "type": "string",
                                    "description": "Attribute name (e.g., 'HP', 'AC')",
                                },
                                "value": {
                                    "type": "string",
                                    "description": (
                                        "Attribute value. For checkbox use '1'/'0'; "
                                        "for section leave omitted; for random use "
                                        "a dice expression like '1d20+5'."
                                    ),
                                },
                                "type": {
                                    "type": "string",
                                    "enum": _ATTRIBUTE_TYPE_ENUM,
                                    "description": (
                                        "Attribute type. Defaults to 'standard'."
                                    ),
                                },
                                "is_pinned": {
                                    "type": "boolean",
                                    "description": "Pin at top of attribute list",
                                },
                                "is_private": {
                                    "type": "boolean",
                                    "description": "Hidden from players (admin-only)",
                                },
                                "is_star": {
                                    "type": "boolean",
                                    "description": "Mark as important (starred)",
                                },
                                "default_order": {
                                    "type": "integer",
                                    "description": "Sort order among attributes",
                                },
                                "api_key": {
                                    "type": "string",
                                    "description": (
                                        "Optional stable key for programmatic lookup"
                                    ),
                                },
                            },
                            "required": ["entity_id", "name"],
                        },
                    },
                },
                "required": ["attributes"],
            },
        ),
        types.Tool(
            name="update_attributes",
            description="Update existing attributes on entities",
            inputSchema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {
                                    "type": "integer",
                                    "description": "Entity holding the attribute",
                                },
                                "attribute_id": {
                                    "type": "integer",
                                    "description": "The attribute ID to update",
                                },
                                "name": {"type": "string"},
                                "value": {"type": "string"},
                                "type": {
                                    "type": "string",
                                    "enum": _ATTRIBUTE_TYPE_ENUM,
                                },
                                "is_pinned": {"type": "boolean"},
                                "is_private": {"type": "boolean"},
                                "is_star": {"type": "boolean"},
                                "default_order": {"type": "integer"},
                                "api_key": {"type": "string"},
                            },
                            "required": ["entity_id", "attribute_id"],
                        },
                    },
                },
                "required": ["updates"],
            },
        ),
        types.Tool(
            name="delete_attributes",
            description="Delete attributes from entities",
            inputSchema={
                "type": "object",
                "properties": {
                    "deletions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {"type": "integer"},
                                "attribute_id": {"type": "integer"},
                            },
                            "required": ["entity_id", "attribute_id"],
                        },
                    },
                },
                "required": ["deletions"],
            },
        ),
        types.Tool(
            name="list_relations",
            description=(
                "List all relations owned by an entity. Relations link entity "
                "to entity: 'friend', 'father', 'rival', 'employer', etc. Kanka "
                "supports two-way relations (mirrored on the target). Each "
                "returned relation has: id, owner_id, target_id, relation (label), "
                "attitude (-100..100), colour, is_star, is_pinned, is_hidden, "
                "is_two_way (derived), and mirror_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "integer",
                        "description": "The owner entity_id whose relations to list",
                    },
                },
                "required": ["entity_id"],
            },
        ),
        types.Tool(
            name="create_relations",
            description=(
                "Create one or more entity-to-entity relations. Setting "
                "two_way=true creates a mirror on the target side."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "relations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "owner_id": {
                                    "type": "integer",
                                    "description": "Source entity_id",
                                },
                                "target_id": {
                                    "type": "integer",
                                    "description": "Destination entity_id",
                                },
                                "relation": {
                                    "type": "string",
                                    "description": (
                                        "Free-text label, e.g. 'friend', "
                                        "'father', 'rival'"
                                    ),
                                },
                                "attitude": {
                                    "type": "integer",
                                    "description": (
                                        "Numeric attitude score, typically "
                                        "-100 (hostile) to 100 (devoted)"
                                    ),
                                },
                                "colour": {
                                    "type": "string",
                                    "description": (
                                        "Hex colour string for the relation link"
                                    ),
                                },
                                "is_star": {"type": "boolean"},
                                "is_pinned": {"type": "boolean"},
                                "is_hidden": {
                                    "type": "boolean",
                                    "description": "Admin-only visibility",
                                },
                                "two_way": {
                                    "type": "boolean",
                                    "description": (
                                        "Also create the mirror relation on "
                                        "the target's side"
                                    ),
                                },
                            },
                            "required": ["owner_id", "target_id", "relation"],
                        },
                    },
                },
                "required": ["relations"],
            },
        ),
        types.Tool(
            name="update_relations",
            description="Update existing relations",
            inputSchema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {
                                    "type": "integer",
                                    "description": "Owner entity_id (URL path)",
                                },
                                "relation_id": {
                                    "type": "integer",
                                    "description": "The relation ID to update",
                                },
                                "owner_id": {"type": "integer"},
                                "target_id": {"type": "integer"},
                                "relation": {"type": "string"},
                                "attitude": {"type": "integer"},
                                "colour": {"type": "string"},
                                "is_star": {"type": "boolean"},
                                "is_pinned": {"type": "boolean"},
                                "is_hidden": {"type": "boolean"},
                            },
                            "required": ["entity_id", "relation_id"],
                        },
                    },
                },
                "required": ["updates"],
            },
        ),
        types.Tool(
            name="delete_relations",
            description=(
                "Delete relations. Note: Kanka only removes the specified row; "
                "the mirror on the target side of a two-way relation is NOT "
                "auto-deleted. To fully remove both sides, delete both "
                "relation_ids."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "deletions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {"type": "integer"},
                                "relation_id": {"type": "integer"},
                            },
                            "required": ["entity_id", "relation_id"],
                        },
                    },
                },
                "required": ["deletions"],
            },
        ),
        # =============================================================
        # Phase E: entity_abilities
        # =============================================================
        types.Tool(
            name="list_entity_abilities",
            description=(
                "List all ability attachments on an entity. Each row links "
                "the entity to an ability entity and tracks charges + notes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {"type": "integer"},
                },
                "required": ["entity_id"],
            },
        ),
        types.Tool(
            name="create_entity_abilities",
            description=(
                "Attach ability entities to characters/creatures. Note: "
                "`ability_id` is the ability's TYPE-specific id (from "
                "get_entities' `id` field), not the entity_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {"type": "integer"},
                                "ability_id": {
                                    "type": "integer",
                                    "description": (
                                        "Type-specific id of the ability"
                                    ),
                                },
                                "charges": {"type": "integer"},
                                "note": {"type": "string"},
                                "position": {"type": "integer"},
                                "is_hidden": {"type": "boolean"},
                            },
                            "required": ["entity_id", "ability_id"],
                        },
                    },
                },
                "required": ["items"],
            },
        ),
        types.Tool(
            name="update_entity_abilities",
            description="Update existing entity_ability rows",
            inputSchema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {"type": "integer"},
                                "entity_ability_id": {"type": "integer"},
                                "ability_id": {"type": "integer"},
                                "charges": {"type": "integer"},
                                "note": {"type": "string"},
                                "position": {"type": "integer"},
                                "is_hidden": {"type": "boolean"},
                            },
                            "required": ["entity_id", "entity_ability_id"],
                        },
                    },
                },
                "required": ["updates"],
            },
        ),
        types.Tool(
            name="delete_entity_abilities",
            description="Remove ability attachments from entities",
            inputSchema={
                "type": "object",
                "properties": {
                    "deletions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {"type": "integer"},
                                "entity_ability_id": {"type": "integer"},
                            },
                            "required": ["entity_id", "entity_ability_id"],
                        },
                    },
                },
                "required": ["deletions"],
            },
        ),
        # =============================================================
        # Phase E: inventory
        # =============================================================
        types.Tool(
            name="list_inventory",
            description="List all inventory rows for an entity",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {"type": "integer"},
                },
                "required": ["entity_id"],
            },
        ),
        types.Tool(
            name="create_inventory",
            description=(
                "Add inventory rows to an entity. Each row either links to a "
                "Kanka Item (via item_id, TYPE-specific id) or is a freeform "
                "name string. At least one of item_id / name is required."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {"type": "integer"},
                                "item_id": {
                                    "type": "integer",
                                    "description": (
                                        "Kanka Item's TYPE-specific id (nullable)"
                                    ),
                                },
                                "name": {
                                    "type": "string",
                                    "description": (
                                        "Freeform name if no item_id"
                                    ),
                                },
                                "amount": {"type": "integer"},
                                "description": {"type": "string"},
                                "position": {
                                    "type": "string",
                                    "description": (
                                        "Freeform location: 'backpack', "
                                        "'belt', 'left hand', etc."
                                    ),
                                },
                                "is_equipped": {"type": "boolean"},
                                "is_hidden": {"type": "boolean"},
                                "copy_item_entry": {
                                    "type": "boolean",
                                    "description": (
                                        "Copy the Item entity's entry as "
                                        "the description"
                                    ),
                                },
                            },
                            "required": ["entity_id"],
                        },
                    },
                },
                "required": ["items"],
            },
        ),
        types.Tool(
            name="update_inventory",
            description="Update existing inventory rows",
            inputSchema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {"type": "integer"},
                                "inventory_id": {"type": "integer"},
                                "item_id": {"type": "integer"},
                                "name": {"type": "string"},
                                "amount": {"type": "integer"},
                                "description": {"type": "string"},
                                "position": {"type": "string"},
                                "is_equipped": {"type": "boolean"},
                                "is_hidden": {"type": "boolean"},
                            },
                            "required": ["entity_id", "inventory_id"],
                        },
                    },
                },
                "required": ["updates"],
            },
        ),
        types.Tool(
            name="delete_inventory",
            description="Remove inventory rows",
            inputSchema={
                "type": "object",
                "properties": {
                    "deletions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {"type": "integer"},
                                "inventory_id": {"type": "integer"},
                            },
                            "required": ["entity_id", "inventory_id"],
                        },
                    },
                },
                "required": ["deletions"],
            },
        ),
        # =============================================================
        # Phase E: organisation_members
        # =============================================================
        types.Tool(
            name="list_organisation_members",
            description=(
                "List members of an organisation. Note: organisation_id is "
                "the organisation's TYPE-specific id (from get_entities' "
                "`id` field), not entity_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "organisation_id": {"type": "integer"},
                },
                "required": ["organisation_id"],
            },
        ),
        types.Tool(
            name="create_organisation_members",
            description=(
                "Add characters as members of an organisation. Both "
                "organisation_id and character_id are TYPE-specific ids."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "organisation_id": {"type": "integer"},
                                "character_id": {"type": "integer"},
                                "role": {"type": "string"},
                                "is_hidden": {"type": "boolean"},
                                "parent_id": {
                                    "type": "integer",
                                    "description": (
                                        "For hierarchical org structures"
                                    ),
                                },
                                "status_id": {"type": "integer"},
                                "pin_id": {"type": "integer"},
                            },
                            "required": ["organisation_id", "character_id"],
                        },
                    },
                },
                "required": ["items"],
            },
        ),
        types.Tool(
            name="update_organisation_members",
            description="Update existing organisation membership rows",
            inputSchema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "organisation_id": {"type": "integer"},
                                "member_id": {"type": "integer"},
                                "character_id": {"type": "integer"},
                                "role": {"type": "string"},
                                "is_hidden": {"type": "boolean"},
                                "parent_id": {"type": "integer"},
                                "status_id": {"type": "integer"},
                                "pin_id": {"type": "integer"},
                            },
                            "required": ["organisation_id", "member_id"],
                        },
                    },
                },
                "required": ["updates"],
            },
        ),
        types.Tool(
            name="delete_organisation_members",
            description="Remove organisation memberships",
            inputSchema={
                "type": "object",
                "properties": {
                    "deletions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "organisation_id": {"type": "integer"},
                                "member_id": {"type": "integer"},
                            },
                            "required": ["organisation_id", "member_id"],
                        },
                    },
                },
                "required": ["deletions"],
            },
        ),
        # =============================================================
        # Phase E: quest_elements
        # =============================================================
        types.Tool(
            name="list_quest_elements",
            description=(
                "List elements referenced from a quest. Note: quest_id is "
                "the quest's TYPE-specific id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "quest_id": {"type": "integer"},
                },
                "required": ["quest_id"],
            },
        ),
        types.Tool(
            name="create_quest_elements",
            description=(
                "Add elements to a quest (link entities or add freeform "
                "named elements). Either entity_id or name is required."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "quest_id": {"type": "integer"},
                                "entity_id": {
                                    "type": "integer",
                                    "description": "Linked entity (nullable)",
                                },
                                "name": {
                                    "type": "string",
                                    "description": (
                                        "Display name (freeform if no entity)"
                                    ),
                                },
                                "role": {"type": "string"},
                                "entry": {
                                    "type": "string",
                                    "description": (
                                        "Element description in Markdown"
                                    ),
                                },
                                "colour": {"type": "string"},
                                "is_hidden": {"type": "boolean"},
                            },
                            "required": ["quest_id"],
                        },
                    },
                },
                "required": ["items"],
            },
        ),
        types.Tool(
            name="update_quest_elements",
            description="Update existing quest elements",
            inputSchema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "quest_id": {"type": "integer"},
                                "element_id": {"type": "integer"},
                                "entity_id": {"type": "integer"},
                                "name": {"type": "string"},
                                "role": {"type": "string"},
                                "entry": {"type": "string"},
                                "colour": {"type": "string"},
                                "is_hidden": {"type": "boolean"},
                            },
                            "required": ["quest_id", "element_id"],
                        },
                    },
                },
                "required": ["updates"],
            },
        ),
        types.Tool(
            name="delete_quest_elements",
            description="Remove elements from a quest",
            inputSchema={
                "type": "object",
                "properties": {
                    "deletions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "quest_id": {"type": "integer"},
                                "element_id": {"type": "integer"},
                            },
                            "required": ["quest_id", "element_id"],
                        },
                    },
                },
                "required": ["deletions"],
            },
        ),
    ]


@app.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Handle tool calls."""
    logger.info(f"Tool called: {name} with arguments: {arguments}")

    try:
        result: Any
        if name == "find_entities":
            result = await handle_find_entities(**arguments)
        elif name == "create_entities":
            result = await handle_create_entities(**arguments)
        elif name == "update_entities":
            result = await handle_update_entities(**arguments)
        elif name == "get_entities":
            result = await handle_get_entities(**arguments)
        elif name == "delete_entities":
            result = await handle_delete_entities(**arguments)
        elif name == "create_posts":
            result = await handle_create_posts(**arguments)
        elif name == "update_posts":
            result = await handle_update_posts(**arguments)
        elif name == "delete_posts":
            result = await handle_delete_posts(**arguments)
        elif name == "check_entity_updates":
            result = await handle_check_entity_updates(**arguments)
        elif name == "list_attributes":
            result = await handle_list_attributes(**arguments)
        elif name == "create_attributes":
            result = await handle_create_attributes(**arguments)
        elif name == "update_attributes":
            result = await handle_update_attributes(**arguments)
        elif name == "delete_attributes":
            result = await handle_delete_attributes(**arguments)
        elif name == "list_relations":
            result = await handle_list_relations(**arguments)
        elif name == "create_relations":
            result = await handle_create_relations(**arguments)
        elif name == "update_relations":
            result = await handle_update_relations(**arguments)
        elif name == "delete_relations":
            result = await handle_delete_relations(**arguments)
        # Phase E: sub-resources
        elif name == "list_entity_abilities":
            result = await handle_list_entity_abilities(**arguments)
        elif name == "create_entity_abilities":
            result = await handle_create_entity_abilities(**arguments)
        elif name == "update_entity_abilities":
            result = await handle_update_entity_abilities(**arguments)
        elif name == "delete_entity_abilities":
            result = await handle_delete_entity_abilities(**arguments)
        elif name == "list_inventory":
            result = await handle_list_inventory(**arguments)
        elif name == "create_inventory":
            result = await handle_create_inventory(**arguments)
        elif name == "update_inventory":
            result = await handle_update_inventory(**arguments)
        elif name == "delete_inventory":
            result = await handle_delete_inventory(**arguments)
        elif name == "list_organisation_members":
            result = await handle_list_organisation_members(**arguments)
        elif name == "create_organisation_members":
            result = await handle_create_organisation_members(**arguments)
        elif name == "update_organisation_members":
            result = await handle_update_organisation_members(**arguments)
        elif name == "delete_organisation_members":
            result = await handle_delete_organisation_members(**arguments)
        elif name == "list_quest_elements":
            result = await handle_list_quest_elements(**arguments)
        elif name == "create_quest_elements":
            result = await handle_create_quest_elements(**arguments)
        elif name == "update_quest_elements":
            result = await handle_update_quest_elements(**arguments)
        elif name == "delete_quest_elements":
            result = await handle_delete_quest_elements(**arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [types.TextContent(type="text", text=str(result))]
    except Exception as e:
        logger.error(f"Error in tool {name}: {str(e)}", exc_info=True)
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]


async def main() -> None:
    """Main entry point for the MCP server."""
    # Validate required environment variables
    if not os.getenv("KANKA_TOKEN"):
        logger.error("KANKA_TOKEN environment variable is required")
        raise ValueError("KANKA_TOKEN environment variable is required")

    if not os.getenv("KANKA_CAMPAIGN_ID"):
        logger.error("KANKA_CAMPAIGN_ID environment variable is required")
        raise ValueError("KANKA_CAMPAIGN_ID environment variable is required")

    logger.info("Starting Kanka MCP server...")

    # Run the server
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
