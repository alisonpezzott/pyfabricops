---
name: write-changelog
description: "Write the CHANGELOG.md entries for the current changes. Use after staging commits or when preparing a release."
argument-hint: "Version number (e.g. 1.2.0) — leave blank to add to [Unreleased]"
disable-model-invocation: true
---

Analyse the recent changes in this repository (staged files, commits on the current branch against `main`, or the diff provided) and add their entries to **CHANGELOG.md**, which follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

### Procedure

1. **Read** the top of `CHANGELOG.md` — the `[Unreleased]` section and the latest release — to match its tone and level of detail.
2. **Write** the entries under the right subsections (see Rules).
3. **Edit** `CHANGELOG.md` in place. Never rewrite or reorder existing entries; only add to them.
4. **Report** the entries added and, for a release, the links updated.

### Rules

- Subsections, in this order, only those with entries: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.
- One bullet per change, written as prose that describes the user-visible behavior — what a user of the library or an example now gets — not the implementation.
  - Start with the public name in backticks when there is one: `` `GitStateBackend` ``, `` `examples/Deploy-PowerBI-Pro` ``.
  - A `Fixed` entry says what went wrong and in which situation, then what happens now.
  - A bullet may take several sentences. Wrap lines at about 75 characters and indent continuation lines by two spaces.
- Reference an issue or PR at the end of the bullet only when it adds something: `(#42)`.
- No entries for formatting-only, CI-only or repository tooling changes that do not affect users.

### No version given

Add the entries under `## [Unreleased]`, merging into its existing subsections.

### Version given

1. Create `## [<version>] - <YYYY-MM-DD>` (today's date) below `## [Unreleased]`, with the new entries and the ones already in `[Unreleased]`, which is left empty.
2. Keep the `---` line that separates each version section from the next.
3. Update the link references at the end of the file:

```markdown
[Unreleased]: https://github.com/alisonpezzott/pyfabricops/compare/v<version>...HEAD
[<version>]: https://github.com/alisonpezzott/pyfabricops/compare/v<previous>...v<version>
```

### Example

```markdown
## [Unreleased]

---

## [0.8.2] - 2026-10-30

### Added
- `deploy_items()` accepts `dry_run=True`, which returns the deployment
  plan without changing the target workspace.

### Fixed
- `GitStateBackend` left the lock in place when the push of its release
  failed, so the next deployment found the environment locked. The lock
  is now released before the error is raised.
```
