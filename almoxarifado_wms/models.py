from datetime import datetime, timezone
from decimal import Decimal
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Branch(db.Model):
    __tablename__ = "branches"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

class Warehouse(db.Model):
    __tablename__ = "warehouses"
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    branch = db.relationship("Branch", backref="warehouses")
    __table_args__ = (db.UniqueConstraint("branch_id", "code"),)

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="operator", nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"))
    active = db.Column(db.Boolean, default=True, nullable=False)
    branch = db.relationship("Branch")
    def set_password(self, value): self.password_hash = generate_password_hash(value)
    def check_password(self, value): return check_password_hash(self.password_hash, value)
    def can(self, *roles): return self.role in roles

class Party(db.Model):
    __tablename__ = "parties"
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), default="EMPLOYEE", nullable=False)
    document = db.Column(db.String(30))
    name = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(180))
    phone = db.Column(db.String(40))
    active = db.Column(db.Boolean, default=True, nullable=False)

class Item(db.Model):
    __tablename__ = "items"
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(80))
    # Estado de conservação: separado do saldo de estoque e da disponibilidade do patrimônio.
    condition = db.Column(db.String(20), default="UNSPECIFIED", nullable=False)
    item_type = db.Column(db.String(20), nullable=False)  # STOCK/EQUIPMENT
    unit = db.Column(db.String(10), default="UN", nullable=False)
    minimum_stock = db.Column(db.Numeric(14, 3), default=0, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

class Asset(db.Model):
    __tablename__ = "assets"
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False)
    asset_tag = db.Column(db.String(60), unique=True, nullable=False)
    serial_number = db.Column(db.String(100))
    status = db.Column(db.String(30), default="AVAILABLE", nullable=False)
    condition = db.Column(db.String(30), default="GOOD", nullable=False)
    daily_rate = db.Column(db.Numeric(14, 2), default=0, nullable=False)
    late_fee_daily = db.Column(db.Numeric(14, 2), default=0, nullable=False)
    notes = db.Column(db.Text)
    item = db.relationship("Item")
    branch = db.relationship("Branch")
    warehouse = db.relationship("Warehouse")

class AssetPhoto(db.Model):
    __tablename__ = "asset_photos"
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(160))
    uploaded_at = db.Column(db.DateTime, default=now, nullable=False)
    asset = db.relationship("Asset", backref=db.backref("photos", cascade="all, delete-orphan"))

class StockBalance(db.Model):
    __tablename__ = "stock_balances"
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False)
    quantity = db.Column(db.Numeric(14, 3), default=0, nullable=False)
    item = db.relationship("Item")
    warehouse = db.relationship("Warehouse")
    __table_args__ = (db.UniqueConstraint("item_id", "warehouse_id"),)

class StockMovement(db.Model):
    __tablename__ = "stock_movements"
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False)
    movement_type = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Numeric(14, 3), nullable=False)
    reference = db.Column(db.String(100))
    notes = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    item = db.relationship("Item")
    warehouse = db.relationship("Warehouse")
    user = db.relationship("User")

class Loan(db.Model):
    __tablename__ = "loans"
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id"), nullable=False)
    party_id = db.Column(db.Integer, db.ForeignKey("parties.id"), nullable=False)
    kind = db.Column(db.String(20), default="LOAN", nullable=False)
    status = db.Column(db.String(30), default="PENDING", nullable=False)
    requested_at = db.Column(db.DateTime, default=now, nullable=False)
    start_at = db.Column(db.DateTime)
    due_at = db.Column(db.DateTime, nullable=False)
    returned_at = db.Column(db.DateTime)
    approved_at = db.Column(db.DateTime)
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    daily_rate = db.Column(db.Numeric(14, 2), default=0, nullable=False)
    late_fee_daily = db.Column(db.Numeric(14, 2), default=0, nullable=False)
    discount = db.Column(db.Numeric(14, 2), default=0, nullable=False)
    paid_amount = db.Column(db.Numeric(14, 2), default=0, nullable=False)
    notes = db.Column(db.Text)
    return_condition = db.Column(db.String(30))
    asset = db.relationship("Asset")
    party = db.relationship("Party")
    requested_by = db.relationship("User", foreign_keys=[requested_by_id])
    approved_by = db.relationship("User", foreign_keys=[approved_by_id])
    @property
    def rental_days(self):
        if not self.start_at: return 0
        end = self.returned_at or now()
        return max(1, (end.date() - self.start_at.date()).days + 1)
    @property
    def overdue_days(self):
        end = self.returned_at or now()
        return max(0, (end.date() - self.due_at.date()).days)
    @property
    def total(self):
        rental = Decimal(self.daily_rate or 0) * (self.rental_days if self.kind == "RENTAL" else 0)
        late = Decimal(self.late_fee_daily or 0) * self.overdue_days
        return max(Decimal("0"), rental + late - Decimal(self.discount or 0))

class LoanEvent(db.Model):
    __tablename__ = "loan_events"
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False)
    event_type = db.Column(db.String(30), nullable=False)
    details = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    user = db.relationship("User")
    loan = db.relationship("Loan", backref=db.backref("events", order_by="LoanEvent.created_at"))

