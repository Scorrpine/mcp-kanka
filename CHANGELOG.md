# Changelog

All notable changes to this fork are documented here. This fork is based on [ervwalter/mcp-kanka](https://github.com/ervwalter/mcp-kanka).

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
