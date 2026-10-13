import io
import os
from datetime import datetime
from decimal import Decimal
from functools import wraps
from pathlib import Path
from uuid import uuid4

import qrcode
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, send_file, send_from_directory, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from werkzeug.utils import secure_filename

load_dotenv()
from config import Config
from models import Asset, AssetPhoto, Branch, Item, Loan, LoanEvent, Party, StockBalance, StockMovement, User, Warehouse, db, now

ALLOWED_IMAGES = {"png", "jpg", "jpeg", "webp"}

def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config: app.config.update(test_config)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
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
    def globals_(): return {"company_name": app.config["COMPANY_NAME"], "now": now}

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
            db.session.add(Item(sku=request.form["sku"].strip(), name=request.form["name"].strip(), category=request.form.get("category"), item_type=request.form["item_type"], unit=request.form.get("unit", "UN"), minimum_stock=Decimal(request.form.get("minimum_stock") or "0")))
            db.session.commit(); flash("Item cadastrado.", "success"); return redirect(url_for("items"))
        return render_template("items.html", items=Item.query.order_by(Item.name).all())

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
        return render_template("stock.html", balances=StockBalance.query.all(), movements=StockMovement.query.order_by(StockMovement.created_at.desc()).limit(30), items=Item.query.filter_by(item_type="STOCK", active=True).all(), warehouses=warehouses)

    @app.route("/assets", methods=["GET", "POST"])
    @login_required
    def assets():
        if request.method == "POST":
            if not current_user.can("admin", "manager", "operator"): abort(403)
            asset = Asset(item_id=int(request.form["item_id"]), branch_id=int(request.form["branch_id"]), warehouse_id=int(request.form["warehouse_id"]), asset_tag=request.form["asset_tag"].strip(), serial_number=request.form.get("serial_number"), daily_rate=Decimal(request.form.get("daily_rate") or "0"), late_fee_daily=Decimal(request.form.get("late_fee_daily") or "0"), notes=request.form.get("notes"))
            db.session.add(asset); db.session.commit(); flash("Equipamento cadastrado.", "success"); return redirect(url_for("asset_detail", asset_id=asset.id))
        query = branch_scope(Asset.query, Asset)
        return render_template("assets.html", assets=query.order_by(Asset.asset_tag).all(), items=Item.query.filter_by(item_type="EQUIPMENT", active=True).all(), branches=Branch.query.filter_by(active=True).all(), warehouses=Warehouse.query.filter_by(active=True).all())

    @app.route("/assets/<int:asset_id>")
    @login_required
    def asset_detail(asset_id): return render_template("asset_detail.html", asset=Asset.query.get_or_404(asset_id))

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
            loan.status="RETURNED"; loan.returned_at=now(); loan.return_condition=request.form.get("return_condition", "GOOD"); loan.asset.condition=loan.return_condition; loan.asset.status="AVAILABLE" if loan.return_condition != "DAMAGED" else "MAINTENANCE"; event="RETURNED"
        elif action == "pay" and loan.status in {"ACTIVE", "RETURNED"}:
            loan.paid_amount = Decimal(loan.paid_amount or 0) + Decimal(request.form.get("amount") or "0"); event="PAYMENT"
        else: abort(400)
        db.session.add(LoanEvent(loan_id=loan.id, event_type=event, details=request.form.get("details"), user_id=current_user.id)); db.session.commit(); flash("Operação realizada.", "success"); return redirect(url_for("loans"))

    @app.route("/loans/<int:loan_id>/term")
    @login_required
    def loan_term(loan_id):
        loan = Loan.query.get_or_404(loan_id); b = io.BytesIO(); c = canvas.Canvas(b, pagesize=A4); width, height = A4
        c.setFont("Helvetica-Bold", 15); c.drawCentredString(width/2, height-60, "TERMO DE RESPONSABILIDADE / LOCAÇÃO")
        c.setFont("Helvetica", 10); y=height-105
        lines=[f"Empresa: {app.config['COMPANY_NAME']}", f"Termo nº: {loan.id}", f"Responsável: {loan.party.name}", f"Documento: {loan.party.document or '-'}", f"Equipamento: {loan.asset.item.name}", f"Patrimônio: {loan.asset.asset_tag}", f"Número de série: {loan.asset.serial_number or '-'}", f"Modalidade: {'Locação' if loan.kind == 'RENTAL' else 'Empréstimo'}", f"Data limite para devolução: {loan.due_at:%d/%m/%Y %H:%M}", f"Valor diário: R$ {loan.daily_rate:.2f}", f"Multa diária por atraso: R$ {loan.late_fee_daily:.2f}", "", "Declaro que recebi o equipamento acima e assumo responsabilidade por sua guarda,", "uso adequado e devolução nas condições e no prazo acordados.", "", "Assinatura do responsável: ______________________________________________", "", "Assinatura da empresa: _________________________________________________"]
        for line in lines: c.drawString(55,y,line); y-=20
        c.save(); b.seek(0); return send_file(b, mimetype="application/pdf", download_name=f"termo-{loan.id}.pdf")

    @app.cli.command("init-db")
    def init_db():
        db.create_all()
        if not Branch.query.first():
            branch=Branch(code="01", name="Matriz"); db.session.add(branch); db.session.flush(); db.session.add(Warehouse(branch_id=branch.id, code="01", name="Almoxarifado Central")); user=User(name="Administrador", email="admin@empresa.local", role="admin", branch_id=branch.id); user.set_password("Admin@123"); db.session.add(user); db.session.commit(); print("Banco criado. Login: admin@empresa.local / Admin@123")
        else: print("Banco já inicializado.")
    return app

app = create_app()
if __name__ == "__main__": app.run(host="0.0.0.0", port=5000, debug=True)
