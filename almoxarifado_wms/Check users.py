from app import app
from models import Usuario

with app.app_context():
    for u in Usuario.query.all():
        print(u.id, u.nome, u.email, u.tipo_usuario)