# Changelog

All notable changes to this fork are documented here. This fork is based on [ervwalter/mcp-kanka](https://github.com/ervwalter/mcp-kanka).

## [2.0.0a5] - 2026-07-10

### Phase E: Character sub-resources

Adds four sub-resource families of CRUD tools, plus two new character-only fields on `update_entities`. Tool count grows from 17 to 33.

#### Sub-resource tool families (16 new tools)

**Entity abilities** (attach ability entities to characters/creatures):
- `list_entity_abilities`, `create_entity_abilities`, `update_entity_abilities`, `delete_entity_abilities`

**Inventory** (items in an entity's inventory, either linked to a Kanka Item or freeform):
- `list_inventory`, `create_inventory`, `update_inventory`, `delete_inventory`

**Organisation members** (character-in-organisation memberships with role/hierarchy):
- `list_organisation_members`, `create_organisation_members`, `update_organisation_members`, `delete_organisation_members`

**Quest elements** (entities referenced from a quest, or freeform named elements):
- `list_quest_elements`, `create_quest_elements`, `update_quest_elements`, `delete_quest_elements`

#### Character field extensions on `update_entities`

Two new optional fields, applied only when the target entity is a character (silently ignored for other types):

- `title`: the character's title, e.g. `"The Wise"`, `"Warden of the North"`
- `race_ids`: list of race TYPE-specific ids (from `get_entities`' `id` field)

#### Important API quirks (confirmed via live probe on campaign 396026)

- Cross-cutting: many of these endpoints require **type-specific IDs**, not entity_ids. `ability_id`, `item_id`, `character_id`, `organisation_id`, `quest_id`, and `race_ids` are all type-specific ids. Get them from the `id` field of `get_entities` results (versus `entity_id`).
- **Entity abilities**: POST accepts `abilities: [id]` array (array-of-one for single-row create). PATCH also requires `abilities` in the payload, so the service auto-fetches the current row's `ability_id` when the caller omits it, preserving a friendly partial-update experience.
- **Inventory**: `entity_id` must appear in BOTH the URL path and the JSON body. PATCH requires at least one of `item_id` or `name` — the service auto-fetches to fill in.
- **Organisation members**: URL uses the organisation's type-specific id, and both `organisation_id` and `character_id` in the body are also type-specific ids (redundant).
- **Quest elements**: `entry` is stored as HTML on Kanka's side; the service converts markdown → HTML on write and HTML → markdown on read (same as post/entity entries).
- **Journal readers**: The `/journals/{id}/journal_readers` endpoint returns 404 in the current Kanka API version. Skipped from this fork until upstream exposes it.

### Tests

- 30 new tests in `tests/unit/test_sub_resources.py`: HTTP endpoint/verb correctness for all four families, request-body shape (including the `entity_id`-in-body inventory quirk and the `abilities`-array entity_ability quirk), auto-fetch behavior on partial updates, batch aggregation with mixed validation + HTTP failures, and character title/race_ids field-guard behavior on non-character entity types.
- Full suite: 257 baseline + 30 new = 287 tests passing.
- Live campaign round-trip: created scratch character + ability + item + org + quest + race; attached ability, added inventory rows (both linked and freeform), added org membership, added quest elements (both linked and freeform), updated one row from each family via **partial** update, deleted all rows, and confirmed cleanup.

## [2.0.0a4] - 2026-07-10

### Phase D: Relation CRUD

Adds full CRUD for entity-to-entity relations (character `friend of` character, character `father of` character, character `rival of` character, etc.).

Four new MCP tools, bringing total from 13 to 17:
- `list_relations(entity_id)` — read all relations owned by an entity
- `create_relations(relations: [...])` — batch create
- `update_relations(updates: [...])` — batch update
- `delete_relations(deletions: [...])` — batch delete

### Relation shape

Each relation returned to callers contains:
- `id`, `owner_id`, `target_id` — entity IDs
- `relation` — free-text label (`"friend"`, `"father"`, `"employer"`, etc.)
- `attitude` — numeric score, typically -100 (hostile) to 100 (devoted)
- `colour` — hex string for the link
- `is_star`, `is_pinned` — display flags
- `is_hidden` — admin-only (translated from Kanka's `visibility_id`)
- `is_two_way` — derived: true when `mirror_id` is non-null
- `mirror_id` — the paired mirror relation's ID (if two-way)

### Two-way relations

Setting `two_way: true` on create causes Kanka to also create the mirror on the target entity's side. The response includes `mirror_id` linking to the mirror.

**Important gotcha (confirmed via live probe against a real campaign):** Kanka's `DELETE` on a two-way relation only removes the row on the specified owner's side. The mirror on the target survives. To fully remove both sides, `delete_relations` needs both `relation_id`s in the batch. This is documented in the tool description and `service.delete_relation` docstring.

### Implementation notes

- POST `/entities/{id}/relations` returns `data` as a **list** (cumulative relations on the owner side after the create, not just the new row). The service picks the max-id item to identify the just-created record.
- PATCH intentionally never sends `two_way` — that flag only takes effect at creation time; changing it via update has no effect.
- `is_hidden` translates to/from Kanka's `visibility_id` (1 = visible, 2 = admin-only) the same way posts do.

### Tests

- 20 new tests in `tests/unit/test_relations.py`: payload construction (visibility translation, two_way passthrough, empty rejection), dict normalization (is_two_way derivation, boolean coercion), service HTTP verb correctness (GET/POST/PATCH/DELETE and URL shapes), max-id selection from list response, batch aggregation (mixed validation success/failure and HTTP success/failure).
- Full suite: 237 baseline + 20 new = 257 tests passing.
- Live campaign round-trip: 3 scratch characters (A/B/C), one-way A→B ("Friend"), two-way A↔C ("Rival"), mirror creation confirmed on C, update on Friend (attitude 50→90 + pin), delete of the two-way A-side (confirmed the mirror on C survives).

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
