from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import func, distinct
from app.extensions import db
from app.models.customer import Customer
from app.models.appointment import Appointment
from app.models.service import Service
from app.customers.forms import CustomerForm
from app.utils.decorators import admin_required

customers_bp = Blueprint("customers", __name__)


# ── Listagem ──────────────────────────────────────────────────────────────────
@customers_bp.route("/")
@login_required
@admin_required
def index():
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "name")

    query = Customer.query
    if q:
        query = query.filter(
            Customer.name.ilike(f"%{q}%") | Customer.phone.ilike(f"%{q}%")
        )

    if sort == "recent":
        query = query.order_by(Customer.created_at.desc())
    elif sort == "visits":
        visits_sq = (
            db.session.query(
                Appointment.customer_id,
                func.count(Appointment.id).label("cnt"),
            )
            .filter_by(status="completed")
            .group_by(Appointment.customer_id)
            .subquery()
        )
        query = (
            query
            .outerjoin(visits_sq, Customer.id == visits_sq.c.customer_id)
            .order_by(func.coalesce(visits_sq.c.cnt, 0).desc(), Customer.name)
        )
    else:
        query = query.order_by(Customer.name)

    customers = query.all()

    today = date.today()
    month_start = today.replace(day=1)
    summary = {
        "total":        Customer.query.count(),
        "new_month":    Customer.query.filter(Customer.created_at >= month_start).count(),
        "attended":     db.session.query(
                            func.count(distinct(Appointment.customer_id))
                        ).filter_by(status="completed").scalar() or 0,
        "total_visits": Appointment.query.filter_by(status="completed").count(),
    }

    return render_template(
        "customers/index.html",
        customers=customers, summary=summary, q=q, sort=sort,
    )


# ── Detalhe ───────────────────────────────────────────────────────────────────
@customers_bp.route("/<int:customer_id>")
@login_required
@admin_required
def detail(customer_id: int):
    customer = Customer.query.get_or_404(customer_id)

    revenue = float(
        db.session.query(func.sum(Service.price))
        .join(Appointment, Appointment.service_id == Service.id)
        .filter(
            Appointment.customer_id == customer_id,
            Appointment.status == "completed",
        )
        .scalar() or 0
    )

    last_appt = (
        customer.appointments
        .filter_by(status="completed")
        .order_by(Appointment.scheduled_date.desc(), Appointment.scheduled_time.desc())
        .first()
    )

    recent = (
        customer.appointments
        .order_by(Appointment.scheduled_date.desc(), Appointment.scheduled_time.desc())
        .limit(20)
        .all()
    )

    stats = {
        "total":     customer.total_appointments,
        "completed": customer.total_visits,
        "pending":   customer.pending_appointments,
        "revenue":   revenue,
        "last_appt": last_appt,
    }

    return render_template(
        "customers/detail.html",
        customer=customer, stats=stats, recent=recent,
    )


# ── Criar ─────────────────────────────────────────────────────────────────────
@customers_bp.route("/new", methods=["GET", "POST"])
@login_required
@admin_required
def new():
    form = CustomerForm()

    if form.validate_on_submit():
        import re as _re
        cpf_raw = (form.cpf.data or "").strip()
        cpf_clean = _re.sub(r'\D', '', cpf_raw)
        cpf_fmt = f'{cpf_clean[:3]}.{cpf_clean[3:6]}.{cpf_clean[6:9]}-{cpf_clean[9:]}' if len(cpf_clean) == 11 else None
        customer = Customer(
            name=form.name.data.strip(),
            phone=(form.phone.data or "").strip() or None,
            cpf=cpf_fmt,
            email=(form.email.data or "").strip() or None,
            birth_date=form.birth_date.data,
            notes=(form.notes.data or "").strip() or None,
        )
        db.session.add(customer)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Erro ao salvar. Verifique se o CPF já está cadastrado.", "danger")
            return render_template("customers/form.html", form=form, action="new")
        flash(f"Cliente '{customer.name}' cadastrado com sucesso!", "success")
        return redirect(url_for("customers.detail", customer_id=customer.id))

    return render_template("customers/form.html", form=form, action="new")


# ── Editar ────────────────────────────────────────────────────────────────────
@customers_bp.route("/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit(customer_id: int):
    customer = Customer.query.get_or_404(customer_id)
    form = CustomerForm(customer_id=customer_id)

    if request.method == "GET":
        form.name.data = customer.name
        form.phone.data = customer.phone or ""
        form.cpf.data = customer.cpf or ""
        form.email.data = customer.email or ""
        form.birth_date.data = customer.birth_date
        form.notes.data = customer.notes or ""

    if form.validate_on_submit():
        import re as _re
        cpf_raw = (form.cpf.data or "").strip()
        cpf_clean = _re.sub(r'\D', '', cpf_raw)
        cpf_fmt = f'{cpf_clean[:3]}.{cpf_clean[3:6]}.{cpf_clean[6:9]}-{cpf_clean[9:]}' if len(cpf_clean) == 11 else None
        customer.name = form.name.data.strip()
        customer.phone = (form.phone.data or "").strip() or None
        customer.cpf = cpf_fmt
        customer.email = (form.email.data or "").strip() or None
        customer.birth_date = form.birth_date.data
        customer.notes = (form.notes.data or "").strip() or None
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Erro ao salvar. Verifique se o CPF já está cadastrado.", "danger")
            return render_template("customers/form.html", form=form, action="edit", customer=customer)
        flash(f"Cliente '{customer.name}' atualizado com sucesso!", "success")
        return redirect(url_for("customers.detail", customer_id=customer.id))

    return render_template("customers/form.html", form=form, action="edit", customer=customer)


# ── Excluir ───────────────────────────────────────────────────────────────────
@customers_bp.route("/<int:customer_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete(customer_id: int):
    customer = Customer.query.get_or_404(customer_id)
    total = customer.total_appointments
    if total > 0:
        flash(
            f"'{customer.name}' possui {total} agendamento(s) e não pode ser excluído. "
            "Remova os agendamentos vinculados antes de excluir o cliente.",
            "warning",
        )
        return redirect(url_for("customers.index"))

    name = customer.name
    db.session.delete(customer)
    db.session.commit()
    flash(f"Cliente '{name}' excluído.", "info")
    return redirect(url_for("customers.index"))
