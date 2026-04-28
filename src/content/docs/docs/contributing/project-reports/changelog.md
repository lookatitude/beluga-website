---
title: "Changelog — Beluga AI"
description: "All notable changes to Beluga AI organized by release. Auto-generated from conventional commits covering features, fixes, and improvements."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI changelog, release notes, version history, Go AI framework updates, conventional commits"
---

This page is auto-populated from the project's CHANGELOG.md at build time.

## [2.13.1] - 2026-04-22

### Miscellaneous

- **release**: Update CHANGELOG.md for v2.13.0 [skip ci] (#329)

## [2.13.1] - 2026-04-22

### Documentation

- C-020 + C-021 framework-workflow learnings from DX-1 S4 (PR #326) (#327)

## [2.13.0] - 2026-04-22

### Features

- DX-1 S4 — beluga eval CLI + scaffolded eval branch [LOO-154] (#326)

### Miscellaneous

- **release**: Update CHANGELOG.md for v2.12.0 [skip ci] (#323)

## [2.12.0] - 2026-04-21

### Features

- **cli**: Beluga run/dev/test dev loop + mock LLM + real o11y bootstrap (LOO-151, DX-1 S3) (#324)

### Miscellaneous

- **release**: Update CHANGELOG.md for v2.11.0 [skip ci] (#320)

## [2.11.1] - 2026-04-21

### Documentation

- Capture PR #314 + PR #318 pre-push hardening learnings (#321)

### Miscellaneous

- **deps**: Bump the aws-sdk group with 4 updates (#315)

## [2.11.0] - 2026-04-21

### Features

- **cli**: Beluga init and beluga new scaffolding (LOO-149, DX-1 S2) (#314)

## [2.10.2] - 2026-04-21

### Bug Fixes

- Remove UsageCount mutation from SearchHeuristics

### Miscellaneous

- **release**: Update CHANGELOG.md for v2.10.1 [skip ci]
- Fix SonarCloud issues in infra/misc files
- Fix SonarCloud issues in agent/ package
- Fix SonarCloud issues in memory/ package
- Fix SonarCloud S1192 issues in eval/ package
- Fix SonarCloud issues in auth/, runtime/, k8s/operator/
- Fix SonarCloud issues in guard/, orchestration/, llm/
- Fix SonarCloud issues in core/ and remaining packages
- Gofmt agent-modified files
- Nosec G101 on credential operation-name constants
- **security**: Resolve all 32 gosec/SonarCloud findings
- **deps**: Bump the go-minor-patch group with 4 updates
