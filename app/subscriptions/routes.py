from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required
from app.extensions import db
from app.models.subscription_plan import SubscriptionPlan
from app.models.subscription import (
    CustomerSubscription, SubscriptionCreditBalance, SubscriptionCreditUsage
)
from app.models.customer import Customer
from app.utils.decorators import admin_required
from app.subscriptions.service import get_active_subscription, check_credit, check_credit_kit

subscriptions_bp = Blueprint("subscriptions", __name__)

_VALIDITY_OPTIONS = [
    ("30",  "30 dias"),
    ("45",  "45 dias"),
    ("60",  "60 dias"),
    ("90",  "90 dias"),
    ("custom", "Data personalizada"),
]


def _resolve_end_date(start: date) -> date:
    """Lê validity_days / end_date_custom do request e retorna end_date calculado."""
    validity = request.form.get("validity_days", "30").strip()
    if validity == "custom":
        raw = request.form.get("end_date_custom", "").strip()
        try:
            end = date.fromisoformat(raw)
            if end <= start:
                flash("Data personalizada deve ser após a data de início. Usando 30 dias.", "warning")
                return start + timedelta(days=30)
            return end
        except ValueError:
            flash("Data personalizada inválida. Usando 30 dias.", "warning")
            return start + timedelta(days=30)
    try:
        days = int(validity)
        if days not in (30, 45, 60, 90):
            days = 30
    except ValueError:
        days = 30
    return start + timedelta(days=days)


# ── Listagem ──────────────────────────────────────────────────────────────────
@subscriptions_bp.route("/")
@login_required
@admin_required
def index():
    status_filter = request.args.get("status", "")
    today = date.today()

    query = CustomerSubscription.query
    if status_filter == "active":
        query = query.filter_by(status="active").filter(
            CustomerSubscription.end_date >= today
        )
    elif status_filter == "expiring":
        query = query.filter_by(status="active").filter(
            CustomerSubscription.end_date >= today,
            CustomerSubscription.end_date <= today + timedelta(days=3),
        )
    elif status_filter == "expired":
        query = query.filter_by(status="active").filter(
            CustomerSubscription.end_date < today
        )
    elif status_filter == "cancelled":
        query = query.filter_by(status="cancelled")

    subscriptions = query.order_by(CustomerSubscription.end_date.desc()).all()

    summary = {
        "total": CustomerSubscription.query.count(),
        "active": CustomerSubscription.query.filter_by(status="active").filter(
            CustomerSubscription.end_date >= today
        ).count(),
        "expiring": CustomerSubscription.query.filter_by(status="active").filter(
            CustomerSubscription.end_date >= today,
            CustomerSubscription.end_date <= today + timedelta(days=3),
        ).count(),
        "expired": CustomerSubscription.query.filter_by(status="active").filter(
            CustomerSubscription.end_date < today
        ).count(),
    }

    return render_template(
        "subscriptions/index.html",
        subscriptions=subscriptions,
        summary=summary,
        status_filter=status_filter,
        today=today,
    )


# ── Nova assinatura ────────────────────────────────────────────────────────────
@subscriptions_bp.route("/new", methods=["GET", "POST"])
@login_required
@admin_required
def new():
    plans = SubscriptionPlan.query.filter_by(active=True).order_by(SubscriptionPlan.name).all()
    customers = Customer.query.order_by(Customer.name).all()

    if request.method == "POST":
        customer_id = request.form.get("customer_id", type=int)
        plan_id = request.form.get("plan_id", type=int)
        start_date_str = request.form.get("start_date", "").strip()

        errors = []
        if not customer_id:
            errors.append("Selecione um cliente.")
        if not plan_id:
            errors.append("Selecione um plano.")

        customer = Customer.query.get(customer_id) if customer_id else None
        plan = SubscriptionPlan.query.get(plan_id) if plan_id else None

        if customer_id and not customer:
            errors.append("Cliente não encontrado.")
        if plan_id and not plan:
            errors.append("Plano não encontrado.")

        try:
            start = date.fromisoformat(start_date_str) if start_date_str else date.today()
        except ValueError:
            start = date.today()

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "subscriptions/form.html",
                plans=plans, customers=customers, validity_options=_VALIDITY_OPTIONS,
            )

        end = _resolve_end_date(start)

        # Cancela assinatura ativa anterior (se houver)
        existing = get_active_subscription(customer_id)
        if existing:
            existing.status = "cancelled"

        sub = CustomerSubscription(
            customer_id=customer_id,
            plan_id=plan_id,
            start_date=start,
            end_date=end,
        )
        db.session.add(sub)
        db.session.flush()

        for plan_credit in plan.credits:
            db.session.add(SubscriptionCreditBalance(
                subscription_id=sub.id,
                service_id=plan_credit.service_id,
                total_credits=plan_credit.quantity,
                used_credits=0,
            ))

        db.session.commit()
        flash(f"Assinatura do Clube Athos criada para '{customer.name}'!", "success")
        return redirect(url_for("subscriptions.detail", sub_id=sub.id))

    return render_template(
        "subscriptions/form.html",
        plans=plans, customers=customers, validity_options=_VALIDITY_OPTIONS,
    )


# ── Detalhe ───────────────────────────────────────────────────────────────────
@subscriptions_bp.route("/<int:sub_id>")
@login_required
@admin_required
def detail(sub_id: int):
    sub = CustomerSubscription.query.get_or_404(sub_id)
    usages = (
        sub.credit_usages
        .order_by(SubscriptionCreditUsage.used_at.desc())
        .all()
    )
    return render_template(
        "subscriptions/detail.html",
        sub=sub,
        usages=usages,
        today=date.today(),
        validity_options=_VALIDITY_OPTIONS,
    )


# ── Renovar (estende assinatura existente) ────────────────────────────────────
@subscriptions_bp.route("/<int:sub_id>/renew", methods=["POST"])
@login_required
@admin_required
def renew(sub_id: int):
    sub = CustomerSubscription.query.get_or_404(sub_id)
    new_start = date.today()
    new_end = _resolve_end_date(new_start)

    sub.end_date = new_end
    sub.renewed_at = datetime.utcnow()
    sub.status = "active"

    # Soma os créditos do plano ao saldo atual (créditos não usados permanecem)
    for plan_credit in sub.plan.credits:
        balance = SubscriptionCreditBalance.query.filter_by(
            subscription_id=sub.id,
            service_id=plan_credit.service_id,
        ).first()
        if balance:
            balance.total_credits += plan_credit.quantity
        else:
            db.session.add(SubscriptionCreditBalance(
                subscription_id=sub.id,
                service_id=plan_credit.service_id,
                total_credits=plan_credit.quantity,
                used_credits=0,
            ))

    db.session.commit()
    flash("Assinatura renovada! Créditos somados ao saldo existente.", "success")
    return redirect(url_for("subscriptions.detail", sub_id=sub.id))


# ── Cancelar ──────────────────────────────────────────────────────────────────
@subscriptions_bp.route("/<int:sub_id>/cancel", methods=["POST"])
@login_required
@admin_required
def cancel(sub_id: int):
    sub = CustomerSubscription.query.get_or_404(sub_id)
    sub.status = "cancelled"
    db.session.commit()
    flash("Assinatura cancelada.", "info")
    return redirect(url_for("subscriptions.index"))


# ── AJAX: verificar crédito ───────────────────────────────────────────────────
@subscriptions_bp.route("/api/credit-check")
@login_required
def credit_check():
    customer_id = request.args.get("customer_id", type=int)
    service_id  = request.args.get("service_id",  type=int)
    kit_id      = request.args.get("kit_id",      type=int)
    if not customer_id:
        return jsonify({"has_credit": False})
    if kit_id:
        return jsonify(check_credit_kit(customer_id, kit_id))
    if service_id:
        return jsonify(check_credit(customer_id, service_id))
    return jsonify({"has_credit": False})
