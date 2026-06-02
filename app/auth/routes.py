from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db
from app.models.user import User
from app.models.barber import Barber
from app.auth.forms import (
    LoginForm, ChangePasswordForm, ProfileForm,
    RegisterUserForm, EditUserForm, AdminResetPasswordForm,
)
from app.utils.decorators import admin_required

auth_bp = Blueprint("auth", __name__)


# ── Login ─────────────────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    lock_info = None  # {minutes: int} quando conta está bloqueada

    if form.validate_on_submit():
        username = form.username.data.strip().lower()
        user = User.query.filter(
            db.func.lower(User.username) == username
        ).first()

        # Usuário inexistente — mensagem genérica (não revelar se existe ou não)
        if not user:
            flash("Usuário ou senha inválidos.", "danger")
            return render_template("auth/login.html", form=form)

        # Conta bloqueada por tentativas excessivas
        if user.is_locked:
            lock_info = {"minutes": user.lock_remaining_minutes}
            flash(
                f"Conta bloqueada. Tente novamente em {user.lock_remaining_minutes} minuto(s).",
                "danger",
            )
            return render_template("auth/login.html", form=form, lock_info=lock_info)

        # Conta desativada
        if not user.is_active:
            flash("Sua conta foi desativada. Contate o administrador.", "warning")
            return render_template("auth/login.html", form=form)

        # Senha incorreta
        if not user.check_password(form.password.data):
            user.handle_failed_login()
            db.session.commit()
            remaining = max(0, 5 - user.failed_attempts)
            if user.is_locked:
                flash(
                    f"Conta bloqueada por {user.lock_remaining_minutes} minuto(s) "
                    "após múltiplas tentativas inválidas.",
                    "danger",
                )
            else:
                msg = f"Senha incorreta. {remaining} tentativa(s) restante(s)." if remaining < 3 else "Usuário ou senha inválidos."
                flash(msg, "danger")
            return render_template("auth/login.html", form=form)

        # Login bem-sucedido
        user.record_login()
        db.session.commit()
        login_user(user, remember=form.remember_me.data)

        flash(f"Bem-vindo de volta, {user.display_name}!", "success")
        next_page = request.args.get("next")
        # Proteção contra open redirect (bloqueia scheme/netloc absolutos, ex: //evil.com)
        if next_page:
            from urllib.parse import urlparse
            parsed = urlparse(next_page)
            if parsed.netloc or parsed.scheme:
                next_page = None
        return redirect(next_page or url_for("dashboard.index"))

    return render_template("auth/login.html", form=form, lock_info=lock_info)


# ── Logout ────────────────────────────────────────────────────────────────────
@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sessão encerrada com sucesso.", "info")
    return redirect(url_for("auth.login"))


# ── Perfil (usuário edita os próprios dados) ──────────────────────────────────
@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(user_id=current_user.id)

    if request.method == "GET":
        form.email.data = current_user.email
        if current_user.is_barber and current_user.barber_profile:
            bp = current_user.barber_profile
            form.name.data = bp.name
            form.phone.data = bp.phone
            form.specialty.data = bp.specialty
            form.bio.data = bp.bio

    if form.validate_on_submit():
        if form.email.data:
            current_user.email = form.email.data.strip()

        if current_user.is_barber and current_user.barber_profile:
            bp = current_user.barber_profile
            if form.name.data:
                bp.name = form.name.data.strip()
            bp.phone = form.phone.data.strip() if form.phone.data else bp.phone
            bp.specialty = form.specialty.data.strip() if form.specialty.data else bp.specialty
            bp.bio = form.bio.data.strip() if form.bio.data else bp.bio

        db.session.commit()
        flash("Perfil atualizado com sucesso!", "success")
        return redirect(url_for("auth.profile"))

    return render_template("auth/profile.html", form=form)


# ── Alterar senha (usuário altera a própria senha) ────────────────────────────
@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Senha atual incorreta.", "danger")
            return render_template("auth/change_password.html", form=form)
        current_user.set_password(form.new_password.data)
        db.session.commit()
        flash("Senha alterada com sucesso!", "success")
        return redirect(url_for("auth.profile"))
    return render_template("auth/change_password.html", form=form)


# ════════════════════════════════════════════════════════
#  GESTÃO DE USUÁRIOS — admin only
# ════════════════════════════════════════════════════════

@auth_bp.route("/users")
@login_required
@admin_required
def users():
    all_users = User.query.order_by(User.role, User.username).all()
    return render_template("auth/users/index.html", users=all_users)


@auth_bp.route("/users/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_user():
    form = RegisterUserForm()

    if form.validate_on_submit():
        user = User(
            username=form.username.data.strip(),
            email=form.email.data.strip(),
            role=form.role.data,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()  # obtém o ID antes do commit

        # Cria perfil de barbeiro automaticamente
        if form.role.data == "barber":
            barber = Barber(
                user_id=user.id,
                name=form.name.data.strip(),
                phone=form.phone.data.strip() if form.phone.data else None,
                specialty=form.specialty.data.strip() if form.specialty.data else None,
            )
            db.session.add(barber)

        db.session.commit()
        flash(f"Usuário '{user.username}' criado com sucesso!", "success")
        return redirect(url_for("auth.users"))

    return render_template("auth/users/form.html", form=form, action="new")


@auth_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id: int):
    user = User.query.get_or_404(user_id)
    form = EditUserForm(user_id=user_id)

    if request.method == "GET":
        form.username.data = user.username
        form.email.data = user.email
        form.role.data = user.role
        form.is_active.data = user.is_active

    if form.validate_on_submit():
        old_role = user.role
        user.username = form.username.data.strip()
        user.email = form.email.data.strip()
        user.is_active = form.is_active.data

        # Mudança de role admin → barber: cria perfil se não existir
        new_role = form.role.data
        user.role = new_role
        if new_role == "barber" and not user.barber_profile:
            barber = Barber(user_id=user.id, name=user.username)
            db.session.add(barber)

        db.session.commit()
        flash(f"Usuário '{user.username}' atualizado!", "success")
        return redirect(url_for("auth.users"))

    return render_template("auth/users/form.html", form=form, action="edit", user=user)


@auth_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_user(user_id: int):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Você não pode desativar a própria conta.", "warning")
        return redirect(url_for("auth.users"))

    user.is_active = not user.is_active
    db.session.commit()
    status = "ativado" if user.is_active else "desativado"
    flash(f"Usuário '{user.username}' {status}.", "info")
    return redirect(url_for("auth.users"))


@auth_bp.route("/users/<int:user_id>/reset-password", methods=["GET", "POST"])
@login_required
@admin_required
def reset_password(user_id: int):
    user = User.query.get_or_404(user_id)
    form = AdminResetPasswordForm()

    if form.validate_on_submit():
        user.set_password(form.new_password.data)
        user.reset_login_attempts()  # desbloqueia a conta junto
        db.session.commit()
        flash(f"Senha de '{user.username}' redefinida com sucesso!", "success")
        return redirect(url_for("auth.users"))

    return render_template("auth/users/reset_password.html", form=form, user=user)


@auth_bp.route("/users/<int:user_id>/unlock", methods=["POST"])
@login_required
@admin_required
def unlock_user(user_id: int):
    user = User.query.get_or_404(user_id)
    user.reset_login_attempts()
    db.session.commit()
    flash(f"Conta de '{user.username}' desbloqueada.", "success")
    return redirect(url_for("auth.users"))


@auth_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id: int):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Você não pode excluir a própria conta.", "danger")
        return redirect(url_for("auth.users"))

    # Impede remover o último admin ativo
    if user.is_admin:
        admin_count = User.query.filter_by(role="admin", is_active=True).count()
        if admin_count <= 1:
            flash("Não é possível remover o único administrador ativo.", "danger")
            return redirect(url_for("auth.users"))

    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f"Usuário '{username}' removido.", "info")
    return redirect(url_for("auth.users"))
