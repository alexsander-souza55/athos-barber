from flask import Blueprint, render_template
from flask_login import login_required, current_user
from datetime import date, timedelta
from sqlalchemy import func
from app.extensions import db
from app.models.appointment import Appointment
from app.models.customer import Customer
from app.models.barber import Barber
from app.models.service import Service

dashboard_bp = Blueprint("dashboard", __name__)

_MONTHS_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]
_WEEKDAYS_PT = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]


def _fmt_brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@dashboard_bp.route("/")
@login_required
def index():
    today = date.today()
    month_start = today.replace(day=1)

    # Scope: admin sees everything; barber sees only own data
    barber_id = None
    if current_user.is_barber and current_user.barber_profile:
        barber_id = current_user.barber_profile.id

    stats = _build_stats(today, month_start, barber_id)
    weekly = _weekly_revenue(barber_id)
    upcoming = _upcoming_appointments(today, barber_id)
    top_barbers = _top_barbers(month_start) if current_user.is_admin else []
    top_services = _top_services(month_start, barber_id)

    today_label = (
        f"{_WEEKDAYS_PT[today.weekday()].capitalize()}, "
        f"{today.day} de {_MONTHS_PT[today.month - 1]} de {today.year}"
    )
    month_label = f"{_MONTHS_PT[today.month - 1].capitalize()} {today.year}"

    return render_template(
        "dashboard/index.html",
        stats=stats,
        weekly=weekly,
        upcoming=upcoming,
        top_barbers=top_barbers,
        top_services=top_services,
        today=today,
        today_label=today_label,
        month_label=month_label,
    )


# ── Helpers ────────────────────────────────────────────────────────────────

def _build_stats(today, month_start, barber_id=None) -> dict:
    """
    All KPI numbers for the cards.
    barber_id=None → global (admin view).
    barber_id set  → filtered to that barber only.
    """

    def _count(*filters):
        q = Appointment.query
        if barber_id:
            q = q.filter(Appointment.barber_id == barber_id)
        for f in filters:
            q = q.filter(f)
        return q.count()

    def _revenue(*filters):
        """Sum of Service.price for completed appointments."""
        q = (
            db.session.query(func.sum(Service.price))
            .join(Appointment, Appointment.service_id == Service.id)
            .filter(Appointment.status == "completed")
        )
        if barber_id:
            q = q.filter(Appointment.barber_id == barber_id)
        for f in filters:
            q = q.filter(f)
        return float(q.scalar() or 0)

    today_total     = _count(Appointment.scheduled_date == today)
    today_pending   = _count(
        Appointment.scheduled_date == today,
        Appointment.status.in_(["pending", "confirmed"]),
    )
    today_completed = _count(
        Appointment.scheduled_date == today,
        Appointment.status == "completed",
    )
    today_revenue   = _revenue(Appointment.scheduled_date == today)
    month_revenue   = _revenue(Appointment.scheduled_date >= month_start)

    # Completion rate = completed / (completed + cancelled + no_show) this month
    # Excludes still-pending/confirmed appointments to avoid penalising future slots
    month_closed = _count(
        Appointment.scheduled_date >= month_start,
        Appointment.status.in_(["completed", "cancelled", "no_show"]),
    )
    month_completed = _count(
        Appointment.scheduled_date >= month_start,
        Appointment.status == "completed",
    )
    completion_rate = round(
        (month_completed / month_closed * 100) if month_closed else 0, 1
    )

    avg_ticket = (today_revenue / today_completed) if today_completed else 0

    total_customers = Customer.query.count() if not barber_id else None
    active_barbers  = Barber.query.filter_by(is_active=True).count() if not barber_id else None

    return {
        "today_total":       today_total,
        "today_pending":     today_pending,
        "today_completed":   today_completed,
        "today_revenue":     today_revenue,
        "today_revenue_fmt": _fmt_brl(today_revenue),
        "month_revenue":     month_revenue,
        "month_revenue_fmt": _fmt_brl(month_revenue),
        "completion_rate":   completion_rate,
        "avg_ticket":        avg_ticket,
        "avg_ticket_fmt":    _fmt_brl(avg_ticket),
        "total_customers":   total_customers,
        "active_barbers":    active_barbers,
    }


def _weekly_revenue(barber_id=None) -> dict:
    """Daily completed revenue for the last 7 days (including today)."""
    today = date.today()
    labels, values = [], []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        labels.append(day.strftime("%d/%m"))
        q = (
            db.session.query(func.sum(Service.price))
            .join(Appointment, Appointment.service_id == Service.id)
            .filter(
                Appointment.scheduled_date == day,
                Appointment.status == "completed",
            )
        )
        if barber_id:
            q = q.filter(Appointment.barber_id == barber_id)
        values.append(float(q.scalar() or 0))
    return {"labels": labels, "amounts": values}


def _upcoming_appointments(today, barber_id=None):
    """Next 8 pending/confirmed appointments from today onwards."""
    q = Appointment.query.filter(
        Appointment.scheduled_date >= today,
        Appointment.status.in_(["pending", "confirmed"]),
    )
    if barber_id:
        q = q.filter(Appointment.barber_id == barber_id)
    return (
        q.order_by(Appointment.scheduled_date, Appointment.scheduled_time)
        .limit(8)
        .all()
    )


def _top_barbers(month_start) -> list:
    """Top 5 barbers by completed appointment count this month (admin only)."""
    rows = (
        db.session.query(
            Barber,
            func.count(Appointment.id).label("cnt"),
            func.coalesce(func.sum(Service.price), 0).label("revenue"),
        )
        .join(Appointment, Appointment.barber_id == Barber.id)
        .join(Service, Service.id == Appointment.service_id)
        .filter(
            Appointment.status == "completed",
            Appointment.scheduled_date >= month_start,
        )
        .group_by(Barber.id)
        .order_by(func.count(Appointment.id).desc())
        .limit(5)
        .all()
    )
    return [
        {
            "barber":      r.Barber,
            "cnt":         r.cnt,
            "revenue":     float(r.revenue),
            "revenue_fmt": _fmt_brl(float(r.revenue)),
        }
        for r in rows
    ]


def _top_services(month_start, barber_id=None) -> list:
    """Top 6 services by completed appointment count this month."""
    q = (
        db.session.query(
            Service,
            func.count(Appointment.id).label("cnt"),
            func.coalesce(func.sum(Service.price), 0).label("revenue"),
        )
        .join(Appointment, Appointment.service_id == Service.id)
        .filter(
            Appointment.status == "completed",
            Appointment.scheduled_date >= month_start,
        )
    )
    if barber_id:
        q = q.filter(Appointment.barber_id == barber_id)
    rows = (
        q.group_by(Service.id)
        .order_by(func.count(Appointment.id).desc())
        .limit(6)
        .all()
    )
    return [
        {
            "service":     r.Service,
            "cnt":         r.cnt,
            "revenue":     float(r.revenue),
            "revenue_fmt": _fmt_brl(float(r.revenue)),
        }
        for r in rows
    ]
