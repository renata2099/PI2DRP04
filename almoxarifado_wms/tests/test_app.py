"""Testes automatizados de estoque, permissões, faturamento e acessibilidade básica."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from models import (Asset, AssetPhoto, Branch, Item, Loan, LoanEvent, Party,
                    StockBalance, StockMovement, User, Warehouse, db)


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                      "UPLOAD_FOLDER": str(tmp_path / "uploads"), "SECRET_KEY": "teste-seguro"})
    with app.app_context():
        db.create_all()
        b1, b2 = Branch(code="01", name="Matriz"), Branch(code="02", name="Filial")
        db.session.add_all([b1, b2]); db.session.flush()
        w1, w2 = Warehouse(branch_id=b1.id, code="01", name="Central"), Warehouse(branch_id=b2.id, code="01", name="Regional")
        db.session.add_all([w1, w2])
        for role in ("admin", "manager", "operator", "viewer"):
            u = User(name=role.title(), email=f"{role}@example.com", role=role, branch_id=b1.id)
            u.set_password("pass"); db.session.add(u)
        db.session.add(Item(sku="P1", name="Luva", item_type="STOCK", unit="UN"))
        db.session.add(Item(sku="E1", name="Projetor", item_type="EQUIPMENT", unit="UN"))
        db.session.add(Party(kind="EMPLOYEE", name="Pessoa teste"))
        db.session.commit()
        equipment = Item.query.filter_by(sku="E1").one()
        db.session.add_all([
            Asset(item_id=equipment.id, branch_id=b1.id, warehouse_id=w1.id, asset_tag="EQ1", status="AVAILABLE"),
            Asset(item_id=equipment.id, branch_id=b2.id, warehouse_id=w2.id, asset_tag="EQ2", status="AVAILABLE"),
        ])
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, role="admin"):
    return client.post("/login", data={"email": f"{role}@example.com", "password": "pass"}, follow_redirects=True)


def ids(app):
    with app.app_context():
        return {
            "stock": Item.query.filter_by(sku="P1").one().id,
            "equipment": Item.query.filter_by(sku="E1").one().id,
            "warehouse1": Warehouse.query.filter_by(name="Central").one().id,
            "warehouse2": Warehouse.query.filter_by(name="Regional").one().id,
            "asset1": Asset.query.filter_by(asset_tag="EQ1").one().id,
            "asset2": Asset.query.filter_by(asset_tag="EQ2").one().id,
            "party": Party.query.first().id,
        }


def stock_data(i, quantity="2", direction="IN", warehouse=None):
    return {"item_id": i["stock"], "warehouse_id": warehouse or i["warehouse1"],
            "movement_type": direction, "quantity": quantity}


def create_loan(client, i, *, kind="RENTAL", rate="10", late="5"):
    due = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    return client.post("/loans", data={"asset_id": i["asset1"], "party_id": i["party"],
             "kind": kind, "due_at": due, "daily_rate": rate, "late_fee_daily": late})


def test_login_and_item(client, app):
    assert login(client).status_code == 200
    r = client.post("/items", data={"sku": "P002", "name": "Capacete", "item_type": "STOCK",
                                    "unit": "UN", "minimum_stock": "2"}, follow_redirects=True)
    assert "Item cadastrado" in r.get_data(as_text=True)
    with app.app_context():
        assert Item.query.filter_by(sku="P002").count() == 1


def test_stock_prevents_negative_balance(client, app):
    login(client); i = ids(app)
    r = client.post("/stock", data=stock_data(i, "1", "OUT"), follow_redirects=True)
    assert "Saldo insuficiente" in r.get_data(as_text=True)
    with app.app_context():
        assert StockMovement.query.count() == 0
        assert StockBalance.query.count() == 0


@pytest.mark.parametrize("quantity,direction", [
    ("0", "IN"), ("-1", "IN"), ("NaN", "IN"), ("Infinity", "IN"),
    ("1.0001", "IN"), ("1", "INVALIDO"), ("", "IN")
])
def test_stock_rejects_invalid_inputs(client, app, quantity, direction):
    login(client); i = ids(app)
    assert client.post("/stock", data=stock_data(i, quantity, direction)).status_code == 400
    with app.app_context():
        assert StockMovement.query.count() == 0
        assert StockBalance.query.count() == 0


def test_stock_adds_and_subtracts_and_preserves_history(client, app):
    login(client); i = ids(app)
    assert client.post("/stock", data=stock_data(i, "2.250", "IN")).status_code == 302
    assert client.post("/stock", data=stock_data(i, "0.750", "OUT")).status_code == 302
    with app.app_context():
        assert StockBalance.query.one().quantity == Decimal("1.500")
        assert [m.movement_type for m in StockMovement.query.order_by(StockMovement.id).all()] == ["IN", "OUT"]


def test_stock_rejects_equipment_as_material(client, app):
    login(client); i = ids(app); data = stock_data(i)
    data["item_id"] = i["equipment"]
    assert client.post("/stock", data=data).status_code == 404


def test_viewer_cannot_modify_even_with_direct_post(client, app):
    login(client, "viewer"); i = ids(app)
    requests = [
        ("/items", {"sku": "X", "name": "X", "item_type": "STOCK"}),
        ("/stock", stock_data(i)),
        ("/parties", {"kind": "CUSTOMER", "name": "Sem permissão"}),
        ("/assets", {"item_id": i["equipment"], "branch_id": 1, "warehouse_id": i["warehouse1"], "asset_tag": "X"}),
        ("/loans", {"asset_id": i["asset1"], "party_id": i["party"], "kind": "LOAN", "due_at": "2099-01-01T12:00"}),
        (f"/assets/{i['asset1']}/photo", {"caption": "Sem permissão"}),
        (f"/assets/{i['asset1']}/condition", {"condition": "USED"}),
    ]
    for url, data in requests:
        assert client.post(url, data=data).status_code == 403, url
    for url in ["/items", "/stock", "/assets", "/loans", "/parties"]:
        assert client.get(url).status_code == 200
    assert "Cadastrar novo item" not in client.get("/items").get_data(as_text=True)
    assert "Adicionar foto" not in client.get(f"/assets/{i['asset1']}").get_data(as_text=True)


def test_operator_cannot_approve_or_receive_payments(client, app):
    i = ids(app)
    login(client, "operator"); assert create_loan(client, i).status_code == 302
    with app.app_context(): loan_id = Loan.query.one().id
    assert client.post(f"/loans/{loan_id}/approve").status_code == 403
    assert client.post(f"/loans/{loan_id}/pay", data={"amount": "5"}).status_code == 403
    assert client.post(f"/loans/{loan_id}/return", data={"return_condition": "GOOD"}).status_code == 400
    with app.app_context(): assert Loan.query.one().status == "PENDING"


def test_manager_approves_and_operator_returns_damaged_item(client, app):
    i = ids(app)
    login(client); assert create_loan(client, i).status_code == 302
    with app.app_context(): loan_id = Loan.query.one().id
    client.get("/logout"); login(client, "manager")
    assert client.post(f"/loans/{loan_id}/approve").status_code == 302
    with app.app_context():
        assert Loan.query.one().status == "ACTIVE"
        assert Asset.query.filter_by(asset_tag="EQ1").one().status == "LOANED"
    client.get("/logout"); login(client, "operator")
    assert client.post(f"/loans/{loan_id}/return", data={"return_condition": "DAMAGED"}).status_code == 302
    with app.app_context():
        assert Loan.query.one().status == "RETURNED"
        assert Asset.query.filter_by(asset_tag="EQ1").one().status == "MAINTENANCE"
        assert [e.event_type for e in LoanEvent.query.order_by(LoanEvent.id).all()] == ["REQUESTED", "APPROVED", "RETURNED"]


def test_payment_rejects_negative_nan_excess_and_accepts_exact(client, app):
    i = ids(app); login(client)
    assert create_loan(client, i).status_code == 302
    with app.app_context(): loan_id = Loan.query.one().id
    assert client.post(f"/loans/{loan_id}/approve").status_code == 302
    for amount in ["-5", "NaN", "Infinity", "0", "0.001", "1000000"]:
        assert client.post(f"/loans/{loan_id}/pay", data={"amount": amount}).status_code == 400, amount
    assert client.post(f"/loans/{loan_id}/pay", data={"amount": "5.00"}).status_code == 302
    with app.app_context():
        assert Loan.query.one().paid_amount == Decimal("5.00")
        assert LoanEvent.query.filter_by(event_type="PAYMENT").count() == 1


def test_restricts_branch_records_in_views_and_writes(client, app):
    login(client, "operator"); i = ids(app)
    assert client.get(f"/assets/{i['asset2']}").status_code == 404
    assert client.get(f"/assets/{i['asset2']}/qr").status_code == 404
    assert client.post("/stock", data=stock_data(i, warehouse=i["warehouse2"])).status_code == 403
    assert client.post("/loans", data={"asset_id": i["asset2"], "party_id": i["party"],
                                          "kind": "LOAN", "due_at": "2099-01-01T12:00"}).status_code == 404


def test_loan_totals_exact():
    loan = Loan(kind="RENTAL", daily_rate=Decimal("10.00"), late_fee_daily=Decimal("5.00"),
                discount=Decimal("2.00"), start_at=datetime(2026, 10, 1, 8),
                due_at=datetime(2026, 10, 3, 8), returned_at=datetime(2026, 10, 5, 8))
    assert loan.rental_days == 5
    assert loan.overdue_days == 2
    assert loan.total == Decimal("58.00")
    loan.kind = "LOAN"
    assert loan.total == Decimal("8.00")  # Multa por atraso, sem cobrança diária


def test_accessibility_landmarks_labels_and_table_regions(client, app):
    login(client)
    for url in ["/", "/items", "/stock", "/assets", "/loans", "/parties", "/admin", "/login"]:
        body = client.get(url).get_data(as_text=True)
        assert 'lang="pt-BR"' in body, url
        assert 'id="conteudo-principal"' in body, url
        assert 'href="#conteudo-principal"' in body, url
        assert '<title>' in body, url
        if url not in ("/login",):
            assert 'aria-label="Navegação principal"' in body, url
    detail = client.get(f"/assets/{ids(app)['asset1']}").get_data(as_text=True)
    assert 'for="photo-upload"' in detail
    assert 'for="photo-caption"' in detail
    assert 'role="region"' in client.get('/loans').get_data(as_text=True)


def test_authentication_and_administration_permissions(client):
    assert client.get('/stock').status_code == 302
    assert '/login' in client.get('/stock').headers['Location']
    assert client.post('/loans/1/return', data={'return_condition':'GOOD'}).status_code == 302
    login(client, 'viewer')
    assert client.get('/admin').status_code == 403
    assert client.post('/admin', data={'entity':'branch', 'code':'99', 'name':'Proibida'}).status_code == 403
    assert 'href="/logout"' in client.get('/items').get_data(as_text=True)


def test_csv_exports_and_search_survive_changes(client, app):
    login(client)
    for url in ['/items?export=csv', '/stock?export=csv', '/assets?export=csv']:
        r = client.get(url)
        assert r.status_code == 200
        assert 'text/csv' in r.content_type
        assert r.data.startswith(b'\xef\xbb\xbf')
    assert client.get('/items?q=luva').status_code == 200
    assert client.get('/assets?q=EQ1').status_code == 200
