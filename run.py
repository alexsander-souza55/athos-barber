import os
from app import create_app
from app.extensions import db

app = create_app(os.environ.get("FLASK_ENV", "development"))


@app.cli.command("init-db")
def init_db():
    """Cria todas as tabelas no banco de dados."""
    with app.app_context():
        db.create_all()
        print("Banco de dados inicializado.")


@app.cli.command("reset-db")
def reset_db():
    """APAGA e recria todas as tabelas (use apenas em desenvolvimento)."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        print("Banco de dados resetado.")


@app.cli.command("seed")
def seed():
    """Popula o banco com dados iniciais (admin + exemplos)."""
    with app.app_context():
        from app.models.user import User
        from app.models.barber import Barber
        from app.models.service import Service

        if User.query.filter_by(username="admin").first():
            print("Seed já aplicado.")
            return

        admin = User(username="admin", email="admin@barberhub.local", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)

        barber_user = User(username="joao", email="joao@barberhub.local", role="barber")
        barber_user.set_password("barber123")
        db.session.add(barber_user)
        db.session.flush()

        barber = Barber(user_id=barber_user.id, name="João Silva",
                        phone="(11) 99999-0001", specialty="Degradê e Navalhado")
        db.session.add(barber)

        services = [
            Service(name="Corte Tradicional", price=35.00, duration_minutes=30,
                    description="Corte clássico com tesoura e máquina."),
            Service(name="Degradê", price=45.00, duration_minutes=40,
                    description="Corte moderno com degradê nas laterais."),
            Service(name="Barba Completa", price=30.00, duration_minutes=30,
                    description="Barba feita com navalha e acabamento perfeito."),
            Service(name="Corte + Barba", price=65.00, duration_minutes=60,
                    description="Combo completo com desconto."),
            Service(name="Hidratação Capilar", price=40.00, duration_minutes=45,
                    description="Tratamento de hidratação profissional."),
        ]
        for s in services:
            db.session.add(s)

        db.session.commit()
        print("Seed aplicado com sucesso!")
        print("  Admin:  admin / admin123")
        print("  Barber: joao  / barber123")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
