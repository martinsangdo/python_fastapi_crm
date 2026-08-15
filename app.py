"""
app.py
------
The main entry point of the FastAPI application.

It does the following:
1. Creates the FastAPI app.
2. Creates the database tables (if they do not exist yet).
3. Makes the "static" folder (CSS/JS) available to the browser.
4. Serves the HTML pages (home, login, dashboard) using Jinja2 templates.
5. Includes the authentication API router (all the /auth/* endpoints).
6. Shows one example of a PROTECTED API endpoint.
"""

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Import the database pieces and models so the tables can be created.
import models  # noqa: F401  (importing registers the User model on Base)
from database import Base, engine
from dependencies import get_current_user
from models import User
from routers import auth, customers, users
from schemas.auth_schemas import UserPublic

# Create the application instance.
app = FastAPI(title="CRM Authentication API")

# Create any missing tables described by our models (here: the users table).
# For a real project you would use migrations instead, but this keeps the
# beginner setup to a single command.
Base.metadata.create_all(bind=engine)

# Serve files inside the "static" folder (like style.css and auth.js).
app.mount("/static", StaticFiles(directory="static"), name="static")

# Tell FastAPI where to find our HTML templates.
templates = Jinja2Templates(directory="templates")

# Plug in all the /auth/* API routes defined in routers/auth.py.
app.include_router(auth.router)

# Plug in the Users administration API (/api/users, /api/roles, ...).
app.include_router(users.router)

# Plug in the Customers API (/api/customers).
app.include_router(customers.router)


# ---------------------------------------------------------------------------
# HTML pages (what a person sees in the browser)
# ---------------------------------------------------------------------------

@app.get("/")
def home(request: Request):
    """The public welcome page."""
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "title": "FastAPI CRM",
            "message": "Welcome! Head to the login page to sign in.",
        },
    )


@app.get("/login")
def login_page(request: Request):
    """The login page (an HTML form driven by static/auth.js)."""
    return templates.TemplateResponse(
        request, "login.html", {"title": "Log in"}
    )


@app.get("/register")
def register_page(request: Request):
    """The sign-up page (an HTML form driven by static/auth.js)."""
    return templates.TemplateResponse(
        request, "register.html", {"title": "Create account"}
    )


@app.get("/dashboard")
def dashboard_page(request: Request):
    """
    A protected page.

    Note: the *page itself* is plain HTML. The check that the visitor is
    logged in happens in the browser (static/auth.js): if there is no valid
    token, the script redirects to /login before showing anything useful.
    """
    return templates.TemplateResponse(
        request, "dashboard.html", {"title": "Dashboard"}
    )


# ---------------------------------------------------------------------------
# Users administration pages (HTML shells)
# ---------------------------------------------------------------------------
# These routes only SERVE the HTML. Just like /dashboard, each page's JavaScript
# checks the login token in the browser and then calls the /api/users API (which
# is where the real permission checks happen). Serving the shell to everyone is
# safe because the API refuses any request that lacks the right permission.

@app.get("/admin/users")
def users_list_page(request: Request):
    """The user list (table with search, filters, paging)."""
    return templates.TemplateResponse(
        request, "users/list.html", {"title": "Users"}
    )


@app.get("/admin/users/new")
def users_create_page(request: Request):
    """The create-user form."""
    return templates.TemplateResponse(
        request, "users/create.html", {"title": "New user"}
    )


@app.get("/admin/users/{user_id}")
def users_detail_page(request: Request, user_id: str):
    """The read-only detail view for one user."""
    return templates.TemplateResponse(
        request, "users/detail.html", {"title": "User detail", "user_id": user_id}
    )


@app.get("/admin/users/{user_id}/edit")
def users_edit_page(request: Request, user_id: str):
    """The edit form (name / role / active) plus a reset-password action."""
    return templates.TemplateResponse(
        request, "users/edit.html", {"title": "Edit user", "user_id": user_id}
    )


# ---------------------------------------------------------------------------
# Customers pages (HTML shells)
# ---------------------------------------------------------------------------
# Same pattern as the Users admin pages above: these routes only serve the
# HTML shell. Each page's JavaScript checks the login token in the browser
# and then calls the /api/customers API, which is where the real permission
# checks happen (customers.read/create/update/delete).

@app.get("/customers")
def customers_list_page(request: Request):
    """The customer list (table with search, filters, paging)."""
    return templates.TemplateResponse(
        request, "customers/list.html", {"title": "Customers"}
    )


@app.get("/customers/new")
def customers_create_page(request: Request):
    """The create-customer form."""
    return templates.TemplateResponse(
        request, "customers/create.html", {"title": "New customer"}
    )


@app.get("/customers/{customer_id}")
def customers_detail_page(request: Request, customer_id: str):
    """The read-only detail view for one customer."""
    return templates.TemplateResponse(
        request,
        "customers/detail.html",
        {"title": "Customer detail", "customer_id": customer_id},
    )


@app.get("/customers/{customer_id}/edit")
def customers_edit_page(request: Request, customer_id: str):
    """The edit form for one customer."""
    return templates.TemplateResponse(
        request,
        "customers/edit.html",
        {"title": "Edit customer", "customer_id": customer_id},
    )


# ---------------------------------------------------------------------------
# Example of a PROTECTED API endpoint
# ---------------------------------------------------------------------------

@app.get("/api/protected", response_model=UserPublic)
def protected_example(current_user: User = Depends(get_current_user)):
    """
    A sample endpoint that only works with a valid access token.

    `Depends(get_current_user)` does all the work: no token (or a bad one)
    means the caller never reaches this function and gets a 401 instead.
    """
    return current_user
