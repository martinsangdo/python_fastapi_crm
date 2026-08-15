"""
categories_service.py
----------------------
The "business logic" of the Categories module.

These functions enforce the module's RULES (required name, unique slug,
delete blocked while products still use the category) and talk to the
database through categories_repository.py. They know NOTHING about HTTP —
instead they raise clear, typed errors that the router turns into the right
status code:
  * NotFoundError      -> the router returns 404
  * BusinessRuleError  -> the router returns 400 (e.g. a slug that can't be
                           derived from an empty name)
  * ConflictError      -> the router returns 409 (duplicate slug, or a
                           delete blocked by products still using it)
"""

import re
from typing import Optional

from sqlalchemy.orm import Session

import repository.categories_repository as repo
from models import Category
from schemas.categories_schemas import CategoryCreate, CategoryDetail, CategoryUpdate


# ---------------------------------------------------------------------------
# Typed errors — the router maps each of these to an HTTP status code.
# ---------------------------------------------------------------------------

class NotFoundError(Exception):
    """Raised when the requested category does not exist."""


class BusinessRuleError(Exception):
    """Raised when a request is understood but breaks a module rule."""


class ConflictError(Exception):
    """Raised on a duplicate slug, or deleting a category still in use."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(value: str) -> str:
    """Turn "Home & Kitchen" into "home-kitchen" — lowercase, dash-separated."""
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def to_detail(db: Session, category: Category) -> CategoryDetail:
    """Build the full detail view of a category, including its product count."""
    return CategoryDetail(
        id=category.id,
        name=category.name,
        slug=category.slug,
        product_count=repo.count_products(db, category.id),
        created_at=category.created_at,
    )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_category_or_404(db: Session, category_id) -> Category:
    """Load a category, or raise NotFoundError if there is none with that id."""
    category = repo.get_category(db, category_id)
    if category is None:
        raise NotFoundError("Category not found.")
    return category


def list_categories(
    db: Session,
    *,
    search: Optional[str],
    sort: str,
    order: str,
    page: int,
    page_size: int,
):
    """Return (rows, total) for a page of categories. Filtering lives in the repo."""
    return repo.list_categories(
        db, search=search, sort=sort, order=order, page=page, page_size=page_size
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_category(db: Session, data: CategoryCreate) -> Category:
    """
    Create a category.

    The name is trimmed and must be non-empty. The slug is either the caller's
    (normalized through the same slugify rules) or derived from the name when
    omitted, and must be unique.
    """
    name = data.name.strip()
    if not name:
        raise BusinessRuleError("Name is required.")

    slug = _slugify(data.slug) if data.slug else _slugify(name)
    if not slug:
        raise BusinessRuleError(
            "Could not derive a URL slug from that name; please provide one."
        )
    if repo.get_category_by_slug(db, slug) is not None:
        raise ConflictError(f"A category with slug '{slug}' already exists.")

    category = Category(name=name, slug=slug)
    return repo.add_category(db, category)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def update_category(db: Session, category_id, data: CategoryUpdate) -> Category:
    """
    Apply a partial update to a category.

    Only the fields actually sent are touched (Pydantic's exclude_unset).
    """
    category = get_category_or_404(db, category_id)
    changes = data.model_dump(exclude_unset=True)

    if "name" in changes:
        name = (changes["name"] or "").strip()
        if not name:
            raise BusinessRuleError("Name is required.")
        category.name = name

    if "slug" in changes:
        slug = _slugify(changes["slug"]) if changes["slug"] else _slugify(category.name)
        if not slug:
            raise BusinessRuleError(
                "Could not derive a URL slug from that name; please provide one."
            )
        if slug != category.slug and repo.get_category_by_slug(db, slug) is not None:
            raise ConflictError(f"A category with slug '{slug}' already exists.")
        category.slug = slug

    return repo.save(db, category)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_category(db: Session, category_id) -> None:
    """
    Permanently remove a category.

    Blocked (409) while any product still references it — matches the
    database's own ON DELETE RESTRICT foreign key.
    """
    category = get_category_or_404(db, category_id)
    in_use = repo.count_products(db, category_id)
    if in_use > 0:
        raise ConflictError(
            f"Cannot delete '{category.name}': {in_use} product(s) still use this category."
        )
    repo.delete_category(db, category)
