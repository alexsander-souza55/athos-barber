from datetime import datetime, date
from sqlalchemy import func
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from app.extensions import db
from app.models.barber import Barber
from app.models.user import User
from app.models.appointment import Appointment
from app.models.service import Service
from app.barbers.forms import CreateBarberForm, EditBarberForm
from app.utils.decorators import admin_required
from app.utils.helpers import save_upload, delete_upload, allowed_file

barbers_bp = Blueprint("barbers", __name__)


# ── Listagem ──────────────────────────────────────────────────────────────────
@barbers_bp.route("/")
@login_required
@admin_required
def index():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")  # "active" | "inactive" | ""

    query = Barber.query
    if q:
        query = query.filter(
            Barber.name.ilike(f"%{q}%") | Barber.specialty.ilike(f"%{q}%")
        )
    if status == "active":
        query = query.filter_by(is_active=True)
    elif status == "inactive":
        query = query.filter_by(is_active=False)

    barbers = query.order_by(Barber.is_active.desc(), Barber.name).all()

    # Estatísticas gerais para o resumo do topo
    summary = {
        "total": Barber.query.count(),
        "active": Barber.query.filter_by(is_active=True).count(),
        "today_total": sum(b.appointments_today() for b in barbers),
    }

    return render_template(
        "barbers/index.html",
        barbers=barbers, summary=summary, q=q, status=status,
    )


# ── Detalhe ───────────────────────────────────────────────────────────────────
@barbers_bp.route("/<int:barber_id>")
@login_required
@admin_required
def detail(barber_id: int):
    barber = Barber.query.get_or_404(barber_id)
    today = date.today()
    month_start = today.replace(day=1)

    # Stats
    revenue_total = float(
        db.session.query(func.sum(Service.price))
        .join(Appointment, Appointment.service_id == Service.id)
        .filter(
            Appointment.barber_id == barber_id,
            Appointment.status == "completed",
        )
        .scalar() or 0
    )
    revenue_month = float(
        db.session.query(func.sum(Service.price))
        .join(Appointment, Appointment.service_id == Service.id)
        .filter(
            Appointment.barber_id == barber_id,
            Appointment.status == "completed",
            Appointment.scheduled_date >= month_start,
        )
        .scalar() or 0
    )

    stats = {
        "total":         barber.total_appointments,
        "completed":     barber.completed_appointments,
        "this_month":    barber.appointments_this_month(),
        "today":         barber.appointments_today(),
        "revenue_total": revenue_total,
        "revenue_month": revenue_month,
    }

    # Agendamentos de hoje
    today_appts = (
        barber.appointments
        .filter_by(scheduled_date=today)
        .order_by(Appointment.scheduled_time)
        .all()
    )

    # Histórico recente
    recent = (
        barber.appointments
        .order_by(Appointment.scheduled_date.desc(), Appointment.scheduled_time.desc())
        .limit(20)
        .all()
    )

    return render_template(
        "barbers/detail.html",
        barber=barber, stats=stats,
        today_appts=today_appts, recent=recent, today=today,
    )


# ── Criar ─────────────────────────────────────────────────────────────────────
@barbers_bp.route("/new", methods=["GET", "POST"])
@login_required
@admin_required
def new():
    form = CreateBarberForm()

    if form.validate_on_submit():
        # 1. Cria usuário com role=barber
        user = User(
            username=form.username.data.strip(),
            email=form.email.data.strip(),
            role="barber",
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()  # obtém o ID do usuário

        # 2. Foto (opcional)
        photo_path = None
        photo_file = form.photo.data
        if photo_file and photo_file.filename:
            photo_path = save_upload(photo_file, subfolder="barbers")

        # 3. Horários
        work_start = _parse_time_safe(form.work_start_time.data)
        work_end   = _parse_time_safe(form.work_end_time.data)

        if work_start and work_end and work_start >= work_end:
            flash("O horário de início deve ser anterior ao horário de término.", "danger")
            return render_template("barbers/form.html", form=form, action="new")

        # 4. Cria perfil de barbeiro
        import re as _re
        barber = Barber(
            user_id=user.id,
            name=form.name.data.strip(),
            phone=form.phone.data.strip() or None,
            whatsapp=_re.sub(r'\D', '', form.whatsapp.data or '') or None,
            specialty=form.specialty.data.strip() or None,
            bio=form.bio.data.strip() or None,
            photo=photo_path,
            work_start_time=work_start,
            work_end_time=work_end,
        )
        db.session.add(barber)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Erro ao salvar. Verifique se o usuário ou e-mail já estão cadastrados.", "danger")
            return render_template("barbers/form.html", form=form, action="new")

        flash(f"Barbeiro '{barber.name}' cadastrado com sucesso!", "success")
        return redirect(url_for("barbers.detail", barber_id=barber.id))

    return render_template("barbers/form.html", form=form, action="new")


# ── Editar ────────────────────────────────────────────────────────────────────
@barbers_bp.route("/<int:barber_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit(barber_id: int):
    barber = Barber.query.get_or_404(barber_id)
    form = EditBarberForm(barber_id=barber_id)

    if request.method == "GET":
        form.name.data = barber.name
        form.phone.data = barber.phone or ""
        form.whatsapp.data = barber.whatsapp or ""
        form.specialty.data = barber.specialty or ""
        form.bio.data = barber.bio or ""
        form.work_start_time.data = barber.work_start_str
        form.work_end_time.data = barber.work_end_str
        form.is_active.data = barber.is_active

    if form.validate_on_submit():
        import re as _re
        barber.name = form.name.data.strip()
        barber.phone = form.phone.data.strip() or None
        barber.whatsapp = _re.sub(r'\D', '', form.whatsapp.data or '') or None
        barber.specialty = form.specialty.data.strip() or None
        barber.bio = form.bio.data.strip() or None
        work_start = _parse_time_safe(form.work_start_time.data)
        work_end   = _parse_time_safe(form.work_end_time.data)

        if work_start and work_end and work_start >= work_end:
            flash("O horário de início deve ser anterior ao horário de término.", "danger")
            return render_template("barbers/form.html", form=form, action="edit", barber=barber)

        barber.work_start_time = work_start
        barber.work_end_time = work_end
        barber.is_active = form.is_active.data

        # Gerenciamento de foto
        if form.remove_photo.data and barber.photo:
            delete_upload(barber.photo)
            barber.photo = None

        photo_file = form.photo.data
        if photo_file and photo_file.filename:
            try:
                new_photo = save_upload(photo_file, subfolder="barbers")
                if barber.photo:
                    delete_upload(barber.photo)
                barber.photo = new_photo
            except (ValueError, RuntimeError) as exc:
                flash(str(exc), "danger")
                return render_template("barbers/form.html", form=form, action="edit", barber=barber)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Erro ao salvar as alterações. Tente novamente.", "danger")
            return render_template("barbers/form.html", form=form, action="edit", barber=barber)

        flash(f"Barbeiro '{barber.name}' atualizado com sucesso!", "success")
        return redirect(url_for("barbers.detail", barber_id=barber.id))

    return render_template("barbers/form.html", form=form, action="edit", barber=barber)


# ── Ativar / Desativar ────────────────────────────────────────────────────────
@barbers_bp.route("/<int:barber_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle(barber_id: int):
    barber = Barber.query.get_or_404(barber_id)
    barber.is_active = not barber.is_active
    db.session.commit()
    status = "ativado" if barber.is_active else "desativado"
    flash(f"Barbeiro '{barber.name}' {status}.", "info")
    return redirect(url_for("barbers.index"))


# ── Excluir ───────────────────────────────────────────────────────────────────
@barbers_bp.route("/<int:barber_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete(barber_id: int):
    barber = Barber.query.get_or_404(barber_id)

    # Impede exclusão se há agendamentos vinculados
    total = barber.total_appointments
    if total > 0:
        flash(
            f"'{barber.name}' possui {total} agendamento(s) e não pode ser excluído. "
            "Desative-o em vez de excluir para preservar o histórico.",
            "warning",
        )
        return redirect(url_for("barbers.index"))

    name = barber.name
    user = barber.user

    # Remove foto do disco
    if barber.photo:
        delete_upload(barber.photo)

    db.session.delete(barber)
    db.session.flush()

    if user:
        db.session.delete(user)

    db.session.commit()
    flash(f"Barbeiro '{name}' e sua conta de acesso foram excluídos.", "info")
    return redirect(url_for("barbers.index"))


# ── Helpers internos ──────────────────────────────────────────────────────────
def _parse_time_safe(value: str):
    """Converte 'HH:MM' para time. Retorna None se vazio ou inválido."""
    if not value or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), "%H:%M").time()
    except ValueError:
        return None
