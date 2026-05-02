---
description: "Write a CHANGELOG.md entry for the current changes. Use after staging commits or when preparing a release."
agent: agent
argument-hint: "Version number (e.g. 1.2.0) — leave blank to add to [Unreleased]"
---

Analyse the recent changes in this repository (staged files, recent commits, or the diff provided) and write a **CHANGELOG.md** entry following the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

### Rules

- Group changes under the appropriate subsections: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.
- Each bullet point must be concise (one line), written in **past tense**, and describe the user-visible impact — not the implementation detail.
- If a version number is provided, create a new `## [<version>] - <today's date>` section.
- If no version is provided, add entries under `## [Unreleased]`.
- Reference issue or PR numbers at the end of the line when available: `(#42)`.
- Do **not** include entries for formatting-only or whitespace changes.

### Output format

```markdown
## [Unreleased]

### Added
- Description of new feature or capability. (#PR)

### Fixed
- Description of bug that was fixed. (#issue)

### Changed
- Description of changed behavior. (#PR)
```

Only output the new section to be inserted — do not rewrite the entire CHANGELOG.
