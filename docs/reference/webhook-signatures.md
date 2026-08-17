# Проверка подписи webhook

Каждая доставка подписывается HMAC-SHA256 с секретом, заданным в подписке. Принимающая сторона **обязана** проверять подпись до того, как поверит содержимому: без этой проверки отправить вам событие может кто угодно.

Форматов два:

- **v2** — с меткой времени и защитой от повторной отправки, по умолчанию для новых подписок
- **v1** — подпись только тела, оставлен для совместимости

## Заголовки

::: code-group

```http [v2]
X-Webhook-Event: user.created
X-Webhook-Signature: sha256=<hex>
X-Webhook-Timestamp: 1744808000
X-Webhook-Signature-Version: v2
```

```http [v1]
X-Webhook-Event: user.created
X-Webhook-Signature: sha256=<hex>
```

:::

## Что подписывается

**v2:**

```
подписываемое = "<timestamp>.<сырое тело>"
ожидаемое     = "sha256=" + hex(hmac_sha256(секрет, подписываемое))
```

Дополнительно нужно отклонять запросы, у которых метка времени отличается от текущего времени больше чем на 300 секунд. Без этой проверки v2 по защищённости не отличается от v1: перехваченный запрос можно будет отправить повторно.

**v1:**

```
подписываемое = "<сырое тело>"
ожидаемое     = "sha256=" + hex(hmac_sha256(секрет, подписываемое))
```

## Python

```python
import hashlib
import hmac
import time

from fastapi import FastAPI, Header, HTTPException, Request

SECRET = b"your-secret"
TOLERANCE = 300

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

Сравнение — только `hmac.compare_digest`: обычное сравнение строк выдаёт длину совпавшего префикса временем работы.

## Node.js

```javascript
import crypto from "node:crypto"
import express from "express"

const SECRET = "your-secret"
const TOLERANCE = 300

const app = express()
app.use(express.raw({ type: "application/json" }))

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

Разбор JSON до проверки подписи ломает её: пересборка меняет пробелы, а подписано было то, что пришло. Берите тело как Buffer.

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
    "time"
)

const secret = "your-secret"
const tolerance = 300

func abs(x int64) int64 {
    if x < 0 {
        return -x
    }
    return x
}

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
        if abs(time.Now().Unix()-ts) > tolerance {
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

func main() {
    http.HandleFunc("/webhook", handler)
    http.ListenAndServe(":8080", nil)
}
```

## PHP

```php
<?php
$secret = "your-secret";
$tolerance = 300;

$body = file_get_contents("php://input");
$sig = $_SERVER["HTTP_X_WEBHOOK_SIGNATURE"] ?? "";
$version = $_SERVER["HTTP_X_WEBHOOK_SIGNATURE_VERSION"] ?? "v1";

if ($version === "v2") {
    $ts = (int)($_SERVER["HTTP_X_WEBHOOK_TIMESTAMP"] ?? 0);
    if (abs(time() - $ts) > $tolerance) {
        http_response_code(400);
        exit("timestamp out of tolerance");
    }
    $signed = $ts . "." . $body;
} else {
    $signed = $body;
}

$expected = "sha256=" . hash_hmac("sha256", $signed, $secret);
if (!hash_equals($expected, $sig)) {
    http_response_code(401);
    exit("invalid signature");
}

echo '{"ok":true}';
```

## Переход с v1 на v2

1. Смените секрет, если есть подозрение, что старые подписи перехватывали
2. Научите приёмник понимать обе версии — их различает заголовок версии
3. Переключите подписку на `v2` в интерфейсе
4. Убедившись по трафику, что всё работает, уберите ветку v1

## Где обычно ошибаются

**Пересобирают JSON перед проверкой.** Подписывать нужно ровно те байты, что пришли.

**Нормализуют перенос строки в конце.** Некоторые прокси его срезают — хешируйте то, что отдал вам фреймворк, без правок.

**Сравнивают подписи обычным равенством.** Нужно постоянное по времени сравнение: `hmac.compare_digest`, `crypto.timingSafeEqual`, `hmac.Equal`, `hash_equals`.

**Пропускают проверку времени в v2.** Тогда v2 не даёт ничего сверх v1.

**Пишут заголовки в лог целиком.** Значение `X-Webhook-Signature` в логах — это подсказка тому, кто их прочитает.
