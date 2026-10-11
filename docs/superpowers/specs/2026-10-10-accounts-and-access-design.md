# Accounts and access: self sign-up, hospital approval, internet access — design

> Status: approved (2026-10-10). Touches: backend auth (Wali), web (Faouzi), infra (Wali).
> Contracts to bump on implementation: `api.md` 1.8 → 1.9, `data-model.md` 1.4 → 1.5.

## 1. Goal

People create their own Medora account, and the hospital (or doctor's cabinet) decides what each account may reach.
Nobody, neither the company nor a hospital admin, ever chooses or sees another person's password. Patients and
staff can use Medora from home over the internet.

Success looks like this:
- A new nurse signs up from home, an admin approves her as "nurse, Cardiology", and she sees the Cardiology ward
  and nothing else.
- A patient signs up with the code reception gave them and lands on their own record. No manual matching is done
  and no other patient's data is reachable.
- An admin disables an account and its open sessions stop working on the next request.
- An internet attacker cannot learn which emails exist, guess codes, or brute-force passwords at useful speed.

## 2. Decisions taken with the user

| Topic | Decision |
|---|---|
| Where data lives | One install per site (hospital server or doctor's cabinet PC). Data stays on that site. The company ships software only and holds no patient data and no login into any site. |
| Who creates accounts | The user signs up with their own email and password. |
| Access levels | Three levels, each approving the one below:<br>**1. Company → hospital.** Our admin activates the hospital's install and creates its first hospital-admin account (setup command plus a one-time code). The company keeps no login into the hospital afterwards.<br>**2. Hospital admin → everyone in the hospital.** Approves doctors, nurses and other admins, and can enroll any patient.<br>**3. Doctor → his team and his patients.** A doctor approves the nurses or assistants who sign up to work with him, and gives his own patients access with an enrollment code. He can also share a patient with another doctor. |
| Pending accounts | Every staff sign-up starts **pending** with no access. It goes to the doctor the person chose at sign-up, or to the hospital admin if they chose none. |
| Reach | From home over the internet, so HTTPS and abuse limits are in scope. |

## 3. Non-goals (v1)

- **Email verification and email delivery.** Admin approval (staff) and enrollment codes (patients) are the trust
  gates, so access never depends on owning an inbox. Email is an add-on once n8n mail is set up (teammate's lane).
- **Multi-factor authentication.** This is the next step for admin and doctor accounts; the data model leaves room
  for it.
- **Other team roles.** A doctor's team is nurses only (decided 2026-10-10); there is no secretary role.
- **One account holding two roles.** In a doctor's cabinet, the doctor and the admin are two accounts, e.g. the
  doctor plus the secretary.
- **Single sign-on, or national INS / Sahetna identity.** This is the production path and is out of scope here.
- **Multi-tenancy in one database.** Each site is its own install.

## 4. How it fits the current architecture

Nothing structural changes. The same containers run. One optional reverse-proxy container is added for internet
access. Every request still goes token → `get_current_user` → `require_roles` → ownership check. The new pieces plug
into those existing gates.

```
Internet ──HTTPS──▶ proxy (Caddy, new, compose profile "internet")
                       ├── /api/*, /ws ──▶ api:8000   (FastAPI, unchanged gates + new auth routes)
                       └── /*          ──▶ web:3000   (Next.js, new sign-up / pending / admin screens)
LAN only: mqtt:1883 (devices).   Localhost only: db, minio, n8n editor.
```

## 5. Data model (migration 0004)

**`users`**, changed:
| Column | Change |
|---|---|
| `role` | becomes nullable: a pending staff account has no role |
| `status` | new, text, not null, default `active`: one of `pending`, `active`, `disabled`, `rejected`. Existing rows become `active`. |
| `failed_logins` | new, int, default 0 |
| `locked_until` | new, timestamptz, null |
| `approved_by`, `approved_at` | new: the admin and time of approval |
| `requested_note` | new, text, nullable: what the person typed at sign-up, e.g. "nurse, Cardiology" (free text, information only) |
| `requested_doctor_id` | new, nullable FK users: the doctor chosen at sign-up ("I work with Dr …"). It decides who sees the pending request. |

**`staff`**, changed:
| Column | Change |
|---|---|
| `supervisor_id` | new, nullable FK users: the doctor whose team this nurse belongs to. Set when that doctor approves the account. |

**`access_codes`**, new. One table for both one-time code uses:
| Column | Notes |
|---|---|
| `id` | `ac-0001` |
| `purpose` | `enrollment` (link a patient account to a record) or `reset` (set a new password) |
| `code_hash` | sha256 of the code. The plain code is shown once to the issuer and never stored. |
| `patient_id` | for `enrollment` |
| `user_id` | for `reset` |
| `issued_by`, `created_at`, `expires_at` | default lifetime 48 h |
| `used_at`, `used_by` | single use |

Issuing a new code for the same patient or user revokes the previous unused one by setting its `expires_at` to now.

**`patient_access`**, new. A doctor shares a patient with another doctor:
| Column | Notes |
|---|---|
| `patient_id`, `user_id` | the doctor receiving access |
| `granted_by` | must be the attending doctor (or an admin) |
| `created_at`, `expires_at` | required; default 30 days, at most 1 year |
| `revoked_at` | nullable |

## 6. Flows

**6.1 Company gives the hospital access (installation):**
`python -m app.bootstrap --email admin@site --name "…"` creates the first `admin` account with status `active` and
prints a one-time `reset` code. The admin opens the web app, chooses "I have a code", and sets their own password.
The command refuses to run if an admin already exists.

**6.2 Staff sign-up and approval:**
1. `POST /auth/register` with name, email, password, an optional note, and an optional "I work with" doctor
   (`requested_doctor_id`, picked from a list of the hospital's doctor names; no emails are shown). The account is
   created `pending`, with role null.
2. Login with a pending account → 403 `account_pending` ("Your account is waiting for approval").
3. **Who sees the request and what they may grant:**

| Approver | Sees in **Pending accounts** | May approve as | Result |
|---|---|---|---|
| Hospital admin | every pending account | `doctor`, `nurse`, `admin`, plus a ward | status `active`, `staff` row with that ward |
| Doctor | only accounts with `requested_doctor_id` = him | `nurse` only (his team) | status `active`, `staff` row with `supervisor_id` = him and ward = null; the hospital admin may add a ward later |

4. Either approver may reject → status `rejected`. A doctor can never create a doctor or an admin. A request that
   names a doctor stays visible to the hospital admin too, so it never gets stuck.
5. Approval and rejection are audited.
6. A rejected account can still be approved later, since approve accepts `pending` or `rejected`. The email stays
   taken, so the person never needs a second account.
7. The hospital admin can disable any account. A doctor can disable only the members of his own team.

**What a doctor's team nurse can see:** the patients whose attending doctor is her supervisor. If the hospital admin
also gives her a ward, she sees that ward too. `can_access` gains this rule for nurses:
`ward matches` **or** `staff.supervisor_id == patient.attending_doctor_id`. The other nurse-scoped lists
(`GET /patients`, `GET /alerts`, WebSocket routing in `ws/hub.py`) use the same rule, so a team nurse with no ward
still receives her doctor's patients' alerts.

**6.3 Patient enrollment:**
1. The admin (reception) or the patient's attending doctor issues an enrollment code for an existing patient record:
   `POST /patients/{id}/enrollment-code` returns `{code, expires_at}`, shown once. It can be printed or read out.
2. The patient signs up with the code. If the code is valid, unused and unexpired, the account is created `active`
   with role `patient` and `patient_id` linked, and the code is marked used.
3. A wrong or expired code does not create a patient account. It returns the same generic error and counts against
   the rate limit (section 7).
4. A patient record can have only one patient account. A second enrollment for the same record → 409
   `already_enrolled`; staff must disable the old account first.

**6.4 Forgotten password:**
1. The admin issues a reset code for the user (`POST /users/{id}/reset-code`), and the person gets it in person or
   by phone.
2. `POST /auth/reset` with email, code and new password sets the password, clears the lockout, and marks the code used.
3. The admin never sees or sets the password.

**6.5 Leaving or blocking:**
- The admin disables an account (`POST /users/{id}/disable`). `get_current_user` already loads the user from the
  database on every request; it will reject a user who is not `active`, so existing tokens die immediately. No
  token blacklist is needed.
- `POST /users/{id}/enable` restores the account.

**6.6 Doctor shares a patient:**
- The attending doctor calls `POST /patients/{id}/access` with `{doctor_id, expires_at}`, and
  `DELETE /patients/{id}/access/{doctor_id}` to revoke.
- `can_access` (`app/auth/deps.py`) gains one rule: doctor = attending **or** holds an unexpired, unrevoked grant.
- **Sharing is read-only** (decided 2026-10-10): the shared doctor reads everything the attending doctor reads
  (record, vitals, exams, appointments, alerts, live updates) but writes nothing on that patient: no notes,
  prescriptions, urgency changes, exam orders or device commands (403). Only the attending doctor or the admin can
  share, revoke or issue codes.
- Every check, grant and revoke goes through the existing audit.

## 7. Security controls (internet-facing)

| Threat | Control |
|---|---|
| Password brute force | Per-account lock: 5 failed logins → `locked_until` = now + 15 min. Per-IP limit of 10 **failed** logins/min, checked before the password is verified. Successful logins don't count, because a whole hospital can share one public IP. |
| Code guessing | Codes are 10 characters from a 31-symbol alphabet with no 0/O/1/I/L (about 50 bits), shown as `XXXXX-XXXXX`. Per-IP limit on `/auth/register` and `/auth/reset`: 5/min, 30/day. Codes expire after 48 h and are single use. |
| Account enumeration | `/auth/register` always answers 202 "If the details are valid, your account was created or is waiting for approval", including for an existing email. Login gives the same 401 for an unknown email and a wrong password. Pending, locked and disabled accounts get their specific message **only after the password is correct**. |
| Self-granted roles | The register body has no role or ward field (`extra="forbid"`). Only an admin can set role and ward. |
| Weak passwords | At least 10 characters, not equal to the email or name, and not in a bundled list of the 1,000 most common passwords. bcrypt cost stays at 12. |
| Stolen or long-lived sessions | Disabling takes effect on the next request (6.5). JWT lifetime drops from 12 h to 8 h (`JWT_EXPIRE_HOURS`). |
| Wrong client IP behind the proxy | uvicorn runs with `--proxy-headers --forwarded-allow-ips=<proxy>`, so rate limits and audit see the real IP. |
| XSS stealing the token | The proxy sets `Content-Security-Policy` (self only), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` and HSTS. |
| Audit gaps | Audit rows are written for register, approve, reject, disable, enable, code issue, code use, failed code, login failure and lockout. |

**Rate-limit implementation:** an in-process sliding window keyed by IP and route (and by email for login). It needs
no new dependency and is correct because the API runs as one process; this is documented next to the code. If the
API is ever scaled out, the limits move to the proxy or Redis.

## 8. Internet exposure (compose profile `internet`)

- A new `proxy` service (Caddy 2) runs only with `docker compose --profile internet up`. The offline demo is
  unchanged.
- `WARD_DOMAIN` set means automatic Let's Encrypt TLS. Unset means `tls internal`, for testing on a LAN.
- Routes: `/api/*` → `api:8000` with the `/api` prefix stripped; `/ws` → api; everything else → web. The web
  app is built with `NEXT_PUBLIC_API_URL=https://$WARD_DOMAIN/api`.
- Port binding is configurable: `API_BIND` / `WEB_BIND` default to `0.0.0.0` (demo) and are set to `127.0.0.1`
  with the internet profile, so only the proxy's 80/443 face the internet.
- MQTT stays on the LAN. Devices never go over the internet.
- The n8n editor is bound to localhost in this profile. n8n-to-api traffic stays on the docker network.
- CORS `allow_origins` comes from a setting (`WEB_ORIGIN`) instead of the hard-coded localhost.
- `WARD_ENV=prod` is required with this profile, so all default secrets are refused (Task 4 hardening).

## 9. API changes (api.md 1.9)

| Method and path | Who | Notes |
|---|---|---|
| `POST /auth/register` | anyone | `{name, email, password, note?, enrollment_code?}` → 202 generic |
| `POST /auth/reset` | anyone | `{email, code, new_password}` → 204, or generic 400 |
| `POST /auth/login` | anyone | adds 403 `account_pending` / `account_disabled` / 423 `account_locked`, only after the password is correct |
| `POST /auth/change-password` | logged-in user | `{current_password, new_password}` |
| `POST /auth/logout` | logged-in user | 204 + audit row. Ends **this device's** session only (user decision, 2026-10-10): the client deletes its token, and tokens are not revoked server-side, so a copied token stays valid until it expires |
| `GET /doctors/directory` | anyone | doctor display names and ids only, for the sign-up "I work with" picker. Rate-limited, no emails. |
| `GET /users?status=pending` | admin (all), doctor (his requests) | pending list: name, email, note, created_at |
| `POST /users/{id}/approve` | admin, doctor | admin: `{role, ward?}`, role in doctor/nurse/admin. Doctor: role nurse only, into his team (403 otherwise). |
| `POST /users/{id}/reject` · `/disable` · `/enable` | admin (anyone), doctor (his team only) | |
| `GET /doctors/me/team` | doctor | his team members and their status |
| `PATCH /users/{id}` | admin | `{ward}`: add or clear a ward on an active doctor or nurse (e.g. a team nurse) |
| `POST /patients/{id}/reset-code` | admin, attending doctor | reset code for the patient's account → `{code, expires_at}` |
| `POST /users/{id}/reset-code` | admin | → `{code, expires_at}`, shown once |
| `POST /patients/{id}/enrollment-code` | admin, attending doctor | → `{code, expires_at}`, shown once |
| `POST /patients/{id}/access` · `DELETE …/access/{doctor_id}` | attending doctor, admin | doctor sharing |
| `GET /staff` | admin | gains `status` |

Error envelope and status-code conventions are unchanged. Existing endpoints keep their shapes.

## 10. Web changes (Faouzi)

- Sign-in page: links to "Create an account" and "I have a code".
- **Create account** form: name, email, password, optional note, optional enrollment code, then a "waiting for
  approval" or "you're in" screen.
- Login messages for pending, locked and disabled accounts.
- Admin: a **Pending accounts** tab with approve (role + ward picker) and reject, and disable/enable plus "issue
  reset code" on the Staff page.
- Doctor: a **My team** tab showing pending requests addressed to him (approve as nurse / reject) and his team
  members (disable/enable).
- The sign-up form has an optional "I work with" doctor picker.
- Patient detail (admin, attending doctor): an "Issue enrollment code" button that shows the code once with a
  print view; doctor: "Share with a doctor".
- A change-password screen in each role's menu.
- All strings in French, Arabic and English (i18n messages files).

## 11. Migration and compatibility

- Migration 0004 is additive. Existing users become `active` with their current roles, so seeds, tests and the demo
  keep working.
- `python -m app.seed` keeps creating active demo accounts (demo only; prod refuses the seed password, per Task 4).
- No change to MQTT, the AI modules or n8n.

## 12. Testing

API tests (pytest, existing fixtures), written first:
- Register:
  - creates a pending account with no role;
  - a role or ward in the body → 422;
  - an existing email gets the same 202 and creates no duplicate.
- Login:
  - pending/disabled → the specific error only with the right password;
  - unknown email and wrong password give identical responses;
  - 5 failures lock the account, and a correct password during the lock → 423.
- Approve, as admin: sets role, ward and the staff row; a nurse → 403; the user can log in afterwards and sees only
  their ward.
- Approve, as doctor:
  - only requests naming him are listed, and approving another doctor's request → 403;
  - approving as `doctor` or `admin` → 403;
  - the approved nurse gets `supervisor_id` = him, sees exactly his patients (and their alerts), and not another
    doctor's patients in the same ward;
  - he can disable his team members but nobody else.
- Enrollment:
  - a valid code links the account to the right patient;
  - reuse, expired and wrong codes fail with a generic error;
  - issuing a new code revokes the old one;
  - a second account for the same patient → 409;
  - only the admin or attending doctor can issue.
- Disable: a token issued before the disable is rejected on the next request.
- Reset: a code sets a new password, clears the lock, and works once.
- Sharing: a grant gives access until expiry or revoke, then 403; only the attending doctor or admin can grant.
- Rate limits: the 11th login per minute from one IP → 429, and register/reset hit their limits.
- Audit rows exist for every event in section 7.
- Bootstrap: refuses when an admin exists; the printed code works once.

End-to-end check: the `internet` profile with `tls internal` on a laptop. Over `https://<lan-ip>`, run sign-up →
approve → login as a nurse, and enrollment code → patient login. Check that the security headers are present and
that ports 5432, 8000, 3000 and 5678 are unreachable from another machine.

## 13. Rollout and ownership

1. Backend (Wali's lane, coordinate): migration 0004, auth routes, `can_access` grant rule, rate limiter, bootstrap
   command, tests.
2. Contracts: `api.md` 1.9 and `data-model.md` 1.5 in the same PR, announced to the team.
3. Web (Faouzi): the screens in section 10, built against the new contract (mocks first).
4. Infra (Wali): the `proxy` service, Caddyfile, bind variables, uvicorn proxy flags.

Items 1, 3 and 4 can be built in parallel once the contract is agreed.

## 14. Open questions

- Code lifetime: 48 h for enrollment and reset codes. Should reception be able to choose a shorter time?
- The domain name, and who operates the server and its backups at each site (an operational question, not code).

## Addendum (2026-10-10): sign-up v2, decided by the user

This overrides the sections above where they differ.

- **Sign-up form:** name, email, own password (never shared), a **role** from `patient | nurse | doctor`, and the
  **hospital**. One install is one hospital (the database stays local), so the list shows this install's
  hospital (`GET /hospital`). Patients and nurses may also pick a doctor (cabinet).
- **Approval:** the hospital admin's dashboard lists every pending request. A doctor sees the patients and nurses who
  picked him and can approve them. Doctors are approved by the admin only. The approver may change the requested role,
  and `admin` can't be requested.
- **Patient record link:** the approver links the account to an existing record (search) or creates a new one.
  A human checks the identity, so **enrollment codes are removed**.
- **Codes that stay:** the password-reset code (no email server offline) and the first-admin bootstrap code.
- **Hardening from the final review:**
  - a doctor can't undo an admin's disable or reject;
  - a disabled account loses its live connections, Telegram alerts and the digest at once.
- **Patient sharing between doctors is read-only** (see 6.6).
