---
name: review-pr
description: "Review a Python pull request or set of changes for correctness, style, security and test coverage."
argument-hint: "PR number, branch or files to review (blank: current branch against main)"
disable-model-invocation: true
---

Review the provided Python code changes as a senior engineer. Be constructive and specific.

### Changes to review

- **PR number** — `gh pr diff <number>`.
- **Branch** — `git diff main...<branch>`.
- **Files** — review those files as they are now.
- **Nothing given** — `git diff main...HEAD`, plus uncommitted changes from `git diff HEAD`.

Read the surrounding code of each changed file before judging a change in isolation.

### Review checklist

#### Correctness
- [ ] Logic is correct and handles edge cases.
- [ ] No off-by-one errors or silent failures.
- [ ] Error handling is explicit (no bare `except`, no swallowed exceptions).

#### Style & Conventions
- [ ] Type hints on all function signatures.
- [ ] Google-style docstrings on all public functions and classes.
- [ ] Follows Ruff rules — no linting issues would be introduced.
- [ ] Variable and function names are descriptive and in `snake_case`.

#### Security (OWASP Top 10 awareness)
- [ ] No secrets or credentials hard-coded.
- [ ] User input is validated at system boundaries.
- [ ] No SQL concatenation (use parameterised queries).
- [ ] Dependencies are not introduced without justification.

#### Tests
- [ ] New logic has corresponding tests.
- [ ] Tests cover happy path, edge cases and error scenarios.
- [ ] No test is asserting implementation details (test behaviour, not internals).

#### Performance
- [ ] No N+1 queries or unnecessary loops.
- [ ] Heavy operations are not called in tight loops.

### Output format

For each issue found, use this structure:

```
**[Severity]** `path/to/file.py` line N
_Category_: Short title
> Explanation of the problem and suggested fix.
```

Severity levels: `Critical` | `Major` | `Minor` | `Suggestion`

End with a **Summary** section noting overall quality and any blocking concerns.
