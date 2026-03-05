# API Adjustmenter

**API Adjustmenter** adjusts messy JSON into a stable contract.

It provides:
- **Normalize**: key style unification + value coercion (numbers/dates) + empty-to-null
- **Transform**: rule-based shaping (rename/defaults/cast/flatten)
- **Diff**: schema drift detection (breaking change flags + key/type changes)

✅ Response format follows **APIron common response spec**:
- Success: `{"result": ..., "meta": {...}}`
- Error: `{"error": {...}, "meta": {...}}`

---

## Why this exists (RapidAPI-friendly)

Most API tools can tell you *“the endpoint is up”*.  
API Adjustmenter tells you *“the response is usable and stable”*.

Use cases:
- **Frontend stability**: absorb field/type drift without rewriting client logic
- **ETL/ELT pipelines**: normalize API payloads before loading into DWH
- **Integration adapters**: unify multiple third-party APIs into one contract
- **Regression detection**: detect breaking schema changes early via `/diff`

---

## Features

### 1) Normalize
- Key style: `keep | snake | camel`
- Optional coercions:
  - string numbers → numeric
  - epoch/date-ish strings → ISO8601
  - empty string → `null`

### 2) Transform (Rules)
- `rename`: move/rename fields via dot-path
- `defaults`: fill missing fields
- `cast`: enforce types (`int/float/bool/string/json`)
- `flatten`: lift object fields into top-level (prefix-based)

### 3) Diff (Schema Drift)
- `breaking`: true if removed keys or type changes exist
- `removed_keys`, `added_keys`, `type_changes`

---

## API Endpoints

- `GET  /healthz`
- `POST /normalize`
- `POST /transform`
- `POST /diff`

OpenAPI spec:
- `openapi.yaml` (RapidAPI listing ready)

---

## Response Format (APIron common response spec)

### Success
```json
{
  "result": { "..." : "..." },
  "meta": {
    "execution_ms": 2,
    "input_length": 218,
    "request_id": "uuid"
  }
}
```

### Error

```json
{
  "error": {
    "code": "CAST_FAILED",
    "message": "Failed to cast to int",
    "hint": "Check request fields/types and try again."
  },
  "meta": {
    "execution_ms": 1,
    "input_length": 198,
    "request_id": "uuid"
  }
}
```

---

## Quick Start (Local)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pytest

uvicorn api_adjustmenter.main:app --reload --host 127.0.0.1 --port 8000
```

Swagger UI:

* [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## Examples

### 1) Normalize

Request:

```bash
curl -s http://127.0.0.1:8000/normalize \
  -H "Content-Type: application/json" \
  -d '{
    "input": {"userId":"12","created_at":1700000000,"name":""},
    "options":{"key_style":"snake","coerce_numbers":true,"empty_to_null":true,"date_to_iso":true}
  }' | jq
```

Response (shape):

```json
{
  "result": {
    "output": {
      "user_id": 12,
      "created_at": "2023-11-14T22:13:20Z",
      "name": null
    },
    "adjustment": {
      "key_style": "snake",
      "changes": 3,
      "options": {
        "key_style": "snake",
        "coerce_numbers": true,
        "empty_to_null": true,
        "date_to_iso": true
      }
    }
  },
  "meta": { "execution_ms": 3, "input_length": 123, "request_id": "..." }
}
```
## Rulesets (Reusable Presets)

Rulesets let you store transform rules once and reuse them by `ruleset_id`.

### 1) Create a ruleset
```bash
curl -s http://127.0.0.1:8000/rulesets \
  -H "Content-Type: application/json" \
  -d '{
    "name":"my-default",
    "rules":{
      "rename":{"userId":"user_id"},
      "cast":{"user_id":"int"},
      "flatten":{"profile":"profile_"},
      "pick":["user_id","profile_zip","profile_country"],
      "omit":[]
    }
  }' | jq
````

### 2) Use `ruleset_id` in `/transform`

> Tip: store the id in a shell variable to avoid copy mistakes.

```bash
RULESET_ID="<paste_ruleset_id_here>"

curl -s http://127.0.0.1:8000/transform \
  -H "Content-Type: application/json" \
  -d '{
    "input":{"userId":"12","profile":{"zip":"1000001","country":"JP"}},
    "ruleset_id":"'"$RULESET_ID"'"
  }' | jq
```

### 3) Patch with `override_rules` (optional)

```bash
RULESET_ID="<paste_ruleset_id_here>"

curl -s http://127.0.0.1:8000/transform \
  -H "Content-Type: application/json" \
  -d '{
    "input":{"userId":"12","profile":{"zip":"1000001","country":"JP"},"extra":"x"},
    "ruleset_id":"'"$RULESET_ID"'",
    "override_rules":{"omit":["extra"]}
  }' | jq
```

### 4) List / Get / Delete rulesets

```bash
curl -s "http://127.0.0.1:8000/rulesets?limit=50" | jq
curl -s "http://127.0.0.1:8000/rulesets/<ruleset_id>" | jq
curl -s -X DELETE "http://127.0.0.1:8000/rulesets/<ruleset_id>" | jq
```


### 2) Transform

Request:

```bash
curl -s http://127.0.0.1:8000/transform \
  -H "Content-Type: application/json" \
  -d '{
    "input":{"userId":"12","profile":{"zip":"1000001","country":"JP"},"extra":"x"},
    "rules":{
      "rename":{"userId":"user_id"},
      "cast":{"user_id":"int"},
      "flatten":{"profile":"profile_"},
      "pick":["user_id","profile_zip","profile_country","extra"],
      "omit":["extra"]
    }
  }' | jq
```

### 3) Diff (Schema Drift)

Request:

```bash
curl -s http://127.0.0.1:8000/diff \
  -H "Content-Type: application/json" \
  -d '{
    "before":{"id":1,"name":"a","tags":["x"]},
    "after":{"id":"1","full_name":"a","tags":"x"}
  }' | jq
```

---

## Pricing (RapidAPI plan suggestion)

Recommended (example):

* **Free**: 1,000 requests/month (evaluation)
* **Pro**: 50,000 requests/month (solo dev / small team)
* **Ultra**: 300,000 requests/month (data pipelines / teams)

*(Tune the quotas/price after observing demand.)*

---

## Security & Data Handling

* Designed to be **stateless** (MVP).
* Do **not** store payloads by default.
* Avoid sending secrets/PII unless you explicitly accept that risk.

---

## Roadmap (next high-value upgrades)

* `pick/omit` rule (select/remove keys)
* stronger diff summarization (object-key centric)
* ruleset presets (store and call by id)
* OpenAPI-driven RapidAPI templates and code samples

---

# 日本語版

## 概要

**API Adjustmenter** は「崩れたJSONレスポンス」を **使える契約（contract）** に調整するAPIです。

できること：

* **Normalize**：キーの揺れ統一＋型/日付の整形＋空文字→null
* **Transform**：ルールに従って整形（rename/default/cast/flatten）
* **Diff**：レスポンス形状の差分検知（破壊的変更の検出）

Rulesetsは、整形ルールを保存して `ruleset_id` で何度でも再利用できる機能です。

### 1) ruleset作成

```bash
curl -s http://127.0.0.1:8000/rulesets \
  -H "Content-Type: application/json" \
  -d '{
    "name":"my-default",
    "rules":{
      "rename":{"userId":"user_id"},
      "cast":{"user_id":"int"},
      "flatten":{"profile":"profile_"},
      "pick":["user_id","profile_zip","profile_country"],
      "omit":[]
    }
  }' | jq
```

### 2) `/transform` で ruleset_id を使う

> コピーミス防止のため、変数に入れるのがおすすめです。

```bash
RULESET_ID="<ruleset_idを貼り付け>"

curl -s http://127.0.0.1:8000/transform \
  -H "Content-Type: application/json" \
  -d '{
    "input":{"userId":"12","profile":{"zip":"1000001","country":"JP"}},
    "ruleset_id":"'"$RULESET_ID"'"
  }' | jq
```

### 3) override_rules で一時上書き（任意）

```bash
RULESET_ID="<ruleset_idを貼り付け>"

curl -s http://127.0.0.1:8000/transform \
  -H "Content-Type: application/json" \
  -d '{
    "input":{"userId":"12","profile":{"zip":"1000001","country":"JP"},"extra":"x"},
    "ruleset_id":"'"$RULESET_ID"'",
    "override_rules":{"omit":["extra"]}
  }' | jq
```

### 4) 一覧 / 取得 / 削除

```bash
curl -s "http://127.0.0.1:8000/rulesets?limit=50" | jq
curl -s "http://127.0.0.1:8000/rulesets/<ruleset_id>" | jq
curl -s -X DELETE "http://127.0.0.1:8000/rulesets/<ruleset_id>" | jq
```
---

## 使用用途

「死活監視」ではなく、**“レスポンスが安定して使えるか”** を扱います。

用途：

* フロントの例外処理を削る（型ブレ吸収）
* ETL前処理（API→DWHの前の整形）
* 外部API統合のアダプタ（複数APIを同じ形へ）
* 破壊的変更の早期検知（/diff）

---

## エンドポイント

* `GET  /healthz`
* `POST /normalize`
* `POST /transform`
* `POST /diff`

OpenAPI:

* `openapi.yaml`（RapidAPI掲載向け）

---

## ローカル起動

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pytest

uvicorn api_adjustmenter.main:app --reload --host 127.0.0.1 --port 8000
```

Swagger:

* [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 料金（例）

* **Free**：月1,000回（試用）
* **Pro**：月50,000回（個人〜小規模）
* **Ultra**：月300,000回（チーム/ETL）

---

## セキュリティ・取り扱い

* MVPは基本 **ステートレス設計**
* デフォルトでは **payloadを保存しない**
* 機微情報/PIIは送らない運用推奨（必要なら方針を明示）

---
