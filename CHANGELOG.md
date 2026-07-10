# Changelog

All notable changes to this fork are documented here. This fork is based on [ervwalter/mcp-kanka](https://github.com/ervwalter/mcp-kanka).

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
