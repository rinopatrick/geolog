# Security Evidence Template (Phase 3a)

Fill this after each security/deployment hardening cycle.

## Metadata
- Date (UTC):
- Engineer:
- Commit SHA:
- Branch:
- Environment:

## Controls
### 1) Container hardening
- Docker image tag:
- Non-root user enabled: yes/no
- Healthcheck enabled: yes/no
- Evidence: (build log link / command output)

### 2) Secrets policy
- `GEOLOG_SECRETS_SOURCE` configured: yes/no
- `GEOLOG_ENFORCE_SECRETS_SOURCE` enabled: yes/no
- Non-dev startup guard verified: yes/no
- Evidence:

### 3) TLS policy
- `GEOLOG_REQUIRE_TLS` value:
- TLS enforcement verified: yes/no
- Evidence:

### 4) CI security gates
- Bandit result: pass/fail
- pip-audit result: pass/fail
- Secret regex gate: pass/fail
- Workflow URL:

### 5) Backup/restore drill
- Report path:
- Signature path:
- `report.ok`:
- `signature.signature_alg`:
- Retention days:
- Artifact URL:

## API posture snapshots
- `/api/ops/security-posture-status` payload:
- `/api/ops/evidence-status?probe=true` payload:

## Open risks / follow-ups
- Risk:
- Owner:
- ETA:
