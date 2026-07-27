# FastAPI CRM — Authentication

A minimal full-stack **CRM authentication module** built with **FastAPI**,
**SQLAlchemy**, **Jinja2 templates**, and plain **HTML/CSS/JavaScript**, backed
by **PostgreSQL** (Supabase compatible).

It covers **authentication only** — register, login, logout, "who am I", and
change password — using **bcrypt** password hashing and **JWT** access/refresh
tokens. There are no roles or permissions yet, by design.

---

## Folder Structure

```
python_fastapi_crm/
│
├── app.py               # FastAPI app: HTML pages + wires in the auth router
├── database.py          # SQLAlchemy engine, session, Base, get_db() dependency
├── models.py            # SQLAlchemy models (the User table)
├── schemas.py           # Pydantic request/response schemas
├── security.py          # Password hashing (bcrypt) + JWT create/decode helpers
├── auth_service.py      # Business logic: register, authenticate, change password
├── dependencies.py      # get_current_user() — the auth dependency (verifies JWT)
│
├── routers/
│   └── auth.py          # All /auth/* API endpoints
│
├── sql/
│   └── users.sql        # CREATE TABLE script, indexes, trigger + seed user
│
├── templates/
│   ├── index.html       # Public welcome page
│   ├── login.html       # Login form
│   └── dashboard.html   # Protected page — shows the logged-in user's name
│
├── static/
│   ├── style.css        # Styles
│   └── auth.js          # Token storage, login/logout, redirect-if-logged-out
│
├── requirements.txt     # Python dependencies
├── .env.example         # Template for DATABASE_URL + JWT settings
└── README.md            # This file
```

---

## How authentication works (the short version)

1. A user **registers** or **logs in** with email + password.
2. The server checks the password against a **bcrypt hash** and, on success,
   returns two **JWTs**: a short-lived **access token** and a longer-lived
   **refresh token**.
3. The browser stores both tokens and sends the access token on every request
   as an `Authorization: Bearer <token>` header.
4. Protected endpoints use the `get_current_user` dependency, which decodes the
   token, loads the user, and rejects anything invalid with **401**.
5. When the access token expires, the client calls `/auth/refresh` to get a new
   pair without re-entering the password.

---

## API Documentation

Base URL: `http://127.0.0.1:8000`. Interactive docs are auto-generated at
`/docs` (Swagger UI) and `/redoc`.

| Method | Path                    | Auth?  | Description                              |
|--------|-------------------------|--------|------------------------------------------|
| POST   | `/auth/register`        | No     | Create a new account.                    |
| POST   | `/auth/login`           | No     | Get an access + refresh token pair.      |
| POST   | `/auth/refresh`         | No\*   | Swap a refresh token for a new pair.     |
| POST   | `/auth/logout`          | Yes    | Confirms logout (client discards tokens).|
| GET    | `/auth/me`              | Yes    | The current logged-in user.              |
| POST   | `/auth/change-password` | Yes    | Change the current user's password.      |
| GET    | `/api/protected`        | Yes    | Example protected endpoint.              |

\* `/auth/refresh` needs a valid **refresh** token in the body, not the header.

"Auth? = Yes" means the request must include the header
`Authorization: Bearer <access_token>`.

### Examples (using `curl`)

**Register**
```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"jane@example.com","full_name":"Jane Doe","password":"Password123!"}'
```

**Login** (returns `access_token` and `refresh_token`)
```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"jane@example.com","password":"Password123!"}'
```

**Get current user** (replace `TOKEN` with the access token)
```bash
curl http://127.0.0.1:8000/auth/me \
  -H "Authorization: Bearer TOKEN"
```

**Change password**
```bash
curl -X POST http://127.0.0.1:8000/auth/change-password \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"Password123!","new_password":"NewPassword456!"}'
```

**Refresh tokens**
```bash
curl -X POST http://127.0.0.1:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"REFRESH_TOKEN"}'
```

### Error responses

Errors come back as JSON: `{"detail": "..."}`.

| Status | When                                             |
|--------|--------------------------------------------------|
| 400    | Bad request (e.g. wrong current password).       |
| 401    | Bad login, or missing/expired/invalid token.     |
| 403    | The account is disabled (`is_active = false`).   |
| 409    | Registering an email that already exists.        |
| 422    | Input failed validation (bad email, short pass). |

---

## Setup

### Required software

- **Python 3.10+**
- A **PostgreSQL** database — a local install or a free
  [Supabase](https://supabase.com) project both work.

### 1. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate          # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and set:

- `DATABASE_URL` — your PostgreSQL/Supabase connection string
  (`postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE`).
- `JWT_SECRET_KEY` — a long random secret. Generate one with:

  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```

The `.env` file holds secrets and must **not** be committed to git.

### 3. Create the database table

You have two options — pick one:

- **Automatic (default):** just run the app. On startup `app.py` calls
  `Base.metadata.create_all(...)`, which creates the `users` table if it is
  missing.
- **Manual / with a seed user:** run [`sql/users.sql`](sql/users.sql) in your
  database (for Supabase, paste it into the SQL editor). This also inserts a
  ready-to-use seed account:
  - **Email:** `admin@example.com`
  - **Password:** `Password123!`

### 4. Run the development server

```bash
uvicorn app:app --reload
```

Then open:

- Home page: `http://127.0.0.1:8000/`
- Login page: `http://127.0.0.1:8000/login`
- API docs: `http://127.0.0.1:8000/docs`

Log in on the `/login` page (use the seed account if you loaded the SQL) and
you will be redirected to the protected `/dashboard`, which greets you by name.

---

## Database schema

The `users` table (see [`sql/users.sql`](sql/users.sql) and
[`models.py`](models.py)):

| Column          | Type          | Notes                                    |
|-----------------|---------------|------------------------------------------|
| `id`            | `UUID`        | Primary key, random default.             |
| `email`         | `VARCHAR(255)`| **Unique**, indexed, required.           |
| `password_hash` | `VARCHAR(255)`| Bcrypt hash — never the plain password.  |
| `full_name`     | `VARCHAR(255)`| Required.                                |
| `is_active`     | `BOOLEAN`     | Default `true`; `false` disables login.  |
| `created_at`    | `TIMESTAMPTZ` | Set automatically on insert.             |
| `updated_at`    | `TIMESTAMPTZ` | Refreshed automatically on update.       |
| `last_login`    | `TIMESTAMPTZ` | Nullable; set on each successful login.  |

---

## A note on token storage & security

- **Passwords** are hashed with **bcrypt** (a salted, slow hash). The plain
  password is never stored or logged.
- **Access tokens** are short-lived (default 30 min); **refresh tokens** last
  longer (default 7 days). Both are configurable in `.env`.
- The frontend stores tokens in **`localStorage`** for simplicity. This is easy
  to follow but readable by JavaScript, so it is exposed to XSS. For a
  production app, prefer storing the token in an **httpOnly cookie** that
  scripts cannot read, and serve the app over **HTTPS**.
- Because JWTs are stateless, `/auth/logout` cannot truly "kill" a token
  server-side; the client simply discards it. Add a token blocklist if you need
  hard server-side logout.

---

## Not included (yet)

By request, this module is **authentication only** — no roles, no permissions,
and no other CRM business logic. Those can be layered on top later.
