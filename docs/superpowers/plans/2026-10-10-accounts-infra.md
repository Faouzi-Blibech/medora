# Accounts and access: Internet Exposure (Infra) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let patients and staff reach Medora from home over HTTPS. Only the proxy faces the internet; the offline demo
is unchanged.

**Architecture:** A Caddy 2 container runs only under the compose profile `internet`. It terminates TLS, adds the
security headers, and routes `/api/*` (prefix stripped, WebSocket included) to `api:8000` and everything else to
`web:3000`. Port bindings become variables so the internet profile can bind api, web and n8n to 127.0.0.1. uvicorn
trusts `X-Forwarded-For` only from the configured proxy addresses, so rate limits and the audit log see real client IPs.

**Tech Stack:** Docker Compose profiles, Caddy 2 (automatic HTTPS / `tls internal`), uvicorn proxy headers.

**Spec:** `docs/superpowers/specs/2026-10-10-accounts-and-access-design.md` §8 (and §7 for the headers).
Backend plan: `2026-10-10-accounts-backend.md` (its Task 9 adds `WEB_ORIGIN`).

## Global Constraints

- `docker compose -f infra/docker-compose.yml --env-file .env up` with `.env.example` defaults must behave exactly as
  today (no proxy, same ports).
- `infra/` is Wali's lane: coordinate before merging.
- Pin images to a version tag (`caddy:2.8`), never `latest`.
- MQTT is never exposed through the proxy. Postgres and MinIO stay bound to 127.0.0.1 (already done).
- `WARD_ENV=prod` is required with the internet profile, so default secrets are refused (backend hardening).
- Only commit when the user has asked for commits; no AI attribution lines.

## Review Focus

1. **WebSocket through the proxy** (`wss://domain/api/ws?token=…`): the live dashboards must still update. Pinned in
   Task 2, step 6.
2. **Spoofed `X-Forwarded-For`** sent straight to the API in the demo profile must not change the IP that the rate
   limiter sees. Pinned in Task 1, step 3.
3. **Exam result PDFs** opened from a `blob:` URL must render under the CSP. Pinned in Task 2, step 6.
4. **The web app built for the proxy** must call `https://domain/api`, not `localhost:8000`. Pinned in Task 2, step 5.
5. **Ports reachable from another machine** in the internet profile: only 80/443 (and MQTT 1883 on the LAN). Pinned
   in Task 2, step 7.

---

### Task 1: Bind variables and trusted proxy headers

**Files:**
- Modify: `infra/docker-compose.yml`, `.env.example`

**Interfaces:**
- Produces: env vars `API_BIND`, `WEB_BIND`, `N8N_BIND` (default `0.0.0.0`) and `FORWARDED_ALLOW_IPS` (default
  `127.0.0.1`). Task 2 relies on them.

- [ ] **Step 1: Edit the compose ports and the api command.** In `infra/docker-compose.yml`:
  - `api` ports: `["${API_BIND:-0.0.0.0}:${API_PORT:-8000}:8000"]`
  - `web` ports: `["${WEB_BIND:-0.0.0.0}:${WEB_PORT:-3000}:3000"]`
  - `n8n` ports: `["${N8N_BIND:-0.0.0.0}:5678:5678"]`
  - `api` command:

```yaml
    command: ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
```

- [ ] **Step 2: Document the variables in `.env.example`** (new block before `--- Host ports`):

```bash
# --- Internet access (compose profile "internet"; see docs/superpowers/specs/2026-10-10-accounts-and-access-design.md §8)
# Leave these defaults for the offline demo. With the proxy: API_BIND=127.0.0.1, WEB_BIND=127.0.0.1,
# N8N_BIND=127.0.0.1, FORWARDED_ALLOW_IPS=* (safe only because the api port is then bound to localhost),
# WARD_ENV=prod, WEB_ORIGIN=https://<WARD_DOMAIN>, NEXT_PUBLIC_API_URL=https://<WARD_DOMAIN>/api
API_BIND=0.0.0.0
WEB_BIND=0.0.0.0
N8N_BIND=0.0.0.0
FORWARDED_ALLOW_IPS=127.0.0.1
WARD_DOMAIN=
# "internal" = self-signed CA for LAN testing; an email address = real Let's Encrypt certificate for WARD_DOMAIN
WARD_TLS=internal
```

- [ ] **Step 3: Verify the demo is unchanged and the header can't be spoofed.** From the repo root:
  - `docker compose -f infra/docker-compose.yml --env-file .env config | grep -E "published|forwarded"` →
    expected: published 8000, 3000, 5678 on `0.0.0.0` and `--forwarded-allow-ips "127.0.0.1"`.
  - `docker compose -f infra/docker-compose.yml --env-file .env up -d --build api && sleep 6 && curl -s localhost:8000/health` → `"status":"ok"`.
  - **Spoof check:** send 11 failed logins with a different `X-Forwarded-For` each time:

```bash
for i in $(seq 1 11); do curl -s -o /dev/null -w "%{http_code} " -H "X-Forwarded-For: 10.0.0.$i" \
  -H 'Content-Type: application/json' -d '{"email":"ghost@x.tn","password":"wrong-pass-1"}' localhost:8000/auth/login; done; echo
```

  Expected once the backend plan's Task 3 is merged: ten `401` then `429`, so the header was ignored. Before that,
  expect eleven `401`.

- [ ] **Step 4: Commit** (only if asked):
  `git add infra/docker-compose.yml .env.example && git commit -m "feat(infra): configurable port binding and trusted proxy headers"`

---

### Task 2: Caddy proxy under the `internet` profile

**Files:**
- Create: `infra/caddy/Caddyfile`
- Modify: `infra/docker-compose.yml` (new `proxy` service + `caddy-data` volume), `README.md` (a short "Internet
  access" section; README is Faouzi's, so ask)

**Interfaces:**
- Consumes: the Task 1 variables; backend `WEB_ORIGIN` (backend plan Task 9).
- Produces: `https://$WARD_DOMAIN/` → web and `https://$WARD_DOMAIN/api/*` → api.

- [ ] **Step 1: Write `infra/caddy/Caddyfile`:**

```caddyfile
# Medora reverse proxy (compose profile "internet"). TLS + security headers; /api/* → FastAPI, the rest → Next.js.
{$WARD_DOMAIN:localhost} {
	tls {$WARD_TLS:internal}
	encode gzip

	header {
		Strict-Transport-Security "max-age=31536000"
		X-Frame-Options "DENY"
		X-Content-Type-Options "nosniff"
		Referrer-Policy "same-origin"
		Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' wss:; frame-src 'self' blob:; object-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
		-Server
	}

	# /api/ws is the WebSocket; reverse_proxy upgrades it automatically
	handle_path /api/* {
		reverse_proxy api:8000
	}
	handle {
		reverse_proxy web:3000
	}
}
```

  (`'unsafe-inline'` for scripts is needed by the Next.js App Router without nonces. Tightening it with nonces is a
  later step, noted in the README.)

- [ ] **Step 2: Add the service** to `infra/docker-compose.yml` (after `web`) and the volume:

```yaml
  proxy:
    image: caddy:2.8
    profiles: ["internet"]
    environment:
      WARD_DOMAIN: ${WARD_DOMAIN:-localhost}
      WARD_TLS: ${WARD_TLS:-internal}
    ports: ["80:80", "443:443"]
    volumes:
      - ./caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
    depends_on: [api, web]
```

Under `volumes:`, add `caddy-data:`.

- [ ] **Step 3: Validate.** Run `docker compose -f infra/docker-compose.yml --env-file .env config -q && echo ok`
  → `ok`. Run `docker compose -f infra/docker-compose.yml --env-file .env config --services` → `proxy` is **not**
  listed. Then run it again with `--profile internet` → `proxy` **is** listed.
  Run `docker run --rm -v "$(pwd -W)/infra/caddy:/c" caddy:2.8 caddy validate --config /c/Caddyfile --adapter caddyfile` → `Valid configuration`.

- [ ] **Step 4: Prepare a LAN test `.env.internet`** (git-ignored; copy of `.env` with these overrides; `<lan-ip>` is
  this laptop's IP):

```bash
API_BIND=127.0.0.1
WEB_BIND=127.0.0.1
N8N_BIND=127.0.0.1
FORWARDED_ALLOW_IPS=*
WARD_DOMAIN=<lan-ip>
WARD_TLS=internal
WEB_ORIGIN=https://<lan-ip>
NEXT_PUBLIC_API_URL=https://<lan-ip>/api
NEXT_PUBLIC_USE_MOCKS=0
```

  Add `.env.internet` to `.gitignore` if `.env*` isn't already covered (check with `git check-ignore .env.internet`).
  `WARD_ENV=prod` will refuse the demo secrets, so set real ones here, or keep `WARD_ENV=demo` for this LAN test only
  and say so in the PR.

- [ ] **Step 5: Start and check routing.**
  `docker compose -f infra/docker-compose.yml --env-file .env.internet --profile internet up -d --build`, then:
  - `curl -sk https://<lan-ip>/api/health` → `{"status":"ok",...}`
  - `curl -skI https://<lan-ip>/` → `200`, with the `content-security-policy`, `strict-transport-security`,
    `x-frame-options: DENY` and `x-content-type-options: nosniff` headers present.
  - `docker exec ward-web-1 sh -c "grep -rl 'https://<lan-ip>/api' .next/static | head -1"` → one file. This proves
    the build points at the proxy.

- [ ] **Step 6: Browser end-to-end** (Chrome; accept the internal CA warning once):
  - Log in as `nurse@medora.tn` at `https://<lan-ip>/`.
  - Publish one vital as `bsu-001` (the MQTT command from the MQTT hardening report) → the nurse dashboard updates
    live. That proves `wss://<lan-ip>/api/ws`.
  - Log in as the doctor and open an exam result PDF → it renders, with no CSP errors in the console.
  - Sign up a new account (backend plan Task 4) → the generic success screen appears.

- [ ] **Step 7: Exposure check from another machine on the LAN** (a phone on the same Wi-Fi works, or a second laptop):
  `nmap -p 80,443,3000,5432,5678,8000,9000,1883 <lan-ip>` → open: 80, 443, 1883. Closed or filtered: 3000, 5432,
  5678, 8000, 9000.
  Without nmap: in a phone browser, `http://<lan-ip>:8000/health` must fail and `https://<lan-ip>/api/health` must work.

- [ ] **Step 8: Back to demo mode.**
  `docker compose -f infra/docker-compose.yml --env-file .env --profile internet down proxy && docker compose -f infra/docker-compose.yml --env-file .env up -d --build`
  → `http://localhost:3000` works as before.

- [ ] **Step 9: README note** (ask Faouzi): add an "Internet access" section with the Step 4 variables, the start
  command, the domain/DNS + ports 80/443 requirement for real Let's Encrypt, and the note that CSP `unsafe-inline` is a
  known v1 limit.

- [ ] **Step 10: Commit** (only if asked):
  `git add infra/caddy infra/docker-compose.yml .gitignore README.md && git commit -m "feat(infra): HTTPS reverse proxy profile for internet access"`
