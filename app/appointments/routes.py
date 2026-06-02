from datetime import date, datetime, timezone, timedelta
from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, request, jsonify,
)
from flask_login import login_required, current_user
from sqlalchemy import func
from app.extensions import db
from app.models.appointment import Appointment, APPOINTMENT_STATUSES
from app.models.barber import Barber
from app.models.customer import Customer
from app.models.service import Service
from app.appointments.forms import AppointmentAdminForm, BookingForm
from app.appointments.availability import get_available_slots, is_slot_available
from app.utils.decorators import admin_required

appointments_bp = Blueprint("appointments", __name__)


# ── Admin / Barber: Listagem ──────────────────────────────────────────────────
@appointments_bp.route("/")
@login_required
def index():
    date_str     = request.args.get("date", str(date.today()))
    status_filter = request.args.get("status", "")
    barber_filter = request.args.get("barber_id", type=int)

    try:
        filter_date = date.fromisoformat(date_str)
    except ValueError:
        filter_date = date.today()
        date_str = str(filter_date)

    query = Appointment.query.filter_by(scheduled_date=filter_date)

    # Barbers only see their own schedule
    if current_user.is_barber and current_user.barber_profile:
        query = query.filter_by(barber_id=current_user.barber_profile.id)
    elif current_user.is_admin and barber_filter:
        query = query.filter_by(barber_id=barber_filter)

    if status_filter:
        query = query.filter_by(status=status_filter)

    appointments = query.order_by(Appointment.scheduled_time).all()

    # Daily stats for today (regardless of current filter date)
    today = date.today()
    today_q = Appointment.query.filter_by(scheduled_date=today)
    if current_user.is_barber and current_user.barber_profile:
        today_q = today_q.filter_by(barber_id=current_user.barber_profile.id)

    stats = {
        "today_total":     today_q.count(),
        "today_pending":   today_q.filter(
                               Appointment.status.in_(["pending", "confirmed"])
                           ).count(),
        "today_completed": today_q.filter_by(status="completed").count(),
        "today_cancelled": today_q.filter(
                               Appointment.status.in_(["cancelled", "no_show"])
                           ).count(),
    }

    barbers = (
        Barber.query.filter_by(is_active=True).order_by(Barber.name).all()
        if current_user.is_admin else []
    )

    prev_date = str(filter_date - timedelta(days=1))
    next_date = str(filter_date + timedelta(days=1))

    return render_template(
        "appointments/index.html",
        appointments=appointments,
        date_str=date_str,
        filter_date=filter_date,
        prev_date=prev_date,
        next_date=next_date,
        status_filter=status_filter,
        barber_filter=barber_filter,
        stats=stats,
        barbers=barbers,
        STATUS_LABELS=APPOINTMENT_STATUSES,
    )


# ── Admin: Criar agendamento ──────────────────────────────────────────────────
@appointments_bp.route("/new", methods=["GET", "POST"])
@login_required
@admin_required
def new():
    form = AppointmentAdminForm()

    customers = Customer.query.order_by(Customer.name).all()
    barbers   = Barber.query.filter_by(is_active=True).order_by(Barber.name).all()
    services  = Service.query.filter_by(is_active=True).order_by(Service.name).all()

    form.customer_id.choices = [
        (c.id, f"{c.name}" + (f"  ·  {c.phone}" if c.phone else ""))
        for c in customers
    ]
    form.barber_id.choices  = [(b.id, b.name) for b in barbers]
    form.service_id.choices = [
        (s.id, f"{s.name}  ·  {s.duration_formatted}  ·  {s.price_formatted}")
        for s in services
    ]

    if not customers:
        flash("Cadastre ao menos um cliente antes de criar um agendamento.", "warning")
    if not barbers:
        flash("Não há barbeiros ativos. Ative um barbeiro primeiro.", "warning")
    if not services:
        flash("Não há serviços ativos. Ative um serviço primeiro.", "warning")

    if form.validate_on_submit():
        sched_date = form.scheduled_date.data
        sched_time = datetime.strptime(form.scheduled_time.data.strip(), "%H:%M").time()

        if not is_slot_available(form.barber_id.data, form.service_id.data, sched_date, sched_time):
            flash(
                "Horário indisponível: o barbeiro já tem um agendamento neste intervalo.",
                "danger",
            )
            return render_template("appointments/form.html", form=form,
                                   barbers=barbers, services=services)

        appt = Appointment(
            customer_id=form.customer_id.data,
            barber_id=form.barber_id.data,
            service_id=form.service_id.data,
            scheduled_date=sched_date,
            scheduled_time=sched_time,
            notes=(form.notes.data or "").strip() or None,
        )
        db.session.add(appt)
        db.session.commit()
        flash("Agendamento criado com sucesso!", "success")
        return redirect(url_for("appointments.index", date=str(sched_date)))

    return render_template("appointments/form.html", form=form,
                           barbers=barbers, services=services)


# ── Admin / Barber: Atualizar status ─────────────────────────────────────────
@appointments_bp.route("/<int:appt_id>/status", methods=["POST"])
@login_required
def update_status(appt_id: int):
    appt = Appointment.query.get_or_404(appt_id)

    if current_user.is_barber and current_user.barber_profile:
        if appt.barber_id != current_user.barber_profile.id:
            flash("Acesso negado.", "danger")
            return redirect(url_for("appointments.index"))

    new_status = request.form.get("status", "")
    if new_status not in APPOINTMENT_STATUSES:
        flash("Status inválido.", "danger")
        return redirect(url_for("appointments.index", date=str(appt.scheduled_date)))

    appt.status = new_status
    if new_status == "completed" and appt.customer:
        appt.customer.last_visit = datetime.now(timezone.utc)

    db.session.commit()
    flash(f"Status atualizado para '{APPOINTMENT_STATUSES[new_status]}'.", "success")
    return redirect(url_for("appointments.index", date=str(appt.scheduled_date)))


# ── Admin: Excluir ────────────────────────────────────────────────────────────
@appointments_bp.route("/<int:appt_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete(appt_id: int):
    appt = Appointment.query.get_or_404(appt_id)
    appt_date = str(appt.scheduled_date)
    db.session.delete(appt)
    db.session.commit()
    flash("Agendamento removido.", "info")
    return redirect(url_for("appointments.index", date=appt_date))


# ── Público: Slots disponíveis (AJAX GET) ────────────────────────────────────
@appointments_bp.route("/slots")
def slots():
    """
    Retorna JSON com horários disponíveis.
    GET /appointments/slots?barber_id=1&service_id=2&date=2026-05-20
    Resposta: {"slots": ["09:00", "09:30", ...]}
    """
    barber_id  = request.args.get("barber_id",  type=int)
    service_id = request.args.get("service_id", type=int)
    date_str   = request.args.get("date", "")

    if not all([barber_id, service_id, date_str]):
        return jsonify({"slots": []})

    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"slots": []})

    if target_date < date.today():
        return jsonify({"slots": []})

    available = get_available_slots(barber_id, service_id, target_date)
    return jsonify({"slots": [t.strftime("%H:%M") for t in available]})


# ── Público: Agendamento online ───────────────────────────────────────────────
@appointments_bp.route("/book", methods=["GET", "POST"])
def book():
    """Wizard público de agendamento — não requer login."""
    services = Service.query.filter_by(is_active=True).order_by(Service.name).all()
    barbers  = Barber.query.filter_by(is_active=True).order_by(Barber.name).all()
    form = BookingForm()

    if form.validate_on_submit():
        # Valida se todos os campos do wizard foram preenchidos
        missing = [
            label for value, label in [
                (form.service_id.data,     "serviço"),
                (form.barber_id.data,      "barbeiro"),
                (form.scheduled_date.data, "data"),
                (form.scheduled_time.data, "horário"),
            ] if not value
        ]
        if missing:
            flash(f"Por favor, selecione: {', '.join(missing)}.", "warning")
            return render_template("appointments/book.html",
                                   form=form, services=services, barbers=barbers)

        try:
            sched_date = date.fromisoformat(form.scheduled_date.data)
            sched_time = datetime.strptime(form.scheduled_time.data, "%H:%M").time()
            barber_id  = int(form.barber_id.data)
            service_id = int(form.service_id.data)
        except (ValueError, TypeError):
            flash("Dados inválidos. Por favor, refaça a seleção.", "danger")
            return render_template("appointments/book.html",
                                   form=form, services=services, barbers=barbers)

        # Dupla verificação de disponibilidade (evita race condition e bypass de JS)
        if not is_slot_available(barber_id, service_id, sched_date, sched_time):
            flash(
                "Este horário não está mais disponível. Por favor, escolha outro.",
                "danger",
            )
            return render_template("appointments/book.html",
                                   form=form, services=services, barbers=barbers)

        # Cria ou recupera cliente pelo CPF/telefone e salva o agendamento
        try:
            customer, _ = Customer.get_or_create(
                name=form.customer_name.data,
                phone=form.customer_phone.data,
                cpf=form.customer_cpf.data,
            )
            db.session.flush()

            appt = Appointment(
                customer_id=customer.id,
                barber_id=barber_id,
                service_id=service_id,
                scheduled_date=sched_date,
                scheduled_time=sched_time,
                notes=(form.notes.data or "").strip() or None,
            )
            db.session.add(appt)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Erro ao salvar o agendamento. Por favor, tente novamente.", "danger")
            return render_template("appointments/book.html",
                                   form=form, services=services, barbers=barbers)

        return redirect(url_for("appointments.book_success", appt_id=appt.id))

    return render_template("appointments/book.html",
                           form=form, services=services, barbers=barbers)


# ── Público: Confirmação ──────────────────────────────────────────────────────
@appointments_bp.route("/book/success/<int:appt_id>")
def book_success(appt_id: int):
    appt = Appointment.query.get_or_404(appt_id)
    return render_template("appointments/book_success.html", appt=appt)
