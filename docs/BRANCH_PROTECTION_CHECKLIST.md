# Branch Protection Checklist (Phase 3a)

Use this checklist when configuring `main` protection in GitHub.

## Required settings
- [ ] Require pull request before merging
- [ ] Require at least 1 approving review
- [ ] Dismiss stale approvals when new commits are pushed
- [ ] Require conversation resolution before merge
- [ ] Require status checks to pass before merging
- [ ] Require branches to be up to date before merging
- [ ] Include administrators in restrictions
- [ ] Restrict force pushes
- [ ] Restrict branch deletion

## Required CI checks
- [ ] `CI / verify`
- [ ] `Security Gates / security`
- [ ] `Phase2 Quality Gate / phase2_critical_coverage` (or equivalent gate name in workflow)

## Optional but recommended
- [ ] Require signed commits
- [ ] Require linear history
- [ ] Require merge queue

## Evidence capture
For audit, capture:
1. Screenshot/settings export of branch protection config
2. One passing PR showing required checks
3. Link to workflow run IDs
