import re
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.extensions import db
from app.models.customer import Customer
from app.models.appointment import Appointment, APPOINTMENT_STATUSES
from app.models.barber import Barber
from app.appointments.availability import get_available_slots, is_slot_available

client_bp = Blueprint("client", __name__)


def _clean_cpf(cpf: str) -> str:
    return re.sub(r'\D', '', cpf or '')


def _format_cpf(cpf: str) -> str:
    c = _clean_cpf(cpf)
    if len(c) == 11:
        return f'{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}'
    return cpf


def _verify_ownership(appt: Appointment, cpf: str) -> bool:
    if not cpf or not appt.customer or not appt.customer.cpf:
        return False
    return _format_cpf(cpf) == appt.customer.cpf


def _load_appointments(customer: Customer, date_from: str, date_to: str):
    q = customer.appointments
    if date_from:
        try:
            q = q.filter(Appointment.scheduled_date >= date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(Appointment.scheduled_date <= date.fromisoformat(date_to))
        except ValueError:
            pass
    all_appts = q.order_by(
        Appointment.scheduled_date.desc(), Appointment.scheduled_time.desc()
    ).all()
    today = date.today()
    future = sorted(
        [a for a in all_appts if a.scheduled_date >= today],
        key=lambda a: (a.scheduled_date, a.scheduled_time),
    )
    past = [a for a in all_appts if a.scheduled_date < today]
    return future + past


@client_bp.route("/lookup", methods=["GET", "POST"])
def lookup():
    cpf_input = session.get("client_cpf", "")
    date_from = session.get("client_date_from", "")
    date_to = session.get("client_date_to", "")
    customer = None
    appointments = []

    if request.method == "POST":
        cpf_input = request.form.get("cpf", "").strip()
        date_from = request.form.get("date_from", "").strip()
        date_to = request.form.get("date_to", "").strip()

        clean = _clean_cpf(cpf_input)
        if not cpf_input:
            session.pop("client_cpf", None)
            session.pop("client_date_from", None)
            session.pop("client_date_to", None)
        elif len(clean) != 11:
            flash("CPF inválido. Informe os 11 dígitos.", "danger")
            session.pop("client_cpf", None)
        else:
            formatted = _format_cpf(cpf_input)
            found = Customer.query.filter_by(cpf=formatted).first()
            if not found:
                flash("CPF não encontrado. Verifique o número ou realize um agendamento.", "warning")
                session.pop("client_cpf", None)
            else:
                session["client_cpf"] = formatted
                session["client_date_from"] = date_from
                session["client_date_to"] = date_to
        return redirect(url_for("client.lookup"))

    # GET — restore from session
    if cpf_input:
        customer = Customer.query.filter_by(cpf=cpf_input).first()
        if customer:
            appointments = _load_appointments(customer, date_from, date_to)

    return render_template(
        "client/lookup.html",
        customer=customer,
        appointments=appointments,
        cpf_input=cpf_input,
        date_from=date_from,
        date_to=date_to,
        today=date.today(),
        STATUS_LABELS=APPOINTMENT_STATUSES,
    )


@client_bp.route("/appointment/<int:appt_id>/confirm", methods=["POST"])
def confirm_appointment(appt_id: int):
    appt = Appointment.query.get_or_404(appt_id)
    cpf = request.form.get("cpf", "").strip()

    if not _verify_ownership(appt, cpf):
        flash("Acesso negado.", "danger")
        return redirect(url_for("client.lookup"))

    if appt.status != "pending":
        flash("Apenas agendamentos pendentes podem ser confirmados.", "warning")
    else:
        appt.status = "confirmed"
        db.session.commit()
        flash("Agendamento confirmado!", "success")

    return redirect(url_for("client.lookup"))


@client_bp.route("/appointment/<int:appt_id>/cancel", methods=["POST"])
def cancel_appointment(appt_id: int):
    appt = Appointment.query.get_or_404(appt_id)
    cpf = request.form.get("cpf", "").strip()

    if not _verify_ownership(appt, cpf):
        flash("Acesso negado.", "danger")
        return redirect(url_for("client.lookup"))

    if appt.status not in ("pending", "confirmed"):
        flash("Este agendamento não pode ser cancelado.", "warning")
    else:
        appt.status = "cancelled"
        db.session.commit()
        flash("Agendamento cancelado.", "info")

    return redirect(url_for("client.lookup"))


@client_bp.route("/appointment/<int:appt_id>/reschedule", methods=["GET", "POST"])
def reschedule_appointment(appt_id: int):
    appt = Appointment.query.get_or_404(appt_id)
    cpf = session.get("client_cpf", "") if request.method == "GET" else request.form.get("cpf", "").strip()

    if not _verify_ownership(appt, cpf):
        flash("Acesso negado.", "danger")
        return redirect(url_for("client.lookup"))

    if appt.status not in ("pending", "confirmed"):
        flash("Este agendamento não pode ser remarcado.", "warning")
        return redirect(url_for("client.lookup"))

    barbers = Barber.query.filter_by(is_active=True).order_by(Barber.name).all()

    if request.method == "POST":
        barber_id = request.form.get("barber_id", type=int)
        date_str = request.form.get("scheduled_date", "").strip()
        time_str = request.form.get("scheduled_time", "").strip()

        errors = []
        sched_date = None
        sched_time = None

        if not barber_id:
            errors.append("Selecione um barbeiro.")
        if not date_str:
            errors.append("Selecione uma data.")
        if not time_str:
            errors.append("Selecione um horário.")

        if not errors:
            try:
                sched_date = date.fromisoformat(date_str)
                sched_time = datetime.strptime(time_str, "%H:%M").time()
            except ValueError:
                errors.append("Data ou horário inválido.")

        if not errors and sched_date < date.today():
            errors.append("A data não pode ser no passado.")

        if not errors:
            if not is_slot_available(barber_id, appt.service_id, sched_date, sched_time,
                                     exclude_appointment_id=appt.id):
                errors.append("Horário não disponível. Escolha outro slot.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "client/reschedule.html",
                appt=appt, barbers=barbers, cpf=cpf,
                today=date.today(), selected_barber_id=barber_id,
                selected_date=date_str, selected_time=time_str,
            )

        appt.status = "cancelled"
        new_appt = Appointment(
            customer_id=appt.customer_id,
            barber_id=barber_id,
            service_id=appt.service_id,
            scheduled_date=sched_date,
            scheduled_time=sched_time,
        )
        db.session.add(new_appt)
        db.session.commit()
        flash("Agendamento remarcado com sucesso!", "success")
        return redirect(url_for("client.lookup"))

    return render_template(
        "client/reschedule.html",
        appt=appt, barbers=barbers, cpf=cpf,
        today=date.today(),
        selected_barber_id=appt.barber_id,
        selected_date="", selected_time="",
    )


@client_bp.route("/slots")
def slots():
    barber_id = request.args.get("barber_id", type=int)
    service_id = request.args.get("service_id", type=int)
    date_str = request.args.get("date", "")
    exclude_id = request.args.get("exclude_id", type=int)

    if not all([barber_id, service_id, date_str]):
        return jsonify({"slots": []})
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"slots": []})
    if target_date < date.today():
        return jsonify({"slots": []})

    available = get_available_slots(barber_id, service_id, target_date,
                                    exclude_appointment_id=exclude_id)
    if target_date == date.today():
        now = datetime.now().time()
        available = [t for t in available if t > now]

    return jsonify({"slots": [t.strftime("%H:%M") for t in available]})
