# shiftr

Backend for Shiftr, a personal shift tracker and weekly working-hours calculator.

## Development

```powershell
.\venv\bin\python.exe -m pip install -r requirements.txt
.\venv\bin\python.exe manage.py migrate
.\venv\bin\python.exe manage.py runserver
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
