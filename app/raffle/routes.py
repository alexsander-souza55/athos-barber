import random
from datetime import date, datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import func, distinct

from app.extensions import db
from app.models.raffle import Raffle, RaffleWinner
from app.models.customer import Customer
from app.models.appointment import Appointment
from app.utils.decorators import admin_required

raffle_bp = Blueprint("raffle", __name__)


@raffle_bp.route("/")
@login_required
@admin_required
def index():
    raffles = Raffle.query.order_by(Raffle.created_at.desc()).all()
    return render_template("raffle/index.html", raffles=raffles)


@raffle_bp.route("/new", methods=["GET", "POST"])
@login_required
@admin_required
def new():
    errors = {}
    form_data = {}

    if request.method == "POST":
        form_data = {
            "name":         request.form.get("name", "").strip(),
            "prize":        request.form.get("prize", "").strip(),
            "description":  request.form.get("description", "").strip(),
            "start_date":   request.form.get("start_date", "").strip(),
            "end_date":     request.form.get("end_date", "").strip(),
            "winner_count": request.form.get("winner_count", "1").strip(),
        }

        if not form_data["name"]:
            errors["name"] = "Nome é obrigatório."

        start = end = None
        try:
            start = date.fromisoformat(form_data["start_date"])
        except ValueError:
            errors["start_date"] = "Data inicial inválida."

        try:
            end = date.fromisoformat(form_data["end_date"])
        except ValueError:
            errors["end_date"] = "Data final inválida."

        if start and end and start > end:
            errors["end_date"] = "A data final deve ser igual ou posterior à inicial."

        winner_count = 1
        try:
            winner_count = int(form_data["winner_count"])
            if not (1 <= winner_count <= 50):
                raise ValueError
        except (ValueError, TypeError):
            errors["winner_count"] = "Informe um número entre 1 e 50."

        if not errors:
            raffle = Raffle(
                name=form_data["name"],
                prize=form_data["prize"] or None,
                description=form_data["description"] or None,
                start_date=start,
                end_date=end,
                winner_count=winner_count,
            )
            db.session.add(raffle)
            db.session.commit()
            flash(f"Sorteio «{raffle.name}» criado com sucesso!", "success")
            return redirect(url_for("raffle.detail", raffle_id=raffle.id))

    return render_template("raffle/form.html", errors=errors, form_data=form_data)


@raffle_bp.route("/<int:raffle_id>")
@login_required
@admin_required
def detail(raffle_id: int):
    raffle = Raffle.query.get_or_404(raffle_id)
    winners = raffle.winners.order_by(RaffleWinner.position).all()

    pool_count = 0
    pool_sample = []

    if raffle.status == "pending":
        # Conta clientes únicos com ao menos um atendimento concluído no período
        pool_count = (
            db.session.query(func.count(distinct(Appointment.customer_id)))
            .filter(
                Appointment.status == "completed",
                Appointment.scheduled_date >= raffle.start_date,
                Appointment.scheduled_date <= raffle.end_date,
            )
            .scalar()
        ) or 0

        if pool_count > 0:
            cids = [
                r[0]
                for r in db.session.query(Appointment.customer_id)
                .filter(
                    Appointment.status == "completed",
                    Appointment.scheduled_date >= raffle.start_date,
                    Appointment.scheduled_date <= raffle.end_date,
                )
                .distinct()
                .limit(10)
                .all()
            ]
            pool_sample = (
                Customer.query.filter(Customer.id.in_(cids))
                .order_by(Customer.name)
                .all()
            )

    return render_template(
        "raffle/detail.html",
        raffle=raffle,
        winners=winners,
        pool_count=pool_count,
        pool_sample=pool_sample,
    )


@raffle_bp.route("/<int:raffle_id>/draw", methods=["POST"])
@login_required
@admin_required
def draw(raffle_id: int):
    raffle = Raffle.query.get_or_404(raffle_id)

    if raffle.status == "drawn":
        flash("Este sorteio já foi realizado.", "warning")
        return redirect(url_for("raffle.detail", raffle_id=raffle_id))

    # ── 1. Montar o pool: clientes únicos com atendimento concluído no período ──
    customer_ids = [
        r[0]
        for r in db.session.query(Appointment.customer_id)
        .filter(
            Appointment.status == "completed",
            Appointment.scheduled_date >= raffle.start_date,
            Appointment.scheduled_date <= raffle.end_date,
        )
        .distinct()
        .all()
    ]

    if not customer_ids:
        flash(
            "Nenhum cliente foi atendido (concluído) no período selecionado. "
            "Verifique as datas e tente novamente.",
            "danger",
        )
        return redirect(url_for("raffle.detail", raffle_id=raffle_id))

    pool = Customer.query.filter(Customer.id.in_(customer_ids)).all()

    # ── 2. Sortear sem repetição ──────────────────────────────────────────────
    # Se o pool for menor que os vencedores solicitados, sorteia todos do pool
    n_winners = min(raffle.winner_count, len(pool))
    chosen = random.sample(pool, n_winners)

    # ── 3. Persistir vencedores com snapshot imutável ─────────────────────────
    now = datetime.now(timezone.utc)
    for position, customer in enumerate(chosen, start=1):
        db.session.add(
            RaffleWinner(
                raffle_id=raffle.id,
                customer_id=customer.id,
                position=position,
                customer_name=customer.name,
                customer_phone=customer.phone or "",
                drawn_at=now,
            )
        )

    raffle.status = "drawn"
    raffle.pool_size = len(pool)
    raffle.drawn_at = now
    db.session.commit()

    flash(
        f"Sorteio realizado! {n_winners} vencedor(es) de {len(pool)} clientes elegíveis.",
        "success",
    )
    return redirect(url_for("raffle.detail", raffle_id=raffle_id))


@raffle_bp.route("/<int:raffle_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete(raffle_id: int):
    raffle = Raffle.query.get_or_404(raffle_id)
    name = raffle.name
    db.session.delete(raffle)
    db.session.commit()
    flash(f"Sorteio «{name}» excluído.", "info")
    return redirect(url_for("raffle.index"))
