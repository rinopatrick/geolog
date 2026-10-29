# Security policy

## Supported versions

Security fixes are applied to the latest `0.x` release on `main`. Older tags are
not maintained.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting on this repository:

1. Open the **Security** tab.
2. Choose **Report a vulnerability**.
3. Include affected version, reproduction steps, impact and any suggested fix.

Do not open a public issue for an unfixed vulnerability. Do not include real
customer data, production credentials or licensed well data in a report.

## Scope

In scope:

- Authentication, token lifecycle, RBAC and project/well ACL bypasses.
- SQL injection, path traversal, SSRF and stored/reflected XSS.
- Upload handling, denial of service and resource exhaustion.
- Secret exposure in logs, artifacts, responses or the container image.
- Audit-chain or security-evidence tampering.

Out of scope:

- Findings that require a compromised host, database or artifact directory.
- Missing headers on endpoints that return no HTML.
- Rate-limit thresholds that are configurable by the operator.

## Response

This is a small project. Reports are acknowledged on a best-effort basis, and a
fix is released as a patch when the issue is confirmed. Credit is given in the
release notes unless you ask to remain anonymous.
