"""
app.py
------
The main entry point of the FastAPI application.

It does three simple things:
1. Creates the FastAPI app.
2. Makes the "static" folder (CSS) available to the browser.
3. Shows a "Hello World" welcome page using a Jinja2 template.
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Create the application instance.
app = FastAPI()

# Serve files inside the "static" folder (like style.css) at the "/static" URL.
app.mount("/static", StaticFiles(directory="static"), name="static")

# Tell FastAPI where to find our HTML templates.
templates = Jinja2Templates(directory="templates")


@app.get("/")
def home(request: Request):
    """
    Handle requests to the home page ("/").

    We render "index.html" and pass in some values the template can display.
    The "request" object must be the first argument.
    """
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "title": "FastAPI Starter",
            "message": "Hello World! Your FastAPI app is running.",
        },
    )
