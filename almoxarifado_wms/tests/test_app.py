from datetime import datetime, timedelta
from decimal import Decimal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from models import Asset, Branch, Item, Loan, Party, StockBalance, User, Warehouse, db

def setup_app(tmp_path):
    app=create_app({"TESTING":True,"SQLALCHEMY_DATABASE_URI":"sqlite:///:memory:","UPLOAD_FOLDER":str(tmp_path),"SECRET_KEY":"test"})
    with app.app_context():
        db.create_all(); b=Branch(code="01",name="Matriz"); db.session.add(b); db.session.flush(); w=Warehouse(branch_id=b.id,code="01",name="Central"); u=User(name="Admin",email="a@a.com",role="admin",branch_id=b.id); u.set_password("pass"); db.session.add_all([w,u]); db.session.commit()
    return app

def login(client): return client.post("/login",data={"email":"a@a.com","password":"pass"},follow_redirects=True)

def test_login_and_item(tmp_path):
    app=setup_app(tmp_path); c=app.test_client(); assert login(c).status_code==200
    r=c.post("/items",data={"sku":"P001","name":"Luva","item_type":"STOCK","unit":"UN","minimum_stock":"2"},follow_redirects=True)
    assert b"Item cadastrado" in r.data

def test_stock_prevents_negative_balance(tmp_path):
    app=setup_app(tmp_path); c=app.test_client(); login(c)
    with app.app_context():
        i=Item(sku="P1",name="Peça",item_type="STOCK",unit="UN"); db.session.add(i); db.session.commit(); iid=i.id; wid=Warehouse.query.first().id
    r=c.post("/stock",data={"item_id":iid,"warehouse_id":wid,"movement_type":"OUT","quantity":"1"},follow_redirects=True)
    assert b"Saldo insuficiente" in r.data

def test_loan_totals():
    loan=Loan(kind="RENTAL",daily_rate=Decimal("10"),late_fee_daily=Decimal("5"),discount=Decimal("0"),start_at=datetime.now()-timedelta(days=3),due_at=datetime.now()-timedelta(days=1),returned_at=datetime.now())
    assert loan.total >= Decimal("45")

