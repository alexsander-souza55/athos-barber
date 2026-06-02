from functools import wraps
from flask import flash, redirect, url_for, render_template
from flask_login import current_user


def admin_required(f):
    """Permite apenas usuários com role='admin'. Redireciona ao dashboard com flash."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_admin:
            flash("Acesso restrito a administradores.", "danger")
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated


def barber_required(f):
    """Permite apenas usuários com role='barber'."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_barber:
            flash("Área exclusiva para barbeiros.", "warning")
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated


def own_barber_or_admin(barber_id_param: str = "barber_id"):
    """
    Permite admin (acesso total) ou o próprio barbeiro cujo ID está na rota.
    Uso: @own_barber_or_admin()  ou  @own_barber_or_admin('id')
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.is_admin:
                return f(*args, **kwargs)
            barber_id = kwargs.get(barber_id_param)
            profile = current_user.barber_profile
            if profile and profile.id == barber_id:
                return f(*args, **kwargs)
            flash("Você só pode acessar sua própria área.", "danger")
            return redirect(url_for("dashboard.index"))
        return decorated
    return decorator


def active_required(f):
    """Garante que o usuário autenticado ainda está ativo (camada extra de segurança)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.is_authenticated and not current_user.is_active:
            from flask_login import logout_user
            logout_user()
            flash("Sua conta foi desativada. Contate o administrador.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated
