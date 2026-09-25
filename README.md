[README.md](https://github.com/user-attachments/files/32670516/README.md)
# Notification Service

A centralized notification microservice that handles all outbound Email and SMS
notifications for the platform. Other modules call this service instead of talking
to third-party Email/SMS providers directly.

## What this service does

- Consumes third-party Email and SMS APIs — this service never sends a message
  directly, it wraps and calls out to approved external providers.
- Maintains reusable, placeholder-based notification templates, managed through an
  admin API.
- Logs every notification attempt (recipient, channel, template, status, timestamps,
  provider response, failure reason) to a database.
- Retries failed sends a configurable number of times, distinguishing between
  failures worth retrying and failures that will never succeed.
- Tracks each notification's lifecycle through explicit statuses.
- Keeps all provider URLs, credentials, and tunables in configuration — nothing is
  hardcoded.

## Status: work in progress

**Built and working:**
- Template CRUD (admin API), with case-normalized names/channels and channel
  validation (`SMS` / `EMAIL` only)
- Email sending — token-based auth against the email middleware, automatic
  re-authentication on an expired token, retry logic, and structured logging
- Database-backed notification logging (`notification_logs` table)
- Startup-time config validation (the app refuses to start if a required
  configuration value is missing)

**Not yet built:**
- SMS sending — blocked on third-party SMS API documentation, which hasn't been
  provided yet. `/send` will call `send_sms(...)` for a non-email channel, but that
  function isn't implemented.
- Defensive handling for a non-JSON error response from the email provider (the
  real middleware's documentation doesn't specify what failure bodies look like for
  every status code).
- Background/async processing — `/send` currently blocks synchronously for the
  full duration of any retries before responding to the caller.
  
## Project structure

```
.
├── main.py                # Flask app: TemplateModel, admin CRUD, /send endpoint
├── config.py               # Environment-variable-based configuration
├── src/
│   ├── Create Database.py        # One-off script to create all DB tables
│   ├── extensions.py        # Shared SQLAlchemy `db` instance
│   ├── status.py             # Status and PossibleFailure enums
│   ├── SendEmail.py          # Email sending: auth, retry logic, logging
│   └── SendSMS.py            # SMS sending (not yet implemented)
├── Logs/
│   ├── LogModel.py           # NotificationLog database model
│   └── logs.py                # logs() helper used across the service
├── tests/
|    └── third_party_server(test).py      # Local mock of the third-party email API, for testing
├── instance/
|    └── templates.db      # Contains all the templates and logs
```

## Setup

### Requirements

- Python 3.10+
- `pip install flask flask-restful flask-sqlalchemy requests`

### Configuration

All configuration is read from environment variables, with local-testing defaults
baked in as fallbacks in `config.py` so the service runs out of the box against the
mock server below.

| Variable | Purpose | Local-testing default |
|---|---|---|
| `EMAIL_API_KEY` | API key for the email middleware | `test-api-key-abc123` |
| `BASE_URL` | Base URL of the email middleware | `http://127.0.0.1:6000` |
| `APP_NAME` | App name used to authenticate against the middleware | `test-app` |
| `APP_ID` | App ID used to authenticate against the middleware | `test-app-id-123` |
| `FROM` | Authorized sender email address | `test@example.com` |
| `MAX_RETRIES` | Max send attempts before giving up | `3` |
| `TIMEOUT` | Timeout, in seconds, for outbound HTTP calls | `5` |

Set real environment variables to override these when pointing at an actual
provider. The app validates that every required value is present at startup and
raises immediately if one is missing, rather than failing confusingly on the first
real request.

### Database

Create the SQLite database and its tables before running the app for the first time:

```
python Create_Database.py
```

This creates `templates.db` with two tables: `templates` and `notification_logs`.

### Running the service

```
python main.py
```

Runs on `http://127.0.0.1:5500` by default.

### Testing locally without real provider credentials

`third_party_server(test).py` simulates the third-party email middleware's `/auth/login`
and `/email/send` endpoints — same request/response shapes and header checks as the
real API, but nothing is actually sent anywhere. Run it on a separate port (`6000`
by default) alongside `main.py`; the default config already points `BASE_URL` at it.

```
python tests/third_party_server(test).py
```

It also accepts a special recipient, `trigger500@test.com`, which deliberately
returns a `500` — useful for exercising retry logic on demand without waiting for a
real failure.

## API

### Admin: Templates

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/templates` | List all templates |
| `POST` | `/admin/templates` | Create a template |
| `GET` | `/admin/templates/<id>` | Get one template |
| `PUT` | `/admin/templates/<id>` | Update a template (partial — only provided fields change) |
| `DELETE` | `/admin/templates/<id>` | Delete a template |

**Creating a template** — `POST /admin/templates`

```json
{
  "name": "OTP_VERIFICATION",
  "channel": "EMAIL",
  "subject": "Your verification code",
  "body": "Hi {{name}}, your code is {{otp}}.",
  "template_placeholders": "name,otp"
}
```

- `channel` must be `SMS` or `EMAIL` (case-insensitive on input; stored uppercase).
- `name` and `channel` together identify a template — the same name can exist once
  per channel, so an `EMAIL` and an `SMS` version of `OTP_VERIFICATION` can coexist.
- `subject` is optional and only meaningful for `EMAIL` templates.
- `template_placeholders` is a comma-separated list of the placeholder names used
  in `body` (and `subject`, for email) — placeholders in the body are written as
  `{{placeholder_name}}`.

### Sending a notification

`POST /send`

```json
{
  "name": "OTP_VERIFICATION",
  "channel": "EMAIL",
  "recipient": "someone@example.com",
  "placeholders": { "name": "Dami", "otp": "123456" },
  "isHTML": false
}
```

- Looks up the matching template by `name` + `channel`.
- Substitutes `placeholders` into the template's body (and subject, for email).
- Sends via the appropriate channel, retrying on transient failures per
  `MAX_RETRIES`.
- For `EMAIL`, `recipient` can be a comma-separated list of addresses.
- `isHTML` is optional and defaults to `false`.

## Failure handling & retries

Every send attempt is classified into one of:

- **Success** — logged, returned immediately.
- **`INPUT_ERROR`** — HTTP 400–499 (excluding 401). The request itself was invalid
  (e.g. a malformed body). Not retried, since an identical request will fail
  identically every time.
- **`PROVIDER_ERROR`** — HTTP 500+, connection errors, or timeouts. Retried up to
  `MAX_RETRIES` times, with a short delay between attempts.
- **`USER_ERROR`** — an authentication/token problem against the email middleware
  (expired or invalid credentials). On a `401`, the service automatically
  re-authenticates and retries with a fresh token.

Every individual attempt — success or failure, including each retry — is written to
`notification_logs` as its own row, so a single logical notification with two
retries produces three log rows, each with its own outcome and reason.

## Logging

Each row in `notification_logs` records:

| Field | Meaning |
|---|---|
| `recipient` | Who the notification was sent to |
| `channel` | `EMAIL` or `SMS` |
| `template_name` | Which template was used |
| `status` | `PENDING`, `PROCESSING`, `SUCCESS`, or `FAILED` |
| `failure_category` | `INPUT_ERROR`, `PROVIDER_ERROR`, `USER_ERROR`, or null on success |
| `response_code` | The HTTP status code returned by the provider (or a stand-in, e.g. `503`, if no response was ever received) |
| `failure_reason` | Human-readable detail on what went wrong |
| `created_at` | Timestamp of this attempt |
