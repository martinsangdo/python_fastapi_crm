"""
categories_repository.py
-------------------------
The "data access" layer for the Categories module.

Every function here does ONE thing: talk to the database (through a
SQLAlchemy session) and hand back plain SQLAlchemy objects. There is no
business logic and no HTTP knowledge — same shape as customers_repository.py.
"""

from typing import Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import Category, Product

# The columns a client is allowed to sort by. Anything not in this dict falls
# back to "created_at", so a bad/unknown sort value can never crash the query.
_SORTABLE_COLUMNS = {
    "name": Category.name,
    "slug": Category.slug,
    "created_at": Category.created_at,
}


def list_categories(
    db: Session,
    *,
    search: Optional[str] = None,
    sort: str = "created_at",
    order: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> Tuple[list[Category], int]:
    """Return one page of categories plus the TOTAL number that matched."""
    query = db.query(Category)

    if search:
        like = f"%{search.strip()}%"
        query = query.filter(
            or_(Category.name.ilike(like), Category.slug.ilike(like))
        )

    total = query.count()

    column = _SORTABLE_COLUMNS.get(sort, Category.created_at)
    query = query.order_by(column.asc() if order == "asc" else column.desc())

    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = query.offset((page - 1) * page_size).limit(page_size).all()

    return rows, total


def get_category(db: Session, category_id) -> Optional[Category]:
    """Load one category by id (or None if there is no such category)."""
    return db.query(Category).filter(Category.id == category_id).first()


def get_category_by_slug(db: Session, slug: str) -> Optional[Category]:
    """Look up a category by its unique slug (used to check for duplicates)."""
    return db.query(Category).filter(Category.slug == slug).first()


def count_products(db: Session, category_id) -> int:
    """How many products still reference this category (blocks delete if > 0)."""
    return db.query(Product).filter(Product.category_id == category_id).count()


def add_category(db: Session, category: Category) -> Category:
    """Persist a brand-new category and reload it (fills in id/created_at)."""
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def save(db: Session, category: Category) -> Category:
    """Write pending changes on an existing category back to the database."""
    db.commit()
    db.refresh(category)
    return category


def delete_category(db: Session, category: Category) -> None:
    """Permanently remove a category row (a hard delete)."""
    db.delete(category)
    db.commit()
