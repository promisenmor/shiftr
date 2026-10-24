# shiftr

Backend for Shiftr, a personal shift tracker and weekly working-hours calculator.

## Docker development

Copy the example environment file and set unique secret and database passwords:

```powershell
Copy-Item .env.example .env
```

Start the API and PostgreSQL:

```powershell
docker compose up --build
```

The API is available at `http://localhost:8000`. Django applies migrations when
the API container starts. PostgreSQL data is stored in the `postgres_data`
Docker volume and survives container restarts. To stop the services without
removing data, run `docker compose down`. Removing the volume with
`docker compose down --volumes` permanently deletes the database.

## Local development

PostgreSQL is the default database. To run Django directly, install
`requirements.txt`, provide the `DB_NAME`, `DB_USER`, `DB_PASSWORD`, and
`DB_HOST` environment variables, then run `python manage.py migrate`,
`python manage.py collectstatic --noinput`, and `python manage.py runserver`.

For tests without a local PostgreSQL server, select SQLite explicitly in
PowerShell:

```powershell
$env:DB_ENGINE = "django.db.backends.sqlite3"
$env:DB_NAME = ":memory:"
.\venv\bin\python.exe manage.py test
```

The API uses email/password authentication and JWT access/refresh tokens. Send
the access token on authenticated requests as
`Authorization: Bearer <access-token>`. Access tokens expire after 15 minutes;
refresh tokens expire after 7 days and rotate when refreshed.

## Phase One API

Interactive Swagger documentation is available at `/api/docs/`; the generated
OpenAPI schema is at `/api/schema/`. Shift and target endpoints require the
authenticated user's bearer access token. Logout accepts the current refresh
token in a `refresh` field; it does not immediately invalidate an already issued
access token, which remains valid until its short expiration.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/api/auth/register/` | Create an account and return an access/refresh token pair |
| POST | `/api/auth/login/` | Authenticate and return an access/refresh token pair |
| POST | `/api/auth/refresh/` | Exchange a refresh token for a rotated token pair |
| POST | `/api/auth/logout/` | Revoke the authenticated user's refresh token |
| GET, PATCH | `/api/profile/` | Read or update the authenticated user's display name |
| GET, POST | `/api/shifts/` | List or record shifts (`start_date` and `end_date` filters supported) |
| GET, PATCH, PUT, DELETE | `/api/shifts/{id}/` | Retrieve, edit, or delete an owned shift |
| GET | `/api/weekly-targets/` | List the user's saved weekly targets |
| PUT | `/api/weekly-targets/{week_start}/` | Set or change a target in minutes for a Monday-start week |
| GET | `/api/weeks/{week_start}/summary/` | Get weekly work, target, remaining time, overtime, and shifts |

Timed shifts accept `entry_mode: "timed"` with `start_at` and `end_at` ISO
date-times. Include the UTC offset for ambiguous daylight-saving times. For
example, an unpaid break can be sent as
`{"duration_minutes": 30, "is_paid": false}`. Exact break start/end times are
required when an unpaid break affects allocation across weekly boundaries.
Duration-only shifts use `entry_mode: "duration"`, `shift_date`, and a positive
`duration_minutes`; their work is allocated to the week containing that date.

Weeks run Monday through Sunday in `Europe/London`. The API derives all totals
from saved shifts: unpaid breaks are deducted, paid breaks count as work, and
overnight work is split at local Monday midnight. A new week's previous target
is returned as a suggestion only; saving a target for one week never changes
other weeks. Remaining time is clamped at zero, with overtime reported
separately. The same rules apply after a shift is edited or deleted.

Run the backend tests with:

```powershell
.\venv\bin\python.exe manage.py test
```
