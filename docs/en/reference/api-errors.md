# API v3 Error Format

All error responses use a consistent JSON shape:

```json
{
  "detail": "human-readable error message"
}
```

or, for validation errors raised by FastAPI:

```json
{
  "detail": [
    {"loc": ["body", "username"], "msg": "field required", "type": "value_error.missing"}
  ]
}
```

---

## Status codes

| Code | Meaning | Typical causes |
|---|---|---|
| `200` | OK | Successful read |
| `201` | Created | Successful POST that created a resource |
| `204` | No Content | Successful DELETE |
| `400` | Bad Request | Invalid body, bad uuid format, unknown scope |
| `401` | Unauthorized | Missing / invalid / expired key |
| `403` | Forbidden | Key lacks the required scope |
| `404` | Not Found | Resource does not exist |
| `409` | Conflict | Duplicate name, concurrent modification |
| `422` | Unprocessable Entity | Schema validation failed |
| `429` | Too Many Requests | Rate limit exceeded - see `Retry-After` |
| `500` | Internal Server Error | Bug on our side - please report |
| `502` | Bad Gateway | Remnawave Panel unreachable |
| `503` | Service Unavailable | Database not connected |
| `504` | Gateway Timeout | Panel API timed out |

---

## Authentication errors

### Missing key

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{"detail": "Missing X-API-Key header"}
```

### Invalid / disabled / expired

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{"detail": "Invalid or expired API key"}
```

Check:
- Key was typed correctly (prefix `rwa_` included).
- Key is active (not toggled off in the UI).
- Key has not expired (see `expires_at` on the list).

### Scope denial

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{"detail": "Missing scope: users:write"}
```

Edit the key in the UI and add the required scope, or create a new key with the right scope set.

---

## Rate limiting

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 17

{"detail": "Rate limit exceeded: 120 requests per minute"}
```

Counters reset on fixed 60-second windows. `Retry-After` is seconds remaining in the current
window.

Clients should honor `Retry-After` with exponential backoff:

```python
import time, requests

def call(url, headers, max_retries=5):
    for attempt in range(max_retries):
        r = requests.get(url, headers=headers)
        if r.status_code != 429:
            return r
        wait = int(r.headers.get("Retry-After", "5"))
        time.sleep(wait + 1)
    r.raise_for_status()
```

---

## Validation errors (422)

Raised by FastAPI on schema mismatches. Example:

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "detail": [
    {
      "loc": ["body", "expire_at"],
      "msg": "not a valid datetime",
      "type": "value_error.datetime"
    }
  ]
}
```

The `loc` path tells you exactly which field failed.

---

## Panel proxy errors

Some v3 endpoints forward to the upstream Remnawave Panel API. If the Panel is slow or down,
you may see `502` / `504`. Treat them as transient - retry with backoff.

---

## Reporting bugs

If you get a `500`, include:

- Timestamp (UTC)
- Request method + path
- Truncated key prefix (first 12 chars) - never the full key
- Response body
- Correlation ID from `X-Request-Id` response header (if present)

Open an issue at <https://github.com/Case211/remnawave-admin/issues>.
