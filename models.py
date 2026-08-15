"""
models.py
---------
The database tables, described as Python classes ("models").

We have these models:
  * `User`        — a person who can log in (the authentication module).
  * `Role`        — a named group a user belongs to, e.g. Admin / Manager / Sales.
  * `Permission`  — one thing that can be done, e.g. "customers.read".
  * `role_permissions` — the link table saying which permissions a role has.
  * `Customer`    — a company or individual the CRM sells to (Customers module).
  * `Address`     — a shipping address belonging to a customer.
  * `Category`    — a product category (Categories module).
  * `Product`     — an item in the catalog (Products module).
  * `Order`       — a sales order placed by a customer (Orders module).
  * `OrderItem`   — one product line on an order.

The first four make up "RBAC" (Role-Based Access Control). To answer "can this
user do X?" you follow: user -> role -> permissions.

Each class attribute becomes a column. SQLAlchemy turns these classes into
real SQL tables for us (see `Base.metadata.create_all(...)` in app.py). These
models mirror the tables in `sql/rbac.sql`, `sql/customers.sql`,
`sql/categories.sql`, `sql/products.sql` and `sql/orders.sql`.

NOTE on primary keys: `Customer`/`Category`/`Product`/`Order`/`OrderItem`/
`Address` map to tables that ALREADY EXISTED in this Supabase project (they
were not created by this app) with plain `BIGINT GENERATED ALWAYS AS IDENTITY`
primary keys, so those models use `Integer` ids rather than the UUID ids
used by the RBAC tables above.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


# ---------------------------------------------------------------------------
# role_permissions — the many-to-many link between roles and permissions
# ---------------------------------------------------------------------------
# This is a plain link table (no extra columns of its own), so we describe it
# with SQLAlchemy's `Table` helper rather than a full class. One row means
# "this role has this permission".
#
# The pair (role_id, permission_id) is the primary key, so the same permission
# cannot be attached to the same role twice. ON DELETE CASCADE means deleting a
# role or a permission automatically removes its link rows.
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class User(Base):
    """One row = one person who can log in to the CRM."""

    # The name of the real table created in the database.
    __tablename__ = "users"

    # A unique ID for every user. We use a UUID (a long random identifier)
    # instead of a plain number so IDs are not guessable.
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # The user's email. It must be unique (no two users share one) and we
    # add index=True so looking a user up by email stays fast.
    email = Column(String(255), unique=True, index=True, nullable=False)

    # The BCRYPT hash of the password. We NEVER store the real password.
    password_hash = Column(String(255), nullable=False)

    # The person's display name, shown in the UI after they log in.
    full_name = Column(String(255), nullable=False)

    # A simple on/off switch. Set to False to disable an account without
    # deleting it (a disabled user cannot log in).
    is_active = Column(Boolean, default=True, nullable=False)

    # When the account was created. The database fills this in automatically.
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # When the account was last changed. Updated automatically on every save.
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # The last time the user successfully logged in. Empty until their
    # first login, so this column is allowed to be NULL.
    last_login = Column(DateTime(timezone=True), nullable=True)

    # The role this user belongs to (Admin, Manager, Sales, ...). NULL is
    # allowed so a user can exist before a role is assigned. If the role is
    # deleted, this is set back to NULL (see ondelete="SET NULL") rather than
    # deleting the user.
    role_id = Column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # Convenience link to the full Role object. Lets you write `user.role`
    # instead of looking the role up by id yourself.
    role = relationship("Role", back_populates="users")

    def __repr__(self) -> str:
        # A friendly text version, handy when debugging in the console.
        return f"<User email={self.email!r} active={self.is_active}>"


class Role(Base):
    """One row = one named group of users (e.g. Admin, Manager, Sales)."""

    __tablename__ = "roles"

    # Random UUID primary key, generated in Python for each new row.
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Machine-friendly code used in application logic, e.g. 'ADMIN'. Unique so
    # it can be looked up reliably.
    code = Column(String(50), unique=True, nullable=False)

    # Human-friendly display name shown in the UI, e.g. 'Administrator'.
    name = Column(String(100), unique=True, nullable=False)

    # Optional longer explanation of what the role is for.
    description = Column(Text, nullable=True)

    # TRUE for roles that ship with the system (and should not be deleted by
    # users). FALSE for custom roles someone creates later.
    is_system = Column(Boolean, default=True, nullable=False)

    # When the role was created / last changed. The database fills these in.
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # All users who currently have this role.
    users = relationship("User", back_populates="role")

    # All permissions granted to this role, via the role_permissions link table.
    permissions = relationship(
        "Permission",
        secondary=role_permissions,
        back_populates="roles",
    )

    def __repr__(self) -> str:
        return f"<Role code={self.code!r}>"


class Permission(Base):
    """One row = one thing that can be done, e.g. "customers.read"."""

    __tablename__ = "permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # The feature area, e.g. 'customers', 'orders', 'reports'.
    module = Column(String(100), nullable=False)

    # The operation, e.g. 'read', 'create', 'update', 'delete', 'view'.
    action = Column(String(50), nullable=False)

    # The full permission string "module.action", e.g. 'customers.read'.
    # Unique so each permission exists exactly once — this is what the app checks.
    code = Column(String(150), unique=True, nullable=False)

    # Optional description of what the permission grants.
    description = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Every role that has been granted this permission.
    roles = relationship(
        "Role",
        secondary=role_permissions,
        back_populates="permissions",
    )

    def __repr__(self) -> str:
        return f"<Permission code={self.code!r}>"


class Customer(Base):
    """One row = one person who buys from us (the Customers module)."""

    __tablename__ = "customers"

    # This table already existed in Supabase with a plain, auto-incrementing
    # BIGINT id (not the UUID style the RBAC tables above use), so we map to
    # it exactly as it is rather than redefining it.
    id = Column(Integer, primary_key=True)

    # The one thing every customer must have, and how we contact them.
    # UNIQUE at the database level — see sql/customers.sql.
    email = Column(String, nullable=False, unique=True, index=True)
    full_name = Column(String, nullable=False, index=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # One customer can have many saved shipping addresses.
    addresses = relationship("Address", back_populates="customer")

    def __repr__(self) -> str:
        return f"<Customer email={self.email!r}>"


class Address(Base):
    """One row = one shipping address that belongs to a customer."""

    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True)

    # Deleting a customer deletes their saved addresses too (DB-enforced).
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    line1 = Column(Text, nullable=False)
    city = Column(Text, nullable=False)
    postal_code = Column(Text, nullable=False)
    country = Column(Text, nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)

    customer = relationship("Customer", back_populates="addresses")

    def __repr__(self) -> str:
        return f"<Address id={self.id} customer_id={self.customer_id}>"


class Category(Base):
    """One row = one product category (the Categories module)."""

    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    # URL-friendly unique identifier, e.g. "home-kitchen". Generated from
    # `name` in the service layer if the caller does not supply one.
    slug = Column(Text, nullable=False, unique=True, index=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    products = relationship("Product", back_populates="category")

    def __repr__(self) -> str:
        return f"<Category name={self.name!r} slug={self.slug!r}>"


class Product(Base):
    """One row = one item in the catalog (the Products module)."""

    __tablename__ = "products"

    id = Column(Integer, primary_key=True)

    # Every product belongs to exactly one category. A category with
    # products cannot be deleted (DB FK is ON DELETE RESTRICT).
    category_id = Column(
        Integer,
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    sku = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Money is stored as NUMERIC (Decimal in Python), never float, so prices
    # never suffer floating-point rounding errors.
    price = Column(Numeric(12, 2), nullable=False)

    stock_quantity = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    category = relationship("Category", back_populates="products")

    def __repr__(self) -> str:
        return f"<Product sku={self.sku!r} name={self.name!r}>"


class Order(Base):
    """One row = one sales order placed by a customer (the Orders module)."""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)

    # A customer with orders cannot be hard-deleted (DB FK is ON DELETE
    # RESTRICT) — see service/customers_service.py's delete guard.
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # One of "pending" | "paid" | "shipped" | "completed" | "cancelled"
    # (enforced in the service layer — see service/orders_service.py).
    status = Column(String, nullable=False, default="pending", index=True)

    # Optional: which of the customer's saved addresses to ship to. Kept if
    # the address is later removed (SET NULL), so the order itself survives.
    shipping_address_id = Column(
        Integer,
        ForeignKey("addresses.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Always the sum of item line totals, recomputed server-side on every
    # write — never trusted from the client.
    total_amount = Column(Numeric(12, 2), nullable=False, default=0)

    placed_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    customer = relationship("Customer")
    shipping_address = relationship("Address")
    # Deleting an order deletes its line items too (DB-enforced CASCADE);
    # `cascade="all, delete-orphan"` keeps the Python side in sync.
    items = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItem.id",
    )

    def __repr__(self) -> str:
        return f"<Order id={self.id} status={self.status!r}>"


class OrderItem(Base):
    """One row = one product line on an order (quantity + snapshot price)."""

    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)

    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # A product referenced by an order line cannot be hard-deleted (DB FK is
    # ON DELETE RESTRICT) — see service/products_service.py's delete guard.
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    quantity = Column(Integer, nullable=False)

    # Snapshot of the product's price AT ORDER TIME, so later catalog price
    # changes never rewrite the history of an already-placed order.
    unit_price = Column(Numeric(12, 2), nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")

    def __repr__(self) -> str:
        return f"<OrderItem order_id={self.order_id} product_id={self.product_id}>"
