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
from routers import auth, categories, customers, dashboard, orders, products, public_tasks, users
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

# Plug in the Categories API (/api/categories).
app.include_router(categories.router)

# Plug in the Products API (/api/products).
app.include_router(products.router)

# Plug in the Orders API (/api/orders).
app.include_router(orders.router)

# Plug in the Dashboard API (/api/dashboard/stats).
app.include_router(dashboard.router)

# Plug in the public, API-key-protected task endpoints (/api/public/tasks/...).
app.include_router(public_tasks.router)


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
# Categories pages (HTML shells)
# ---------------------------------------------------------------------------
# Same pattern as the Customers pages above: these routes only serve the HTML
# shell. Each page's JavaScript checks the login token in the browser and
# then calls the /api/categories API, where the real permission checks
# happen (categories.read/create/update/delete).

@app.get("/categories")
def categories_list_page(request: Request):
    """The category list (table with search, sort, paging)."""
    return templates.TemplateResponse(
        request, "categories/list.html", {"title": "Categories"}
    )


@app.get("/categories/new")
def categories_create_page(request: Request):
    """The create-category form."""
    return templates.TemplateResponse(
        request, "categories/create.html", {"title": "New category"}
    )


@app.get("/categories/{category_id}")
def categories_detail_page(request: Request, category_id: str):
    """The read-only detail view for one category."""
    return templates.TemplateResponse(
        request,
        "categories/detail.html",
        {"title": "Category detail", "category_id": category_id},
    )


@app.get("/categories/{category_id}/edit")
def categories_edit_page(request: Request, category_id: str):
    """The edit form for one category."""
    return templates.TemplateResponse(
        request,
        "categories/edit.html",
        {"title": "Edit category", "category_id": category_id},
    )


# ---------------------------------------------------------------------------
# Products pages (HTML shells)
# ---------------------------------------------------------------------------

@app.get("/products")
def products_list_page(request: Request):
    """The product list (table with search, filters, paging)."""
    return templates.TemplateResponse(
        request, "products/list.html", {"title": "Products"}
    )


@app.get("/products/new")
def products_create_page(request: Request):
    """The create-product form."""
    return templates.TemplateResponse(
        request, "products/create.html", {"title": "New product"}
    )


@app.get("/products/{product_id}")
def products_detail_page(request: Request, product_id: str):
    """The read-only detail view for one product."""
    return templates.TemplateResponse(
        request,
        "products/detail.html",
        {"title": "Product detail", "product_id": product_id},
    )


@app.get("/products/{product_id}/edit")
def products_edit_page(request: Request, product_id: str):
    """The edit form for one product."""
    return templates.TemplateResponse(
        request,
        "products/edit.html",
        {"title": "Edit product", "product_id": product_id},
    )


# ---------------------------------------------------------------------------
# Orders pages (HTML shells)
# ---------------------------------------------------------------------------

@app.get("/orders")
def orders_list_page(request: Request):
    """The order list (table with search, filters, paging)."""
    return templates.TemplateResponse(
        request, "orders/list.html", {"title": "Orders"}
    )


@app.get("/orders/new")
def orders_create_page(request: Request):
    """The create-order form (customer + line items)."""
    return templates.TemplateResponse(
        request, "orders/create.html", {"title": "New order"}
    )


@app.get("/orders/{order_id}")
def orders_detail_page(request: Request, order_id: str):
    """The order detail view (header, line items, status control)."""
    return templates.TemplateResponse(
        request, "orders/detail.html", {"title": "Order detail", "order_id": order_id}
    )


@app.get("/orders/{order_id}/edit")
def orders_edit_page(request: Request, order_id: str):
    """The edit form for a pending order's address/line items."""
    return templates.TemplateResponse(
        request, "orders/edit.html", {"title": "Edit order", "order_id": order_id}
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
