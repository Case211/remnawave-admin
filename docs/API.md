# Public API (v3)

Remnawave Admin exposes a read/write HTTP API for external integrations at `/api/v3/*`.
Authentication is by API key. Permissions are controlled by scopes.

- **Endpoint reference:** [API-ENDPOINTS.md](./API-ENDPOINTS.md)
- **Error format:** [API-ERRORS.md](./API-ERRORS.md)
- **Interactive docs:** `/api/v3/docs` (Swagger UI), `/api/v3/openapi.json`

---

## Enabling the API

The public API is opt-in. Set the following environment variables on the web backend:

| Variable | Default | Description |
|---|---|---|
| `EXTERNAL_API_ENABLED` | `false` | Master switch for `/api/v3/*` |
| `EXTERNAL_API_DOCS` | `false` | Expose Swagger UI at `/api/v3/docs` |

Check current state from the UI: `Settings -> API` (or `GET /api/v2/api-keys/status`).

---

## Creating an API key

1. Open **API & Webhooks -> API keys** in the admin UI.
2. Click **Create key**. Provide:
   - **Name** - human-readable label (e.g. `prod-monitoring`).
   - **TTL** - `Never` / `1d` / `7d` / `30d` / `90d` / `365d`. Expired keys return `401`.
   - **Scopes** - see the table below.
   - **Description** (optional).
3. The raw key is shown **once**. Copy it into your secret store. Closing the dialog without
   checking "I have saved this key in a secure place" is blocked.
4. The key prefix (first 12 chars, e.g. `rwa_AbCd3fGh`) is visible afterwards. The full value
   is irrecoverable - if lost, rotate or recreate.

### Key format

```
rwa_<43-char urlsafe base64>
```

- Fixed prefix `rwa_` identifies the key class.
- The random part is `secrets.token_urlsafe(32)` (32 raw bytes, ~43 base64 chars).
- Stored as `SHA-256(raw_key)` hex - the server never holds the plaintext.

---

## Authentication

Send the raw key in the `X-API-Key` header on every request:

```bash
curl -H "X-API-Key: rwa_YOUR_KEY" https://panel.example.com/api/v3/users
```

```python
import requests
r = requests.get(
    "https://panel.example.com/api/v3/users",
    headers={"X-API-Key": "rwa_YOUR_KEY"},
    timeout=10,
)
```

```javascript
const res = await fetch("https://panel.example.com/api/v3/users", {
  headers: { "X-API-Key": "rwa_YOUR_KEY" },
})
```

Failures:

- Missing header -> `401 {"detail": "Missing X-API-Key header"}`
- Invalid / disabled / expired key -> `401 {"detail": "Invalid or expired API key"}`
- Valid key without the required scope -> `403 {"detail": "Missing scope: <name>"}`
- Rate limit exceeded -> `429 {"detail": "Rate limit exceeded: N requests per minute"}` with a
  `Retry-After` header.

---

## Scopes

Scopes are attached to each key at creation time. A request only succeeds if the key has the
scope required by the endpoint.

| Scope | Purpose | Sample endpoints |
|---|---|---|
| `users:read` | Read user list/detail | `GET /users`, `GET /users/{uuid}` |
| `users:write` | Create/update/enable/disable/reset-traffic | `POST /users`, `POST /users/{uuid}/enable`, `POST /users/{uuid}/reset-traffic` |
| `users:delete` | Delete a single user | `DELETE /users/{uuid}` |
| `nodes:read` | Read node list/detail | `GET /nodes`, `GET /nodes/{uuid}` |
| `nodes:write` | Enable/disable/restart a node | `POST /nodes/{uuid}/restart` |
| `hosts:read` | Read hosts | `GET /hosts`, `GET /hosts/{uuid}` |
| `stats:read` | Global statistics | `GET /stats` |
| `violations:read` | Read anti-abuse violations | `GET /violations`, `GET /violations/{id}` |
| `bulk:write` | Bulk operations on users | `POST /users/bulk/*` |

Guidelines:

- **Grant only what you need.** Use `users:read` for dashboards, not `users:delete`.
- **Split integrations.** A dedicated key per integration makes rotation painless.
- **Prefer short TTL** for CI/CD keys (1-7 days) and rotate regularly.
- `bulk:write` bypasses per-user scope checks. Treat it as a privileged scope.

---

## Rate limits

Per-key rate limits are applied via a fixed 60-second window. Defaults (override via env):

| Environment variable | Default | Applies to |
|---|---|---|
| `API_V3_RATE_READ_PER_MIN` | `120` | `GET` endpoints |
| `API_V3_RATE_WRITE_PER_MIN` | `60` | `POST` / `PATCH` / `DELETE` (non-bulk) |
| `API_V3_RATE_BULK_PER_MIN` | `10` | Anything under `/users/bulk/` |

When exceeded, the server returns `429` with a `Retry-After` header (seconds remaining in window).

Rate limit counters are keyed by `api_key_id`, **not** by IP. Two different keys from the same
IP do not share quota.

---

## Rotation

If a key is compromised:

1. In the UI, click the **Rotate** icon next to the key.
2. Confirm. The old secret becomes invalid immediately; a new raw key is shown once.
3. Update your integration.
4. No history is lost - `id`, `name`, `scopes`, `expires_at`, `description` are preserved.

Rotation is logged in the audit trail (`api_keys.rotate`).

---

## Expiration

When a key reaches its `expires_at`, the server treats it as invalid. The UI shows an
**Expired** badge. Expired keys can be re-enabled only by rotating (new secret, new clock).

---

## Auditing

Every create / update / rotate / delete for API keys is written to `admin_audit_log` with the
admin username, IP, and extracted details (name, scopes, description - never the secret).

View from **Admin -> Audit log** or query `admin_audit_log` directly.

---

## FAQ

- **Why is `last_used_at` slightly behind?** Usage is flushed to the database every 30s
  (`API_KEY_LAST_USED_FLUSH_SEC`) to avoid row-lock contention under high RPS.
- **Can I share a key between integrations?** Technically yes. Practically no - a single
  compromised service taints all of them, and audit trails become ambiguous.
- **Can I see the raw key again?** No. Rotate or recreate.
- **IP allowlist?** Not yet - planned for a later release.
