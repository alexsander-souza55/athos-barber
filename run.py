import os
from app import create_app
from app.extensions import db

app = create_app(os.environ.get("FLASK_CONFIG", "development"))


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


@app.cli.command("seed-subscription-plans")
def seed_subscription_plans():
    """Popula os planos do Clube Athos. Não insere se já houver planos."""
    with app.app_context():
        from app.models.subscription_plan import SubscriptionPlan, SubscriptionPlanCredit
        from app.models.service import Service

        if SubscriptionPlan.query.count() > 0:
            print("Planos de assinatura já existem. Nenhum plano inserido.")
            return

        def _get(name):
            svc = Service.query.filter(
                db.func.lower(Service.name) == name.lower()
            ).first()
            if not svc:
                print(f"  AVISO: Serviço '{name}' não encontrado. Execute 'flask seed-services' primeiro.")
            return svc

        cabelo   = _get("Cabelo")
        barba_t  = _get("Barba Terapia")
        barba_tr = _get("Barba Tradicional")
        pezinho  = _get("Pezinho")

        if not all([cabelo, barba_t, barba_tr, pezinho]):
            print("Planos não criados: serviços necessários não encontrados.")
            return

        plans_data = [
            ("Clube Athos — Cabelo + Barba",  220.00, [(cabelo, 4), (barba_t, 4)]),
            ("Clube Athos — Cabelo",           160.00, [(cabelo, 4)]),
            (
                "Clube Athos — Combo Completo (1 Cabelo e Barba + 2 Barbas + 2 Pezinhos)",
                130.00,
                [(cabelo, 1), (barba_t, 1), (barba_tr, 2), (pezinho, 3)],
            ),
        ]

        for name, price, credits in plans_data:
            plan = SubscriptionPlan(name=name, price=price, active=True)
            db.session.add(plan)
            db.session.flush()
            for svc, qty in credits:
                db.session.add(SubscriptionPlanCredit(
                    plan_id=plan.id, service_id=svc.id, quantity=qty
                ))

        db.session.commit()
        print(f"\n{len(plans_data)} plano(s) do Clube Athos inserido(s):\n")
        for name, price, credits in plans_data:
            print(f"  {name} — R$ {price:.2f}")
            for svc, qty in credits:
                print(f"    • {qty}x {svc.name}")
        print()


@app.cli.command("seed-admin")
def seed_admin():
    """Recria o usuário admin de desenvolvimento."""
    with app.app_context():
        from app.models.user import User

        if User.query.filter_by(username="admin").first():
            print("Usuário 'admin' já existe.")
        else:
            admin = User(username="admin", email="admin@barberhub.local", role="admin")
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            print("Admin criado: admin / admin123")


@app.cli.command("seed-prospect")
def seed_prospect():
    """Cria o usuário fixo da Prospect (idempotente)."""
    with app.app_context():
        from app.models.user import User

        if User.query.filter_by(username="prospect").first():
            print("Usuário 'prospect' já existe.")
            return

        prospect = User(
            username="prospect",
            email="administrativo@theprospect.com.br",
            role="admin",
        )
        prospect.set_password("Pro270326!")
        db.session.add(prospect)
        db.session.commit()
        print("Usuário criado: prospect / Pro270326!")


@app.cli.command("seed-kits")
def seed_kits():
    """Cria os kits de serviço (Cabelo + Barba etc.). Não insere se já houver kits."""
    with app.app_context():
        from app.models.service_kit import ServiceKit, ServiceKitItem
        from app.models.service import Service

        if ServiceKit.query.count() > 0:
            print("Kits já existem. Nenhum kit inserido.")
            return

        def _get(name):
            svc = Service.query.filter(
                db.func.lower(Service.name) == name.lower()
            ).first()
            if not svc:
                print(f"  AVISO: Serviço '{name}' não encontrado. Execute 'flask seed-services' primeiro.")
            return svc

        cabelo   = _get("Cabelo")
        barba_t  = _get("Barba Terapia")
        barba_tr = _get("Barba Tradicional")

        if not all([cabelo, barba_t, barba_tr]):
            print("Kits não criados: serviços necessários não encontrados.")
            return

        kits_data = [
            ("Cabelo + Barba",            [(cabelo, 1), (barba_t,  1)]),
            ("Cabelo + Barba Tradicional", [(cabelo, 1), (barba_tr, 1)]),
        ]

        for kit_name, items in kits_data:
            kit = ServiceKit(name=kit_name, active=True)
            db.session.add(kit)
            db.session.flush()
            for order, (svc, _) in enumerate(items, start=1):
                db.session.add(ServiceKitItem(kit_id=kit.id, service_id=svc.id, order=order))

        db.session.commit()
        print(f"\n{len(kits_data)} kit(s) inserido(s):\n")
        for kit_name, items in kits_data:
            svcs = " + ".join(s.name for s, _ in items)
            total_dur = sum(s.duration_minutes for s, _ in items)
            print(f"  {kit_name}: {svcs} ({total_dur} min)")
        print()


@app.cli.command("seed-services")
def seed_services():
    """Popula os serviços reais da Athos Barbearia. Não insere se já houver serviços."""
    with app.app_context():
        from app.models.service import Service

        if Service.query.count() > 0:
            print("Tabela de serviços já possui dados. Nenhum serviço inserido.")
            print("  Use 'flask reset-db' + 'flask seed-services' para recriar do zero.")
            return

        servicos = [
            # ── Avulsos ──────────────────────────────────────────────
            Service(name="Cabelo",             price=50.00, duration_minutes=30,  is_active=True),
            Service(name="Barba Terapia",      price=50.00, duration_minutes=40,  is_active=True),
            Service(name="Barba Tradicional",  price=40.00, duration_minutes=30,  is_active=True),
            Service(name="Sobrancelha",        price=10.00, duration_minutes=15,  is_active=True),
            Service(name="Pezinho",            price=10.00, duration_minutes=15,  is_active=True),
            # ── Clube Athos ───────────────────────────────────────────
            Service(
                name="Clube Athos — Cabelo + Barba",
                price=220.00, duration_minutes=60, is_active=True,
            ),
            Service(
                name="Clube Athos — Cabelo",
                price=160.00, duration_minutes=30, is_active=True,
            ),
            Service(
                name="Clube Athos — Combo Completo (1 Cabelo e Barba + 2 Barbas + 2 Pezinhos)",
                price=130.00, duration_minutes=90, is_active=True,
            ),
        ]

        for s in servicos:
            db.session.add(s)
        db.session.commit()

        print(f"\n{len(servicos)} serviço(s) inserido(s):\n")
        print(f"  {'Nome':<60} {'Preço':>8}  {'Duração'}")
        print(f"  {'-'*60} {'-'*8}  {'-'*8}")
        for s in servicos:
            print(f"  {s.name:<60} {s.price_formatted:>8}  {s.duration_formatted}")
        print()


if __name__ == "__main__":
    app.run(debug=app.debug, host="0.0.0.0", port=5000)
