## What changed

<!-- One paragraph. Explain the failure mode or the missing capability. -->

## Why

<!-- Link the issue: Closes #123 -->

## Verification

- [ ] `python -m pytest tests/ -q`
- [ ] `bash scripts/coverage_gate.sh`
- [ ] `python -m alembic check` (if models changed)
- [ ] `node --check` on changed frontend files
- [ ] Browser smoke (if UI changed)

## Risk

- [ ] Auth / RBAC / ACL
- [ ] Upload or body limits
- [ ] Migration / startup
- [ ] Backup or audit evidence
- [ ] Public API contract
- [ ] None of the above
