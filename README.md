# FastAPI Starter

A minimal full-stack web application built with **FastAPI**, **Jinja2 templates**, and plain **HTML/CSS**. It connects to a **PostgreSQL** database (Supabase compatible) and shows a simple "Hello World" welcome page.

This is a clean starting point only — there are no database tables, models, or business logic yet.

---

## Folder Structure

```
python_fastapi_crm/
│
├── app.py              # Main application: routes and page rendering
├── database.py         # PostgreSQL connection setup (no tables yet)
├── requirements.txt    # Python packages this project needs
├── .env.example        # Template for your environment variables
├── README.md           # This file
│
├── templates/
│   └── index.html      # The welcome page (HTML template)
│
└── static/
    └── style.css       # Styles for the welcome page
```

### What each file does

- **app.py** — Creates the FastAPI app, serves the CSS folder, and renders the home page.
- **database.py** — Sets up the SQLAlchemy engine and session so the app is ready to use PostgreSQL later.
- **requirements.txt** — The list of libraries to install.
- **.env.example** — A copy-me template for secret settings like the database URL.
- **templates/index.html** — The single HTML page shown at `/`.
- **static/style.css** — The single stylesheet for the page.

---

## Required Software

- **Python 3.10+**
- **pip** (comes with Python)
- A **PostgreSQL** database — a local install or a free [Supabase](https://supabase.com) project both work.

---

## Installation

1. **(Recommended) Create and activate a virtual environment**

   ```bash
   python3 -m venv venv
   source venv/bin/activate    # On Windows: venv\Scripts\activate
   ```

2. **Install the dependencies**

   ```bash
   pip install -r requirements.txt
   ```

---

## Environment Variables

1. Copy the example file to create your own `.env`:

   ```bash
   cp .env.example .env
   ```

2. Open `.env` and set `DATABASE_URL` to your PostgreSQL or Supabase connection string:

   ```
   DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE
   ```

   The `.env` file holds secrets and should **not** be committed to git.

---

## Running the Application

Start the development server with:

```bash
uvicorn app:app --reload
```

Then open your browser to:

```
http://127.0.0.1:8000
```

You should see the "Hello World" welcome page. The `--reload` flag restarts the server automatically whenever you change the code.
