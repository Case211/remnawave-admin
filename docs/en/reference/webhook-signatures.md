# Webhook Signature Verification

Remnawave Admin signs webhook deliveries with HMAC-SHA256 using the `secret` configured for
the subscription. Receivers **must** verify the signature before trusting the payload.

Two signature formats are supported:

- **v2 (recommended, default for new webhooks):** timestamped, replay-protected.
- **v1 (legacy):** body-only signature. Kept for backward compatibility.

---

## Headers

### v2

```
X-Webhook-Event: user.created
X-Webhook-Signature: sha256=<hex>
X-Webhook-Timestamp: 1744808000
X-Webhook-Signature-Version: v2
```

### v1

```
X-Webhook-Event: user.created
X-Webhook-Signature: sha256=<hex>
```

No timestamp header. No version header.

---

## Formula

### v2

```
signed_bytes = f"{timestamp}.{raw_body}".encode("utf-8")
expected   = "sha256=" + hmac_sha256(secret, signed_bytes).hex()
```

Receivers MUST also reject requests where `abs(now - timestamp) > 300` seconds to prevent
replay attacks with captured payloads.

### v1

```
signed_bytes = raw_body.encode("utf-8")
expected   = "sha256=" + hmac_sha256(secret, signed_bytes).hex()
```

---

## Python

```python
import hmac, hashlib, time
from fastapi import FastAPI, Request, Header, HTTPException

SECRET = b"your-secret"
TOLERANCE = 300  # seconds

app = FastAPI()

@app.post("/webhook")
async def receive(
    request: Request,
    x_webhook_signature: str = Header(...),
    x_webhook_timestamp: str | None = Header(default=None),
    x_webhook_signature_version: str | None = Header(default=None),
):
    body = await request.body()

    if x_webhook_signature_version == "v2":
        if not x_webhook_timestamp:
            raise HTTPException(400, "missing timestamp")
        ts = int(x_webhook_timestamp)
        if abs(time.time() - ts) > TOLERANCE:
            raise HTTPException(400, "timestamp out of tolerance")
        signed = f"{ts}.".encode() + body
    else:
        signed = body

    expected = "sha256=" + hmac.new(SECRET, signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_webhook_signature):
        raise HTTPException(401, "invalid signature")

    return {"ok": True}
```

Always use `hmac.compare_digest` (constant-time comparison) to prevent timing attacks.

---

## Node.js (Express)

```javascript
import express from "express"
import crypto from "node:crypto"

const SECRET = "your-secret"
const TOLERANCE = 300

const app = express()
app.use(express.raw({ type: "application/json" }))  // keep the raw body

app.post("/webhook", (req, res) => {
  const sig = req.header("X-Webhook-Signature") || ""
  const version = req.header("X-Webhook-Signature-Version")
  const tsHeader = req.header("X-Webhook-Timestamp")

  let signedBuf
  if (version === "v2") {
    if (!tsHeader) return res.status(400).send("missing timestamp")
    const ts = parseInt(tsHeader, 10)
    if (Math.abs(Date.now() / 1000 - ts) > TOLERANCE) {
      return res.status(400).send("timestamp out of tolerance")
    }
    signedBuf = Buffer.concat([Buffer.from(`${ts}.`), req.body])
  } else {
    signedBuf = req.body
  }

  const expected = "sha256=" + crypto.createHmac("sha256", SECRET)
    .update(signedBuf).digest("hex")
  const a = Buffer.from(expected)
  const b = Buffer.from(sig)
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
    return res.status(401).send("invalid signature")
  }

  res.json({ ok: true })
})
```

Do **not** use `bodyParser.json()` before the verification step - JSON re-serialization
changes whitespace and breaks the signature. Capture `req.body` as a Buffer.

---

## Go

```go
package main

import (
    "crypto/hmac"
    "crypto/sha256"
    "encoding/hex"
    "fmt"
    "io"
    "net/http"
    "strconv"
    "strings"
    "time"
)

const secret = "your-secret"
const tolerance = 300

func handler(w http.ResponseWriter, r *http.Request) {
    body, _ := io.ReadAll(r.Body)
    sig := r.Header.Get("X-Webhook-Signature")
    version := r.Header.Get("X-Webhook-Signature-Version")

    var signed []byte
    if version == "v2" {
        ts, err := strconv.ParseInt(r.Header.Get("X-Webhook-Timestamp"), 10, 64)
        if err != nil {
            http.Error(w, "bad timestamp", 400)
            return
        }
        if abs(time.Now().Unix() - ts) > tolerance {
            http.Error(w, "timestamp out of tolerance", 400)
            return
        }
        signed = []byte(fmt.Sprintf("%d.%s", ts, body))
    } else {
        signed = body
    }

    mac := hmac.New(sha256.New, []byte(secret))
    mac.Write(signed)
    expected := "sha256=" + hex.EncodeToString(mac.Sum(nil))
    if !hmac.Equal([]byte(expected), []byte(sig)) {
        http.Error(w, "invalid signature", 401)
        return
    }

    w.Write([]byte(`{"ok":true}`))
}

func abs(x int64) int64 { if x < 0 { return -x }; return x }

func main() {
    _ = strings.HasPrefix  // silence unused in snippet
    http.HandleFunc("/webhook", handler)
    http.ListenAndServe(":8080", nil)
}
```

---

## PHP

```php
<?php
$secret = 'your-secret';
$tolerance = 300;

$body = file_get_contents('php://input');
$sig = $_SERVER['HTTP_X_WEBHOOK_SIGNATURE'] ?? '';
$version = $_SERVER['HTTP_X_WEBHOOK_SIGNATURE_VERSION'] ?? 'v1';

if ($version === 'v2') {
    $ts = (int)($_SERVER['HTTP_X_WEBHOOK_TIMESTAMP'] ?? 0);
    if (abs(time() - $ts) > $tolerance) {
        http_response_code(400);
        exit('timestamp out of tolerance');
    }
    $signed = $ts . '.' . $body;
} else {
    $signed = $body;
}

$expected = 'sha256=' . hash_hmac('sha256', $signed, $secret);
if (!hash_equals($expected, $sig)) {
    http_response_code(401);
    exit('invalid signature');
}

echo '{"ok":true}';
```

---

## Upgrading from v1 to v2

1. Rotate (or set a new) secret if you suspect v1 signatures have been captured.
2. Update the receiver to accept both `v1` and `v2` simultaneously (check the version header).
3. In the admin UI, edit the subscription and switch **Signature version** to `v2`.
4. After traffic confirms v2 works, remove the v1 code path from your receiver.

---

## Common pitfalls

- **Re-parsing the JSON before hashing.** Always hash the raw body bytes as received.
- **Trailing newlines.** Some reverse proxies strip them. Hash the exact bytes your
  framework hands you without normalization.
- **Timing-unsafe compare.** Never use `==` / `===` on signatures. Use constant-time
  comparison (`hmac.compare_digest`, `crypto.timingSafeEqual`, `hmac.Equal`, `hash_equals`).
- **Skipping the timestamp check on v2.** Without it, v2 reduces to v1 from a security POV.
- **Leaking the secret in logs.** Redact `X-Webhook-Signature` values if you log headers.
