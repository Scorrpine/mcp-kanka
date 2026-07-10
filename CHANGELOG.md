# Changelog

All notable changes to this fork are documented here. This fork is based on [ervwalter/mcp-kanka](https://github.com/ervwalter/mcp-kanka).

## [2.0.0a3] - 2026-07-10

### Phase C: Attribute CRUD

Adds full CRUD support for Kanka entity attributes: the per-entity key-value store used for HP, AC, ability scores, currency, damage counters, spell slots, etc. This is arguably the biggest RPG-value phase of the fork.

Four new MCP tools:
- `list_attributes(entity_id)` — read all attributes on an entity
- `create_attributes(attributes: [...])` — batch create
- `update_attributes(updates: [...])` — batch update
- `delete_attributes(deletions: [...])` — batch delete

Tool count grows from 9 to 13.

### Attribute types

All 5 Kanka attribute types are supported by string name; the fork translates to the numeric `type_id` under the hood:

| Type | `type_id` | Notes |
|---|---|---|
| `standard` | 1 | Text value. Default when `type` is omitted. |
| `number` | 2 | Numeric value (stored as string). |
| `checkbox` | 3 | Boolean. Send `"1"`/`"0"` or truthy string; response has `value: true`/`false`. |
| `section` | 4 | Header/divider. `value` should be omitted. |
| `random` | 5 | Dice-expression value, e.g. `"1d6+2"`. Kanka parses on display. |

Type-id mapping verified against a live campaign on 2026-07-10.

### Batch semantics

All three write tools accept arrays and return per-item results. A malformed item (missing `entity_id`/`name`/`attribute_id`, invalid type) fails only that item; the rest still execute. Each result contains `success` and `error` for granular feedback.

### Additional attribute fields exposed

- `is_pinned` — pin at top of the entity's attribute list
- `is_private` — admin-only visibility
- `is_star` — mark as important
- `default_order` — sort index
- `api_key` — stable programmatic key
- `parsed` — Kanka's rendered form (read-only, included in list responses)

### Tests

- 23 new tests in `tests/unit/test_attributes.py`: type-id mapping round-trip, payload construction (empty-none, invalid-type rejection, flag pass-through), `_attribute_to_dict` normalization (null/unknown type_id, boolean coercion, checkbox bool value preservation), service HTTP verb correctness (`GET/POST/PATCH/DELETE` and endpoint URLs), batch aggregation with per-item success/failure.
- Full suite: 214 baseline + 23 new = 237 tests passing.
- Live campaign round-trip: created + listed + updated + deleted one attribute of each type (5 total) against a scratch character. Also verified that a batch with 2 malformed items and 5 valid items returns 7 results (5 success + 2 failure) and never short-circuits.

## [2.0.0a2] - 2026-07-10

### Phase B: Extended entity type coverage

Adds 7 Kanka entity types to the MCP surface. All are additive: no existing behavior changes.

- **New types**: `calendar`, `event`, `family`, `item`, `ability`, `timeline`, and `tag` (first-class; `tag` is still accepted as a filter parameter on other entities).
- `EntityType` union grows from 8 to 15 members.
- `find_entities`, `create_entities`, `update_entities`, `get_entities`, `delete_entities`, `create_posts`, `update_posts`, `delete_posts`, and `check_entity_updates` all accept the new types.

### Implementation notes

- `service.py` gains an `_HttpEntityShim` that mimics the python-kanka `EntityManager` interface via `KankaClient._request(...)`. Used for entity types where python-kanka has no manager: `ability`, `item`, `timeline`.
- `calendar` is *also* routed through the HTTP shim, working around an upstream bug in python-kanka 2.6.2 (Calendar model declares `parameters: str` but the API returns `{"layout": null}`).
- `_HttpEntityFacade` gives raw API dicts pydantic-model-like attribute access (with datetime parsing for `created_at` / `updated_at` and auto-wrapping of nested post lists).
- Reverse lookup `KANKA_TYPE_TO_OUR` replaces the hardcoded if/elif chain in `get_entity_by_id`, and now covers all 15 types.
- `VALID_ENTITY_TYPES` is a shared runtime constant used by `operations.py` validation and by `__main__.py` tool-schema enums. Prevents drift across layers.

### Tests

- 39 new unit tests in `tests/unit/test_new_entity_types.py` cover the partition invariants (manager vs HTTP), `_HttpEntityFacade` attribute proxying, `_HttpEntityShim` HTTP verb correctness (including `entities/<id>/posts` for posts on HTTP-backed entities), datetime parsing, and `_entity_to_dict` handling of facade-wrapped dicts.
- Full suite: 175 baseline + 39 new = 214 tests passing.
- Live campaign smoke test: created + fetched + updated + deleted an `ability` via the new HTTP-backed path.

## [2.0.0a1] - 2026-07-09

### Fork rebrand
- Renamed distribution to `mcp-kanka-scorrpine` (import name stays `mcp_kanka`).
- Bumped version to `2.0.0a1` to signal expanded API coverage over upstream 1.1.x.
- Relaxed Python pin from `==3.14.6` to `>=3.14`.
- Added Scorrpine as a co-author; kept Erv Walter as the original author.

### Baseline (from upstream 1.1.1 + recent Renovate PRs)
- `mcp==1.28.1`
- `python-kanka==2.6.2`
- `mistune==3.3.2` (security)
- `python-dotenv==1.2.2` (security)
- `markdownify==1.2.3`
- `beautifulsoup4==4.15.0`

### Planned (phases B onward)
- Additional entity types: calendar, event, family, item, ability, timeline, first-class tag.
- Attributes CRUD on any entity.
- Relations (two-way entity-to-entity links).
- Character sub-resources: inventory, organisations, races, titles, entity abilities.
- Calendar sub-resources: weather, seasons, moons. Timeline eras and elements.
- Meta: campaign, members, roles, permissions, gallery, bulk operations.
