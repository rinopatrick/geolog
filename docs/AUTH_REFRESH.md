# Token refresh and revocation

JWT access tokens carry a `jti` and `typ`. A refresh token is issued alongside
the access token and is valid for `AUTH_JWT_REFRESH_TTL_SECONDS` (default
30 days).

```text
POST /api/users/token       -> access_token + refresh_token
POST /api/users/refresh     -> new access_token + rotated refresh_token
POST /api/users/revoke      -> persist the token jti (requires any valid role)
```

Refresh rotates and revokes the old refresh token. Revoked jtis are stored in
`revoked_tokens`; the auth middleware rejects them before RBAC. The refresh
endpoint is public-path because the refresh token itself is the credential.
Secrets are signed with the same HMAC key as access tokens; configure a strong
key (>=32 bytes).

## Limits

- No OIDC provider-side logout or JWKS key-rotation webhook.
- No refresh-token family tracking beyond per-token rotation.
- Revocation rows are not automatically pruned; expired jtis can be archived.
