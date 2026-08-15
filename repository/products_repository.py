"""
products_repository.py
-----------------------
The "data access" layer for the Products module.

Every function here does ONE thing: talk to the database (through a
SQLAlchemy session) and hand back plain SQLAlchemy objects. There is no
business logic and no HTTP knowledge — same shape as customers_repository.py.
"""

from typing import Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from models import OrderItem, Product

# The columns a client is allowed to sort by. Anything not in this dict falls
# back to "created_at", so a bad/unknown sort value can never crash the query.
_SORTABLE_COLUMNS = {
    "name": Product.name,
    "price": Product.price,
    "stock_quantity": Product.stock_quantity,
    "created_at": Product.created_at,
}


def list_products(
    db: Session,
    *,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    in_stock: Optional[bool] = None,
    min_price=None,
    max_price=None,
    sort: str = "created_at",
    order: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> Tuple[list[Product], int]:
    """
    Return one page of products plus the TOTAL number that matched the
    filters.

    Filtering:
      - search:      matches name OR sku (case-insensitive, partial).
      - category_id: only products in that category.
      - is_active:   only active (or only inactive) products.
      - in_stock:    only products with stock_quantity > 0.
      - min_price/max_price: inclusive price range.
    """
    query = db.query(Product)

    if search:
        like = f"%{search.strip()}%"
        query = query.filter(or_(Product.name.ilike(like), Product.sku.ilike(like)))

    if category_id is not None:
        query = query.filter(Product.category_id == category_id)

    if is_active is not None:
        query = query.filter(Product.is_active == is_active)

    if in_stock:
        query = query.filter(Product.stock_quantity > 0)

    if min_price is not None:
        query = query.filter(Product.price >= min_price)

    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    total = query.count()

    column = _SORTABLE_COLUMNS.get(sort, Product.created_at)
    query = query.order_by(column.asc() if order == "asc" else column.desc())

    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = query.offset((page - 1) * page_size).limit(page_size).all()

    return rows, total


def get_product(db: Session, product_id) -> Optional[Product]:
    """Load one product (with its category eager-loaded) by id."""
    return (
        db.query(Product)
        .options(joinedload(Product.category))
        .filter(Product.id == product_id)
        .first()
    )


def get_product_by_sku(db: Session, sku: str) -> Optional[Product]:
    """Look up a product by its unique SKU (used to check for duplicates)."""
    return db.query(Product).filter(Product.sku == sku).first()


def count_order_items(db: Session, product_id) -> int:
    """How many order lines still reference this product (blocks delete if > 0)."""
    return db.query(OrderItem).filter(OrderItem.product_id == product_id).count()


def add_product(db: Session, product: Product) -> Product:
    """Persist a brand-new product and reload it (fills in id/created_at)."""
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def save(db: Session, product: Product) -> Product:
    """Write pending changes on an existing product back to the database."""
    db.commit()
    db.refresh(product)
    return product


def delete_product(db: Session, product: Product) -> None:
    """Permanently remove a product row (a hard delete)."""
    db.delete(product)
    db.commit()
