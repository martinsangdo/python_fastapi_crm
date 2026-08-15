"""
products_service.py
--------------------
The "business logic" of the Products module.

These functions enforce the module's RULES (unique SKU, valid category,
non-negative price/stock, delete blocked while order lines reference the
product) and talk to the database through products_repository.py. They know
NOTHING about HTTP — instead they raise clear, typed errors that the router
turns into the right status code:
  * NotFoundError      -> the router returns 404 (unknown product/category)
  * BusinessRuleError  -> the router returns 400
  * ConflictError      -> the router returns 409 (duplicate SKU, or a delete
                           blocked by existing order lines)
"""

from typing import Optional

from sqlalchemy.orm import Session

import repository.categories_repository as categories_repo
import repository.products_repository as repo
from models import Product
from schemas.products_schemas import CategorySummary, ProductCreate, ProductDetail, ProductUpdate


# ---------------------------------------------------------------------------
# Typed errors — the router maps each of these to an HTTP status code.
# ---------------------------------------------------------------------------

class NotFoundError(Exception):
    """Raised when the requested product (or category) does not exist."""


class BusinessRuleError(Exception):
    """Raised when a request is understood but breaks a module rule."""


class ConflictError(Exception):
    """Raised on a duplicate SKU, or deleting a product still in use."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def to_detail(product: Product) -> ProductDetail:
    """Build the full detail view of a product, including its category."""
    return ProductDetail(
        id=product.id,
        sku=product.sku,
        name=product.name,
        description=product.description,
        price=product.price,
        stock_quantity=product.stock_quantity,
        is_active=product.is_active,
        category=CategorySummary.model_validate(product.category),
        created_at=product.created_at,
    )


def _resolve_category(db: Session, category_id) -> None:
    """Raise NotFoundError if category_id does not point at a real category."""
    if categories_repo.get_category(db, category_id) is None:
        raise NotFoundError("The selected category does not exist.")


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_product_or_404(db: Session, product_id) -> Product:
    """Load a product, or raise NotFoundError if there is none with that id."""
    product = repo.get_product(db, product_id)
    if product is None:
        raise NotFoundError("Product not found.")
    return product


def list_products(
    db: Session,
    *,
    search: Optional[str],
    category_id: Optional[int],
    is_active: Optional[bool],
    in_stock: Optional[bool],
    min_price,
    max_price,
    sort: str,
    order: str,
    page: int,
    page_size: int,
):
    """Return (rows, total) for a page of products. Filtering lives in the repo."""
    return repo.list_products(
        db,
        search=search,
        category_id=category_id,
        is_active=is_active,
        in_stock=in_stock,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_product(db: Session, data: ProductCreate) -> Product:
    """
    Create a product.

    SKU is normalized to uppercase/trimmed and must be unique. Category must
    already exist. Price and stock are validated non-negative by the schema.
    """
    sku = data.sku.strip().upper()
    if not sku:
        raise BusinessRuleError("SKU is required.")

    name = data.name.strip()
    if not name:
        raise BusinessRuleError("Name is required.")

    _resolve_category(db, data.category_id)

    if repo.get_product_by_sku(db, sku) is not None:
        raise ConflictError(f"A product with SKU '{sku}' already exists.")

    product = Product(
        category_id=data.category_id,
        sku=sku,
        name=name,
        description=data.description,
        price=data.price,
        stock_quantity=data.stock_quantity,
        is_active=data.is_active,
    )
    product = repo.add_product(db, product)
    # Reload with the category relationship eager-loaded for to_detail().
    return repo.get_product(db, product.id)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def update_product(db: Session, product_id, data: ProductUpdate) -> Product:
    """
    Apply a partial update to a product.

    Only the fields actually sent are touched (Pydantic's exclude_unset). If
    the SKU changes, uniqueness is re-checked; if the category changes, it
    must still point at a real category.
    """
    product = get_product_or_404(db, product_id)
    changes = data.model_dump(exclude_unset=True)

    if "category_id" in changes:
        _resolve_category(db, changes["category_id"])
        product.category_id = changes["category_id"]

    if "sku" in changes:
        sku = (changes["sku"] or "").strip().upper()
        if not sku:
            raise BusinessRuleError("SKU is required.")
        if sku != product.sku and repo.get_product_by_sku(db, sku) is not None:
            raise ConflictError(f"A product with SKU '{sku}' already exists.")
        product.sku = sku

    if "name" in changes:
        name = (changes["name"] or "").strip()
        if not name:
            raise BusinessRuleError("Name is required.")
        product.name = name

    for field in ("description", "price", "stock_quantity", "is_active"):
        if field in changes:
            setattr(product, field, changes[field])

    repo.save(db, product)
    return repo.get_product(db, product.id)


def set_active(db: Session, product_id, is_active: bool) -> Product:
    """Activate or deactivate a product (used by the list page's toggle action)."""
    product = get_product_or_404(db, product_id)
    product.is_active = is_active
    repo.save(db, product)
    return repo.get_product(db, product.id)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_product(db: Session, product_id) -> None:
    """
    Permanently remove a product.

    Blocked (409) while any order line still references it — matches the
    database's own ON DELETE RESTRICT foreign key. Deactivating the product
    instead preserves order history while hiding it from new orders.
    """
    product = get_product_or_404(db, product_id)
    in_use = repo.count_order_items(db, product_id)
    if in_use > 0:
        raise ConflictError(
            f"Cannot delete '{product.name}': it appears on {in_use} order line(s). "
            "Deactivate it instead."
        )
    repo.delete_product(db, product)
