# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A deliberately minimal, beginner-oriented FastAPI full-stack starter: FastAPI + Jinja2 server-rendered templates + plain HTML/CSS, wired to PostgreSQL (Supabase compatible) via SQLAlchemy. It is a **scaffold only** — there are no models, tables, schemas, CRUD, or business logic yet. Do not add those until explicitly asked. Code and comments are intentionally verbose and explanatory for a learning audience; match that beginner-friendly commenting style when extending files.

## Commands

```bash
# One-time setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then set DATABASE_URL

# Run the dev server (auto-reload) at http://127.0.0.1:8000
uvicorn app:app --reload
```

There are no tests, linters, or build steps configured.

## Architecture

- `app.py` — the FastAPI app. Mounts `/static` for CSS, configures the Jinja2 `templates/` directory, and defines routes. `TemplateResponse` takes `request` as the first argument and passes a context dict to the template.
- `database.py` — SQLAlchemy setup only. Exposes `engine`, `SessionLocal`, `Base` (parent for future models), and a `get_db()` dependency generator. It is **not imported by `app.py` yet** and creates no tables. `DATABASE_URL` (format `postgresql+psycopg://USER:PASS@HOST:PORT/DB`) is read from `.env` via `python-dotenv`.
- `templates/` — Jinja2 pages. `index.html` is the live home page; `test_homepage.html` is a scratch file.
- `static/style.css` — the single stylesheet.

When you add persistence: define models on `Base`, wire tables in `app.py` (currently `database.py` is unused), and inject sessions into routes with `Depends(get_db)`.

## CNN design system (`cnn-design-system/`)

Reference design tokens extracted from CNN's live homepage — a three-layer Style-Dictionary pipeline (primitive → semantic → theme/component). `01-theme.md` (color), `02-tokens.md` (8px spacing/sizing scale, type, radius), `03-style.md` (visual language). When building UI intended to match this look: near-black ink (`#0c0c0c`) on white, CNN red (`#cc0000`) reserved for logo/breaking/CTA accents only, square editorial blocks (`radius-none`), hierarchy via type + 8px-grid spacing rather than color. These are guidance docs, not wired into the app's CSS.

