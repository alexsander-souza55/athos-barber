import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, redirect, url_for, flash
from flask_login import current_user, logout_user
from app.config import config
from app.extensions import db, login_manager, csrf


def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    _configure_logging(app)
    _register_blueprints(app)
    _configure_login_manager()
    _register_error_handlers(app)
    _register_middleware(app)
    _register_shell_context(app)
    _register_context_processors(app)
    _register_template_filters(app)
    _ensure_schema(app)

    return app


def _configure_logging(app: Flask) -> None:
    """Configura logging para arquivo rotativo em ambiente não-debug."""
    if app.debug:
        return

    log_dir = os.path.join(os.path.dirname(app.root_path), "logs")
    os.makedirs(log_dir, exist_ok=True)

    handler = RotatingFileHandler(
        os.path.join(log_dir, "barberhub.log"),
        maxBytes=1_000_000,   # 1 MB por arquivo
        backupCount=5,
        encoding="utf-8",
    )
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s %(module)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.WARNING)


def _register_blueprints(app: Flask) -> None:
    from app.auth.routes import auth_bp
    from app.dashboard.routes import dashboard_bp
    from app.barbers.routes import barbers_bp
    from app.customers.routes import customers_bp
    from app.services.routes import services_bp
    from app.appointments.routes import appointments_bp
    from app.raffle.routes import raffle_bp
    from app.reports.routes import reports_bp
    from app.client.routes import client_bp

    app.register_blueprint(auth_bp,         url_prefix="/auth")
    app.register_blueprint(dashboard_bp,    url_prefix="/")
    app.register_blueprint(barbers_bp,      url_prefix="/barbers")
    app.register_blueprint(customers_bp,    url_prefix="/customers")
    app.register_blueprint(services_bp,     url_prefix="/services")
    app.register_blueprint(appointments_bp, url_prefix="/appointments")
    app.register_blueprint(raffle_bp,       url_prefix="/raffle")
    app.register_blueprint(reports_bp,      url_prefix="/reports")
    app.register_blueprint(client_bp,       url_prefix="/client")


def _configure_login_manager() -> None:
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))


def _register_middleware(app: Flask) -> None:
    """Middleware global — encerra sessão de usuários desativados."""

    @app.before_request
    def enforce_active_session():
        if current_user.is_authenticated and not current_user.is_active:
            logout_user()
            flash("Sua conta foi desativada. Contate o administrador.", "danger")
            return redirect(url_for("auth.login"))


def _register_error_handlers(app: Flask) -> None:

    @app.errorhandler(400)
    def bad_request(e):
        return render_template("errors/400.html"), 400

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        app.logger.exception("Erro 500: %s", e)
        return render_template("errors/500.html"), 500


def _register_context_processors(app: Flask) -> None:
    from datetime import datetime, timezone

    @app.context_processor
    def inject_now():
        return {"now": datetime.now(timezone.utc)}


def _register_template_filters(app: Flask) -> None:
    import re

    @app.template_filter("wa_number")
    def wa_number_filter(phone: str) -> str:
        if not phone:
            return ""
        digits = re.sub(r"\D", "", phone)
        if not digits:
            return ""
        if not digits.startswith("55"):
            digits = "55" + digits
        return digits


def _ensure_schema(app: Flask) -> None:
    """Adiciona colunas novas sem quebrar tabelas existentes (SQLite sem Alembic)."""
    with app.app_context():
        from sqlalchemy import inspect, text
        db.create_all()
        inspector = inspect(db.engine)
        migrations = [
            ("customers", "cpf",      "VARCHAR(14)"),
            ("barbers",   "whatsapp", "VARCHAR(20)"),
        ]
        with db.engine.connect() as conn:
            for table, col, col_def in migrations:
                try:
                    existing = {c["name"] for c in inspector.get_columns(table)}
                    if col not in existing:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"))
                        conn.commit()
                except Exception:
                    pass


def _register_shell_context(app: Flask) -> None:
    from app.models import User, Barber, Customer, Service, Appointment, Raffle

    @app.shell_context_processor
    def make_shell_context():
        return {
            "db": db,
            "User": User,
            "Barber": Barber,
            "Customer": Customer,
            "Service": Service,
            "Appointment": Appointment,
            "Raffle": Raffle,
        }
