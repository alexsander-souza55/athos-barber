import uuid
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
    date_str      = request.args.get("date", str(date.today()))
    status_filter = request.args.get("status", "")
    barber_filter = request.args.get("barber_id", type=int)

    try:
        filter_date = date.fromisoformat(date_str)
    except ValueError:
        filter_date = date.today()
        date_str = str(filter_date)

    query = Appointment.query.filter_by(scheduled_date=filter_date)

    if current_user.is_barber and current_user.barber_profile:
        query = query.filter_by(barber_id=current_user.barber_profile.id)
    elif current_user.is_admin and barber_filter:
        query = query.filter_by(barber_id=barber_filter)

    if status_filter:
        query = query.filter_by(status=status_filter)

    appointments = query.order_by(Appointment.scheduled_time).all()

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


# ── Admin / Barber: Criar agendamento ────────────────────────────────────────
WEEKDAY_NAMES_PT = {
    0: "segunda-feira",
    1: "terça-feira",
    2: "quarta-feira",
    3: "quinta-feira",
    4: "sexta-feira",
    5: "sábado",
    6: "domingo",
}


def _add_weeks(d: date, weeks: int) -> date:
    """Avança d por N semanas, mantendo o mesmo dia da semana."""
    return d + timedelta(weeks=weeks)


@appointments_bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if not current_user.is_admin and not current_user.is_barber:
        flash("Acesso negado.", "danger")
        return redirect(url_for("appointments.index"))

    from app.models.service_kit import ServiceKit

    form = AppointmentAdminForm()

    customers = Customer.query.order_by(Customer.name).all()
    services  = Service.query.filter_by(is_active=True).order_by(Service.name).all()
    kits      = ServiceKit.query.filter_by(active=True).order_by(ServiceKit.name).all()

    if current_user.is_barber and current_user.barber_profile:
        barbers = [current_user.barber_profile]
    else:
        barbers = Barber.query.filter_by(is_active=True).order_by(Barber.name).all()

    # Mapa service_id → assigned_barber_id para o JS travar o select
    service_barber_map = {
        s.id: s.assigned_barber_id
        for s in services
        if s.assigned_barber_id is not None
    }

    form.customer_id.choices = [
        (c.id, f"{c.name}" + (f"  ·  {c.phone}" if c.phone else ""))
        for c in customers
    ]
    form.barber_id.choices  = [(b.id, b.name) for b in barbers]
    form.service_id.choices = [(0, "— Selecione —")] + [
        (s.id, f"{s.name}  ·  {s.duration_formatted}  ·  {s.price_formatted}")
        for s in services
    ]

    if not customers:
        flash("Cadastre ao menos um cliente antes de criar um agendamento.", "warning")
    if not barbers:
        flash("Não há barbeiros ativos. Ative um barbeiro primeiro.", "warning")
    if not services and not kits:
        flash("Não há serviços nem kits ativos.", "warning")

    if form.validate_on_submit():
        kit_id_raw = request.form.get("kit_id", "").strip()
        kit_id = int(kit_id_raw) if kit_id_raw else None
        service_id = form.service_id.data or None

        sched_date = form.scheduled_date.data
        sched_time = datetime.strptime(form.scheduled_time.data.strip(), "%H:%M").time()
        notes_val  = (form.notes.data or "").strip() or None

        kit = None
        if kit_id:
            kit = ServiceKit.query.get(kit_id)
            if not kit:
                flash("Kit inválido.", "danger")
                return render_template("appointments/form.html", form=form,
                                       barbers=barbers, services=services, kits=kits,
                                       service_barber_map=service_barber_map)
            service_id = kit.items[0].service_id if kit.items else service_id

        if not service_id:
            flash("Selecione um serviço ou kit.", "danger")
            return render_template("appointments/form.html", form=form,
                                   barbers=barbers, services=services, kits=kits,
                                   service_barber_map=service_barber_map)

        # Se o serviço tem barbeiro exclusivo, força esse barbeiro
        svc_obj = Service.query.get(service_id)
        if svc_obj and svc_obj.assigned_barber_id:
            barber_id_to_use = svc_obj.assigned_barber_id
        elif current_user.is_barber and current_user.barber_profile:
            barber_id_to_use = current_user.barber_profile.id
        else:
            barber_id_to_use = form.barber_id.data

        # Recorrência
        is_recurring = request.form.get("is_recurring") == "1"
        recurring_weeks = 0
        if is_recurring:
            try:
                recurring_weeks = max(1, min(52, int(request.form.get("recurring_weeks", 1))))
            except (ValueError, TypeError):
                recurring_weeks = 1

        # Verifica disponibilidade do slot inicial
        if not is_slot_available(barber_id_to_use, service_id, sched_date, sched_time,
                                 kit_id=kit_id):
            flash("Horário indisponível: o barbeiro já tem um agendamento neste intervalo.", "danger")
            return render_template("appointments/form.html", form=form,
                                   barbers=barbers, services=services, kits=kits,
                                   service_barber_map=service_barber_map)

        from app.subscriptions.service import consume_credit, consume_credit_kit

        group_id = str(uuid.uuid4()) if is_recurring else None
        total_weeks = recurring_weeks if is_recurring else 0
        created_count = 0

        for offset in range(total_weeks + 1):
            current_date = _add_weeks(sched_date, offset) if offset > 0 else sched_date
            if offset > 0 and not is_slot_available(
                barber_id_to_use, service_id, current_date, sched_time, kit_id=kit_id
            ):
                continue  # pula semanas com conflito silenciosamente

            appt = Appointment(
                customer_id=form.customer_id.data,
                barber_id=barber_id_to_use,
                service_id=service_id,
                kit_id=kit_id,
                scheduled_date=current_date,
                scheduled_time=sched_time,
                notes=notes_val,
                is_recurring=is_recurring,
                recurring_group_id=group_id,
            )
            db.session.add(appt)
            db.session.flush()

            if kit:
                consume_credit_kit(form.customer_id.data, kit, appt.id)
            else:
                consume_credit(form.customer_id.data, service_id, appt.id)

            created_count += 1

        db.session.commit()

        if is_recurring and created_count > 1:
            customer = Customer.query.get(form.customer_id.data)
            weekday_name = WEEKDAY_NAMES_PT[sched_date.weekday()]
            flash(
                f"{created_count} agendamentos criados com sucesso para "
                f"{customer.name if customer else 'o cliente'} — "
                f"toda {weekday_name} às {sched_time.strftime('%H:%M')}, por {total_weeks} semana(s).",
                "success",
            )
        else:
            flash("Agendamento criado com sucesso!", "success")

        return redirect(url_for("appointments.index", date=str(sched_date)))

    return render_template("appointments/form.html", form=form,
                           barbers=barbers, services=services, kits=kits,
                           service_barber_map=service_barber_map)


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

    old_status = appt.status
    appt.status = new_status

    if new_status == "completed" and appt.customer:
        appt.customer.last_visit = datetime.now(timezone.utc)

    if new_status == "cancelled" and old_status != "cancelled":
        from app.subscriptions.service import refund_credit
        refund_credit(appt.id)

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

    from app.subscriptions.service import refund_credit
    refund_credit(appt.id)

    db.session.delete(appt)
    db.session.commit()
    flash("Agendamento removido.", "info")
    return redirect(url_for("appointments.index", date=appt_date))


# ── Público: Slots disponíveis (AJAX GET) ────────────────────────────────────
@appointments_bp.route("/slots")
def slots():
    barber_id  = request.args.get("barber_id",  type=int)
    service_id = request.args.get("service_id", type=int)
    kit_id     = request.args.get("kit_id",     type=int)
    date_str   = request.args.get("date", "")

    if not barber_id or not date_str or (not service_id and not kit_id):
        return jsonify({"slots": []})

    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"slots": []})

    if target_date < date.today():
        return jsonify({"slots": []})

    from app.models.barber_schedule_exception import BarberScheduleException
    exc = BarberScheduleException.query.filter_by(
        barber_id=barber_id, date=target_date
    ).first()
    if exc and exc.exception_type == "day_off":
        return jsonify({"slots": [], "reason": "day_off"})

    available = get_available_slots(barber_id, service_id, target_date, kit_id=kit_id)
    return jsonify({"slots": [t.strftime("%H:%M") for t in available]})


# ── Público: Agendamento online ───────────────────────────────────────────────
@appointments_bp.route("/book", methods=["GET", "POST"])
def book():
    from app.models.service_kit import ServiceKit
    services = Service.query.filter_by(is_active=True).order_by(Service.name).all()
    barbers  = Barber.query.filter_by(is_active=True).order_by(Barber.name).all()
    kits     = ServiceKit.query.filter_by(active=True).order_by(ServiceKit.name).all()
    form = BookingForm()

    if form.validate_on_submit():
        kit_id_raw = form.kit_id.data
        kit_id = int(kit_id_raw) if kit_id_raw else None
        service_id_raw = form.service_id.data

        missing = []
        if not kit_id and not service_id_raw:
            missing.append("serviço")
        if not form.barber_id.data:
            missing.append("barbeiro")
        if not form.scheduled_date.data:
            missing.append("data")
        if not form.scheduled_time.data:
            missing.append("horário")
        if missing:
            flash(f"Por favor, selecione: {', '.join(missing)}.", "warning")
            return render_template("appointments/book.html",
                                   form=form, services=services, barbers=barbers, kits=kits)

        try:
            sched_date = date.fromisoformat(form.scheduled_date.data)
            sched_time = datetime.strptime(form.scheduled_time.data, "%H:%M").time()
            barber_id  = int(form.barber_id.data)
        except (ValueError, TypeError):
            flash("Dados inválidos. Por favor, refaça a seleção.", "danger")
            return render_template("appointments/book.html",
                                   form=form, services=services, barbers=barbers, kits=kits)

        kit = None
        service_id = None
        if kit_id:
            kit = ServiceKit.query.get(kit_id)
            if not kit or not kit.active:
                flash("Kit inválido.", "danger")
                return render_template("appointments/book.html",
                                       form=form, services=services, barbers=barbers, kits=kits)
            service_id = kit.items[0].service_id if kit.items else None
        else:
            service_id = int(service_id_raw)

        if not service_id:
            flash("Serviço inválido.", "danger")
            return render_template("appointments/book.html",
                                   form=form, services=services, barbers=barbers, kits=kits)

        if not is_slot_available(barber_id, service_id, sched_date, sched_time,
                                 kit_id=kit_id):
            flash("Este horário não está mais disponível. Por favor, escolha outro.", "danger")
            return render_template("appointments/book.html",
                                   form=form, services=services, barbers=barbers, kits=kits)

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
                kit_id=kit_id,
                scheduled_date=sched_date,
                scheduled_time=sched_time,
                notes=(form.notes.data or "").strip() or None,
            )
            db.session.add(appt)
            db.session.flush()

            from app.subscriptions.service import consume_credit, consume_credit_kit
            if kit:
                consume_credit_kit(customer.id, kit, appt.id)
            else:
                consume_credit(customer.id, service_id, appt.id)

            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Erro ao salvar o agendamento. Por favor, tente novamente.", "danger")
            return render_template("appointments/book.html",
                                   form=form, services=services, barbers=barbers, kits=kits)

        return redirect(url_for("appointments.book_success", appt_id=appt.id))

    return render_template("appointments/book.html",
                           form=form, services=services, barbers=barbers, kits=kits)


# ── Público: Confirmação ──────────────────────────────────────────────────────
@appointments_bp.route("/book/success/<int:appt_id>")
def book_success(appt_id: int):
    appt = Appointment.query.get_or_404(appt_id)

    credit_items = []
    from app.models.subscription import SubscriptionCreditUsage, SubscriptionCreditBalance
    usages = SubscriptionCreditUsage.query.filter_by(appointment_id=appt_id).all()
    for usage in usages:
        balance = SubscriptionCreditBalance.query.filter_by(
            subscription_id=usage.subscription_id,
            service_id=usage.service_id,
        ).first()
        credit_items.append({
            "plan_name": (
                usage.subscription.plan.name
                if usage.subscription and usage.subscription.plan
                else "Clube Athos"
            ),
            "service_name": usage.service.name if usage.service else "—",
            "remaining": balance.remaining_credits if balance else 0,
            "total": balance.total_credits if balance else 0,
        })

    return render_template("appointments/book_success.html",
                           appt=appt, credit_items=credit_items)
