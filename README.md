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

The API uses email/password authentication and DRF token authentication. Send the
returned token on authenticated requests as `Authorization: Token <token>`.

## Phase One API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/api/auth/register/` | Create an account and return its token |
| POST | `/api/auth/login/` | Authenticate and return a token |
| POST | `/api/auth/logout/` | Revoke the current token |
| GET, PATCH | `/api/profile/` | Read or update the authenticated user's display name |

The initial schema also defines user-owned weekly targets, shifts, and breaks.
Shift CRUD, target endpoints, and weekly calculations are the next backend
milestone; weekly calculations use Monday-to-Monday weeks in `Europe/London`.

Run the backend tests with:

```powershell
.\venv\bin\python.exe manage.py test
```
