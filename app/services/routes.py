from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import func
from app.extensions import db
from app.models.service import Service
from app.models.barber import Barber
from app.services.forms import ServiceForm
from app.utils.decorators import admin_required

services_bp = Blueprint("services", __name__)


def _barber_owns_service(service: Service) -> bool:
    """True se o barbeiro logado é o dono exclusivo deste serviço."""
    if not current_user.is_barber or not current_user.barber_profile:
        return False
    return service.assigned_barber_id == current_user.barber_profile.id


def _can_edit_service(service: Service) -> bool:
    return current_user.is_admin or _barber_owns_service(service)


def _barber_choices():
    return [(0, "— Selecione —")] + [
        (b.id, b.name)
        for b in Barber.query.filter_by(is_active=True).order_by(Barber.name).all()
    ]


# ── Listagem ──────────────────────────────────────────────────────────────────
@services_bp.route("/")
@login_required
def index():
    if not current_user.is_admin and not current_user.is_barber:
        flash("Acesso negado.", "danger")
        return redirect(url_for("dashboard.index"))

    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")

    query = Service.query
    if q:
        query = query.filter(Service.name.ilike(f"%{q}%"))
    if status == "active":
        query = query.filter_by(is_active=True)
    elif status == "inactive":
        query = query.filter_by(is_active=False)

    services = query.order_by(Service.is_active.desc(), Service.name).all()

    avg_price = float(
        db.session.query(func.avg(Service.price))
        .filter(Service.is_active.is_(True))
        .scalar() or 0
    )
    summary = {
        "total":     Service.query.count(),
        "active":    Service.query.filter_by(is_active=True).count(),
        "inactive":  Service.query.filter_by(is_active=False).count(),
        "avg_price": avg_price,
    }

    return render_template(
        "services/index.html",
        services=services, summary=summary, q=q, status=status,
    )


# ── Criar ─────────────────────────────────────────────────────────────────────
@services_bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if not current_user.is_admin and not current_user.is_barber:
        flash("Acesso negado.", "danger")
        return redirect(url_for("dashboard.index"))

    form = ServiceForm()
    form.assigned_barber_id.choices = _barber_choices()

    if request.method == "GET":
        form.duration_minutes.data = 30

    if form.validate_on_submit():
        # Determina assigned_barber_id
        if form.is_exclusive.data:
            if current_user.is_admin:
                assigned = form.assigned_barber_id.data or None
            else:
                assigned = current_user.barber_profile.id if current_user.barber_profile else None
        else:
            assigned = None

        service = Service(
            name=form.name.data.strip(),
            description=(form.description.data or "").strip() or None,
            price=form.price.data,
            duration_minutes=form.duration_minutes.data,
            is_active=True,
            assigned_barber_id=assigned,
        )
        db.session.add(service)
        db.session.commit()
        flash(f"Serviço '{service.name}' cadastrado com sucesso!", "success")
        return redirect(url_for("services.index"))

    return render_template("services/form.html", form=form, action="new")


# ── Editar ────────────────────────────────────────────────────────────────────
@services_bp.route("/<int:service_id>/edit", methods=["GET", "POST"])
@login_required
def edit(service_id: int):
    service = Service.query.get_or_404(service_id)

    if not _can_edit_service(service):
        flash("Você não tem permissão para editar este serviço.", "danger")
        return redirect(url_for("services.index"))

    form = ServiceForm(service_id=service_id)
    form.assigned_barber_id.choices = _barber_choices()

    if request.method == "GET":
        form.name.data = service.name
        form.description.data = service.description or ""
        form.price.data = service.price
        form.duration_minutes.data = service.duration_minutes
        form.is_active.data = service.is_active
        form.is_exclusive.data = service.assigned_barber_id is not None
        form.assigned_barber_id.data = service.assigned_barber_id or 0

    if form.validate_on_submit():
        service.name = form.name.data.strip()
        service.description = (form.description.data or "").strip() or None
        service.price = form.price.data
        service.duration_minutes = form.duration_minutes.data

        if current_user.is_admin:
            service.is_active = form.is_active.data
            if form.is_exclusive.data:
                service.assigned_barber_id = form.assigned_barber_id.data or None
            else:
                service.assigned_barber_id = None
        else:
            # Barbeiro só pode manter/remover a exclusividade própria
            if form.is_exclusive.data:
                service.assigned_barber_id = (
                    current_user.barber_profile.id if current_user.barber_profile else None
                )
            else:
                service.assigned_barber_id = None

        db.session.commit()
        flash(f"Serviço '{service.name}' atualizado com sucesso!", "success")
        return redirect(url_for("services.index"))

    return render_template("services/form.html", form=form, action="edit", service=service)


# ── Ativar / Desativar ────────────────────────────────────────────────────────
@services_bp.route("/<int:service_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle(service_id: int):
    service = Service.query.get_or_404(service_id)
    service.is_active = not service.is_active
    db.session.commit()
    status = "ativado" if service.is_active else "desativado"
    flash(f"Serviço '{service.name}' {status}.", "info")
    return redirect(url_for("services.index"))


# ── Excluir ───────────────────────────────────────────────────────────────────
@services_bp.route("/<int:service_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete(service_id: int):
    service = Service.query.get_or_404(service_id)
    total = service.appointments.count()
    if total > 0:
        flash(
            f"'{service.name}' possui {total} agendamento(s) vinculado(s) e não pode ser excluído. "
            "Desative-o para removê-lo da lista de opções.",
            "warning",
        )
        return redirect(url_for("services.index"))

    name = service.name
    db.session.delete(service)
    db.session.commit()
    flash(f"Serviço '{name}' excluído com sucesso.", "info")
    return redirect(url_for("services.index"))
