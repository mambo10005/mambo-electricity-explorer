# 0001 — Application license

- **Status:** Proposed (no license chosen)
- **Date:** 2026-10-11

## Context

The repository is private. No `LICENSE` file is included, and
`pyproject.toml` deliberately leaves `license` unset. Without a license, all
rights are reserved by the copyright holder by default.

Two separate concerns:

1. **Outbound license** — terms under which others may use this code.
   Only matters if the code is ever shared or made public.
2. **Inbound licenses** — terms of every dependency and data source we use.
   These apply regardless of repo visibility. Private visibility does **not**
   replace dependency-license or data-terms review.

## Decision

Defer the outbound license choice to the owner. Until decided: no `LICENSE`
file, all rights reserved, and the `Private :: Do Not Upload` classifier
prevents accidental PyPI publication.

Effective now: every new dependency and data source is checked for license /
terms compatibility before it is added, and recorded in the PR.

## Alternatives considered

- **MIT / Apache-2.0** — permissive; appropriate if the code may go public.
- **Proprietary / all rights reserved (explicit)** — appropriate if it stays
  internal.

## Consequences

Must be revisited before any change in visibility or distribution.
