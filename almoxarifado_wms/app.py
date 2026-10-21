import io
import os
from datetime import datetime
from decimal import Decimal
from functools import wraps
from pathlib import Path
from uuid import uuid4
import csv

from sqlalchemy import inspect, or_, text

import qrcode
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, send_file, send_from_directory, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from werkzeug.utils import secure_filename

load_dotenv()
from config import Config
from models import Asset, AssetPhoto, Branch, Item, Loan, LoanEvent, Party, StockBalance, StockMovement, User, Warehouse, db, now
from loan_pdf import generate_loan_term

ALLOWED_IMAGES = {"png", "jpg", "jpeg", "webp"}
ITEM_CONDITIONS = {"NEW": "Novo", "USED": "Usado", "DISPOSAL": "Descarte"}
CONDITION_LABELS = {**ITEM_CONDITIONS, "GOOD": "A classificar", "DAMAGED": "A classificar", "UNSPECIFIED": "A classificar"}
ASSET_STATUS_LABELS = {"AVAILABLE": "Disponível", "RESERVED": "Reservado", "LOANED": "Emprestado / locado", "MAINTENANCE": "Manutenção", "DISCARDED": "Descartado"}


def ensure_item_condition_column(app):
    """Migração aditiva e idempotente no SQLite existente, sem recriar o banco."""
    with app.app_context():
        engine = db.engine
        if engine.dialect.name != "sqlite":
            return
        inspector = inspect(engine)
        if inspector.has_table("items") and "condition" not in {c["name"] for c in inspector.get_columns("items")}:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE items ADD COLUMN condition VARCHAR(20) NOT NULL DEFAULT 'UNSPECIFIED'"))


def clean_condition(value):
    return value if value in ITEM_CONDITIONS else None


def csv_text(value):
    """Previne interpretação de texto dos cadastros como fórmulas em planilhas."""
    value = str(value if value is not None else "")
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def csv_response(filename, headers, rows):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(headers)
    writer.writerows([[csv_text(v) for v in row] for row in rows])
    return send_file(io.BytesIO(("\ufeff" + output.getvalue()).encode("utf-8")),
                     mimetype="text/csv; charset=utf-8", as_attachment=True, download_name=filename)

def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config: app.config.update(test_config)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    ensure_item_condition_column(app)
    login = LoginManager(app)
    login.login_view = "login"
    login.login_message = "Entre para acessar o sistema."

    @login.user_loader
    def load_user(user_id): return db.session.get(User, int(user_id))

    def roles(*allowed):
        def deco(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                if not current_user.can(*allowed): abort(403)
                return fn(*args, **kwargs)
            return wrapped
        return deco

    def branch_scope(query, model):
        if current_user.role != "admin" and current_user.branch_id and hasattr(model, "branch_id"):
            return query.filter(model.branch_id == current_user.branch_id)
        return query

    @app.context_processor
    def globals_(): return {"company_name": app.config["COMPANY_NAME"], "now": now,
                            "condition_labels": CONDITION_LABELS, "asset_status_labels": ASSET_STATUS_LABELS}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            user = User.query.filter_by(email=request.form["email"].lower().strip(), active=True).first()
            if user and user.check_password(request.form["password"]):
                login_user(user); return redirect(url_for("dashboard"))
            flash("Usuário ou senha inválidos.", "danger")
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout(): logout_user(); return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def dashboard():
        assets = branch_scope(Asset.query, Asset).all()
        active_loans = Loan.query.filter(Loan.status.in_(["APPROVED", "ACTIVE"])).all()
        low = StockBalance.query.join(Item).filter(StockBalance.quantity <= Item.minimum_stock).all()
        pending = Loan.query.filter_by(status="PENDING").count()
        return render_template("dashboard.html", assets=assets, active_loans=active_loans, low=low, pending=pending)

    @app.route("/items", methods=["GET", "POST"])
    @login_required
    def items():
        if request.method == "POST":
            if not current_user.can("admin", "manager", "operator"): abort(403)
            category = request.form.get("category", "").strip()
            if category == "__new__":
                category = request.form.get("new_category", "").strip()
            if len(category) > 80 or (request.form.get("category") == "__new__" and not category):
                flash("Informe uma categoria válida (até 80 caracteres).", "danger")
                return redirect(url_for("items"))
            # Reaproveita a grafia de uma categoria já cadastrada.
            existing = next((c for (c,) in db.session.query(Item.category).distinct().all()
                             if c and c.strip().casefold() == category.casefold()), None)
            category = existing.strip() if existing else (category or None)
            condition = clean_condition(request.form.get("condition", "NEW"))
            if not condition:
                flash("Selecione uma condição válida.", "danger")
                return redirect(url_for("items"))
            db.session.add(Item(sku=request.form["sku"].strip(), name=request.form["name"].strip(), category=category,
                                condition=condition, item_type=request.form["item_type"], unit=request.form.get("unit", "UN"),
                                minimum_stock=Decimal(request.form.get("minimum_stock") or "0")))
            db.session.commit(); flash("Item cadastrado.", "success"); return redirect(url_for("items"))
        all_items = Item.query.order_by(Item.name).all()
        categories = sorted({i.category.strip() for i in all_items if i.category and i.category.strip()}, key=str.casefold)
        search = request.args.get("q", "").strip()[:120]
        kind = request.args.get("type", "")
        condition = request.args.get("condition", "")
        query = Item.query
        if search:
            phrase = f"%{search}%"
            query = query.filter(or_(Item.sku.ilike(phrase), Item.name.ilike(phrase), Item.category.ilike(phrase)))
        if kind in ("STOCK", "EQUIPMENT"):
            query = query.filter_by(item_type=kind)
        if condition in ITEM_CONDITIONS or condition == "UNSPECIFIED":
            query = query.filter_by(condition=condition)
        listed = query.order_by(Item.name).all()
        if request.args.get("export") == "csv":
            return csv_response("itens_wms.csv", ["SKU", "Nome", "Categoria", "Tipo", "Condição", "Unidade", "Mínimo"],
                                [(i.sku, i.name, i.category or "", i.item_type, CONDITION_LABELS.get(i.condition, "A classificar"), i.unit, i.minimum_stock) for i in listed])
        return render_template("items.html", items=listed, categories=categories, search=search,
                               selected_type=kind, selected_condition=condition, total=len(all_items))

    @app.route("/items/<int:item_id>/condition", methods=["POST"])
    @login_required
    def item_condition(item_id):
        if not current_user.can("admin", "manager", "operator"): abort(403)
        item = Item.query.get_or_404(item_id)
        condition = clean_condition(request.form.get("condition"))
        if not condition: abort(400)
        item.condition = condition
        db.session.commit()
        flash(f"Condição do item {item.sku} atualizada.", "success")
        return redirect(url_for("items"))

    @app.route("/stock", methods=["GET", "POST"])
    @login_required
    def stock():
        if request.method == "POST":
            if not current_user.can("admin", "manager", "operator"): abort(403)
            item_id, wh_id = int(request.form["item_id"]), int(request.form["warehouse_id"])
            qty = Decimal(request.form["quantity"]); kind = request.form["movement_type"]
            signed = qty if kind == "IN" else -qty
            balance = StockBalance.query.filter_by(item_id=item_id, warehouse_id=wh_id).with_for_update().first()
            if not balance: balance = StockBalance(item_id=item_id, warehouse_id=wh_id, quantity=0); db.session.add(balance)
            if Decimal(balance.quantity or 0) + signed < 0:
                flash("Saldo insuficiente para a saída.", "danger"); return redirect(url_for("stock"))
            balance.quantity = Decimal(balance.quantity or 0) + signed
            db.session.add(StockMovement(item_id=item_id, warehouse_id=wh_id, movement_type=kind, quantity=qty, reference=request.form.get("reference"), notes=request.form.get("notes"), user_id=current_user.id))
            db.session.commit(); flash("Movimentação registrada.", "success"); return redirect(url_for("stock"))
        warehouses = Warehouse.query.order_by(Warehouse.name).all()
        search = request.args.get("q", "").strip()[:120]
        condition = request.args.get("condition", "")
        balance_query = StockBalance.query.join(Item).join(Warehouse)
        if search:
            phrase = f"%{search}%"
            balance_query = balance_query.filter(or_(Item.sku.ilike(phrase), Item.name.ilike(phrase),
                                                    Item.category.ilike(phrase), Warehouse.name.ilike(phrase)))
        if condition in ITEM_CONDITIONS or condition == "UNSPECIFIED":
            balance_query = balance_query.filter(Item.condition == condition)
        balances = balance_query.order_by(Item.name, Warehouse.name).all()
        if request.args.get("export") == "csv":
            return csv_response("saldos_wms.csv", ["SKU", "Item", "Categoria", "Condição", "Depósito", "Saldo", "Unidade", "Mínimo", "Situação"],
                                [(b.item.sku, b.item.name, b.item.category or "", CONDITION_LABELS.get(b.item.condition, "A classificar"),
                                  b.warehouse.name, b.quantity, b.item.unit, b.item.minimum_stock,
                                  "Repor" if b.quantity <= b.item.minimum_stock else "Em dia") for b in balances])
        total_balances = StockBalance.query.count()
        low_count = StockBalance.query.join(Item).filter(StockBalance.quantity <= Item.minimum_stock).count()
        return render_template("stock.html", balances=balances, movements=StockMovement.query.order_by(StockMovement.created_at.desc()).limit(30),
                               items=Item.query.filter_by(item_type="STOCK", active=True).order_by(Item.name).all(),
                               warehouses=warehouses, search=search, selected_condition=condition,
                               total_balances=total_balances, low_count=low_count)

    @app.route("/assets", methods=["GET", "POST"])
    @login_required
    def assets():
        if request.method == "POST":
            if not current_user.can("admin", "manager", "operator"): abort(403)
            condition = clean_condition(request.form.get("condition", "NEW"))
            if not condition:
                flash("Selecione uma condição válida.", "danger")
                return redirect(url_for("assets"))
            asset = Asset(item_id=int(request.form["item_id"]), branch_id=int(request.form["branch_id"]), warehouse_id=int(request.form["warehouse_id"]), asset_tag=request.form["asset_tag"].strip(), serial_number=request.form.get("serial_number"), daily_rate=Decimal(request.form.get("daily_rate") or "0"), late_fee_daily=Decimal(request.form.get("late_fee_daily") or "0"), notes=request.form.get("notes"), condition=condition, status="DISCARDED" if condition == "DISPOSAL" else "AVAILABLE")
            db.session.add(asset); db.session.commit(); flash("Equipamento cadastrado.", "success"); return redirect(url_for("asset_detail", asset_id=asset.id))
        search = request.args.get("q", "").strip()[:120]
        status = request.args.get("status", "")
        condition = request.args.get("condition", "")
        query = branch_scope(Asset.query, Asset)
        if search:
            phrase = f"%{search}%"
            query = query.join(Item).outerjoin(Branch).outerjoin(Warehouse).filter(or_(
                Asset.asset_tag.ilike(phrase), Asset.serial_number.ilike(phrase), Item.name.ilike(phrase),
                Item.sku.ilike(phrase), Item.category.ilike(phrase), Branch.name.ilike(phrase), Warehouse.name.ilike(phrase)))
        if status in ASSET_STATUS_LABELS:
            query = query.filter(Asset.status == status)
        if condition in ITEM_CONDITIONS:
            query = query.filter(Asset.condition == condition)
        elif condition == "UNSPECIFIED":
            query = query.filter(~Asset.condition.in_(ITEM_CONDITIONS))
        listed_assets = query.order_by(Asset.asset_tag).all()
        # Mantém responsável atual também na tela de patrimônio.
        current_loans = Loan.query.filter(Loan.asset_id.in_([a.id for a in listed_assets]),
                                          Loan.status.in_(["PENDING", "ACTIVE"])).order_by(Loan.requested_at.desc()).all() if listed_assets else []
        holder_by_asset = {}
        for loan in current_loans:
            holder_by_asset.setdefault(loan.asset_id, loan)
        if request.args.get("export") == "csv":
            return csv_response("equipamentos_wms.csv", ["Patrimônio", "Modelo", "SKU", "Série", "Condição", "Disponibilidade", "Filial", "Depósito", "Responsável"],
                                [(a.asset_tag, a.item.name, a.item.sku, a.serial_number or "", CONDITION_LABELS.get(a.condition, "A classificar"),
                                  ASSET_STATUS_LABELS.get(a.status, a.status), a.branch.name, a.warehouse.name,
                                  holder_by_asset[a.id].party.name if a.id in holder_by_asset else "") for a in listed_assets])
        return render_template("assets.html", assets=listed_assets, holder_by_asset=holder_by_asset,
                               items=Item.query.filter_by(item_type="EQUIPMENT", active=True).order_by(Item.name).all(),
                               branches=Branch.query.filter_by(active=True).all(), warehouses=Warehouse.query.filter_by(active=True).all(),
                               search=search, selected_status=status, selected_condition=condition,
                               total_assets=branch_scope(Asset.query, Asset).count())

    @app.route("/assets/<int:asset_id>/condition", methods=["POST"])
    @login_required
    def asset_condition(asset_id):
        if not current_user.can("admin", "manager", "operator"): abort(403)
        asset = branch_scope(Asset.query, Asset).filter(Asset.id == asset_id).first_or_404()
        condition = clean_condition(request.form.get("condition"))
        if not condition: abort(400)
        if condition == "DISPOSAL" and asset.status in {"LOANED", "RESERVED"}:
            flash("Não é possível descartar um equipamento com reserva ou empréstimo em andamento.", "danger")
            return redirect(url_for("asset_detail", asset_id=asset.id))
        previous_condition = asset.condition
        asset.condition = condition
        if condition == "DISPOSAL":
            asset.status = "DISCARDED"
        elif previous_condition == "DISPOSAL" and asset.status == "DISCARDED":
            asset.status = "AVAILABLE"
        db.session.commit()
        flash("Condição atualizada.", "success")
        return redirect(url_for("asset_detail", asset_id=asset.id))

    @app.route("/assets/<int:asset_id>/release", methods=["POST"])
    @login_required
    def asset_release(asset_id):
        if not current_user.can("admin", "manager", "operator"): abort(403)
        asset = branch_scope(Asset.query, Asset).filter(Asset.id == asset_id).first_or_404()
        if asset.status != "MAINTENANCE": abort(400)
        if Loan.query.filter(Loan.asset_id == asset.id, Loan.status.in_(["PENDING", "ACTIVE"])).first():
            flash("Há empréstimo ou reserva em andamento para este patrimônio.", "danger")
            return redirect(url_for("asset_detail", asset_id=asset.id))
        asset.condition = "USED"
        asset.status = "AVAILABLE"
        db.session.commit()
        flash("Patrimônio liberado após manutenção.", "success")
        return redirect(url_for("asset_detail", asset_id=asset.id))

    @app.route("/assets/<int:asset_id>")
    @login_required
    def asset_detail(asset_id):
        asset = branch_scope(Asset.query, Asset).filter(Asset.id == asset_id).first_or_404()
        current_loan = Loan.query.filter(Loan.asset_id == asset.id, Loan.status.in_(["PENDING", "ACTIVE"]))\
            .order_by(Loan.requested_at.desc()).first()
        return render_template("asset_detail.html", asset=asset, current_loan=current_loan)

    @app.route("/assets/<int:asset_id>/photo", methods=["POST"])
    @login_required
    def asset_photo(asset_id):
        asset = Asset.query.get_or_404(asset_id); file = request.files.get("photo")
        if not file or "." not in file.filename or file.filename.rsplit(".", 1)[1].lower() not in ALLOWED_IMAGES:
            flash("Envie uma imagem PNG, JPG ou WEBP.", "danger"); return redirect(url_for("asset_detail", asset_id=asset.id))
        ext = file.filename.rsplit(".", 1)[1].lower(); filename = f"{uuid4().hex}.{ext}"
        file.save(Path(app.config["UPLOAD_FOLDER"]) / filename)
        db.session.add(AssetPhoto(asset_id=asset.id, filename=filename, caption=request.form.get("caption"))); db.session.commit()
        flash("Foto adicionada.", "success"); return redirect(url_for("asset_detail", asset_id=asset.id))

    @app.route("/uploads/<path:filename>")
    @login_required
    def uploads(filename): return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    @app.route("/assets/<int:asset_id>/qr")
    @login_required
    def asset_qr(asset_id):
        asset = Asset.query.get_or_404(asset_id)
        image = qrcode.make(url_for("asset_detail", asset_id=asset.id, _external=True))
        buffer = io.BytesIO(); image.save(buffer, "PNG"); buffer.seek(0)
        return send_file(buffer, mimetype="image/png", download_name=f"QR-{asset.asset_tag}.png")

    @app.route("/parties", methods=["GET", "POST"])
    @login_required
    def parties():
        if request.method == "POST":
            db.session.add(Party(kind=request.form["kind"], document=request.form.get("document"), name=request.form["name"], email=request.form.get("email"), phone=request.form.get("phone")))
            db.session.commit(); flash("Pessoa cadastrada.", "success"); return redirect(url_for("parties"))
        return render_template("parties.html", parties=Party.query.order_by(Party.name).all())

    @app.route("/admin", methods=["GET", "POST"])
    @login_required
    @roles("admin")
    def admin():
        if request.method == "POST":
            entity = request.form["entity"]
            if entity == "branch": db.session.add(Branch(code=request.form["code"], name=request.form["name"]))
            elif entity == "warehouse": db.session.add(Warehouse(branch_id=int(request.form["branch_id"]), code=request.form["code"], name=request.form["name"]))
            elif entity == "user":
                user = User(name=request.form["name"], email=request.form["email"].lower().strip(), role=request.form["role"], branch_id=int(request.form["branch_id"]) if request.form.get("branch_id") else None)
                user.set_password(request.form["password"]); db.session.add(user)
            else: abort(400)
            db.session.commit(); flash("Cadastro administrativo incluído.", "success"); return redirect(url_for("admin"))
        return render_template("admin.html", branches=Branch.query.order_by(Branch.code).all(), warehouses=Warehouse.query.order_by(Warehouse.code).all(), users=User.query.order_by(User.name).all())

    @app.route("/loans", methods=["GET", "POST"])
    @login_required
    def loans():
        if request.method == "POST":
            asset = Asset.query.get_or_404(int(request.form["asset_id"]))
            if asset.status != "AVAILABLE": flash("Equipamento indisponível.", "danger"); return redirect(url_for("loans"))
            due = datetime.fromisoformat(request.form["due_at"])
            loan = Loan(asset_id=asset.id, party_id=int(request.form["party_id"]), kind=request.form["kind"], due_at=due, requested_by_id=current_user.id, daily_rate=Decimal(request.form.get("daily_rate") or asset.daily_rate), late_fee_daily=Decimal(request.form.get("late_fee_daily") or asset.late_fee_daily), notes=request.form.get("notes"))
            asset.status = "RESERVED"; db.session.add(loan); db.session.flush(); db.session.add(LoanEvent(loan_id=loan.id, event_type="REQUESTED", details="Solicitação criada", user_id=current_user.id)); db.session.commit()
            flash("Solicitação enviada para aprovação.", "success"); return redirect(url_for("loans"))
        return render_template("loans.html", loans=Loan.query.order_by(Loan.requested_at.desc()).all(), assets=branch_scope(Asset.query, Asset).filter_by(status="AVAILABLE").all(), parties=Party.query.filter_by(active=True).all())

    @app.route("/loans/<int:loan_id>/<action>", methods=["POST"])
    @login_required
    def loan_action(loan_id, action):
        loan = Loan.query.get_or_404(loan_id)
        if action in {"approve", "reject"} and not current_user.can("admin", "manager"): abort(403)
        if action == "approve" and loan.status == "PENDING":
            loan.status="ACTIVE"; loan.start_at=now(); loan.approved_at=now(); loan.approved_by_id=current_user.id; loan.asset.status="LOANED"; event="APPROVED"
        elif action == "reject" and loan.status == "PENDING":
            loan.status="REJECTED"; loan.asset.status="AVAILABLE"; event="REJECTED"
        elif action == "return" and loan.status == "ACTIVE":
            loan.status="RETURNED"; loan.returned_at=now(); loan.return_condition=request.form.get("return_condition", "GOOD")
            if loan.return_condition not in {"GOOD", "DAMAGED"}: abort(400)
            loan.asset.condition="USED"; loan.asset.status="AVAILABLE" if loan.return_condition == "GOOD" else "MAINTENANCE"; event="RETURNED"
        elif action == "pay" and loan.status in {"ACTIVE", "RETURNED"}:
            loan.paid_amount = Decimal(loan.paid_amount or 0) + Decimal(request.form.get("amount") or "0"); event="PAYMENT"
        else: abort(400)
        db.session.add(LoanEvent(loan_id=loan.id, event_type=event, details=request.form.get("details"), user_id=current_user.id)); db.session.commit(); flash("Operação realizada.", "success"); return redirect(url_for("loans"))

    @app.route("/loans/<int:loan_id>/term")
    @login_required
    def loan_term(loan_id):
        loan = Loan.query.get_or_404(loan_id)
        document = generate_loan_term(loan, app.config["COMPANY_NAME"])
        return send_file(document, mimetype="application/pdf", download_name=f"termo-{loan.id}.pdf")

    @app.cli.command("init-db")
    def init_db():
        db.create_all()
        if not Branch.query.first():
            branch=Branch(code="01", name="Matriz"); db.session.add(branch); db.session.flush(); db.session.add(Warehouse(branch_id=branch.id, code="01", name="Almoxarifado Central")); user=User(name="Administrador", email="admin@empresa.local", role="admin", branch_id=branch.id); user.set_password("Admin@123"); db.session.add(user); db.session.commit(); print("Banco criado. Login: admin@empresa.local / Admin@123")
        else: print("Banco já inicializado.")
    return app

app = create_app()
if __name__ == "__main__": app.run(host="0.0.0.0", port=5000, debug=True)
