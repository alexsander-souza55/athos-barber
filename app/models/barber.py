import re as _re
from app.extensions import db
from datetime import datetime, timezone, date


class Barber(db.Model):
    __tablename__ = "barbers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)

    # Perfil
    name = db.Column(db.String(100), nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=True)
    whatsapp = db.Column(db.String(20), nullable=True)
    specialty = db.Column(db.String(100), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    photo = db.Column(db.String(200), nullable=True)

    # Horário de atendimento
    work_start_time = db.Column(db.Time, nullable=True)
    work_end_time = db.Column(db.Time, nullable=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    appointments = db.relationship("Appointment", backref="barber", lazy="dynamic")
    schedule_exceptions = db.relationship(
        "BarberScheduleException",
        back_populates="barber",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by="BarberScheduleException.date",
    )

    # ── Foto ────────────────────────────────────────────────
    @property
    def photo_url(self) -> str:
        if self.photo:
            return f"/static/uploads/{self.photo}"
        return None  # templates usam avatar de iniciais quando None

    @property
    def whatsapp_link(self) -> str | None:
        if not self.whatsapp:
            return None
        digits = _re.sub(r'\D', '', self.whatsapp)
        if not digits:
            return None
        if not digits.startswith('55'):
            digits = '55' + digits
        return f'https://wa.me/{digits}'

    # ── Horários ─────────────────────────────────────────────
    @property
    def work_hours_str(self) -> str:
        if self.work_start_time and self.work_end_time:
            return (
                f"{self.work_start_time.strftime('%H:%M')} "
                f"– {self.work_end_time.strftime('%H:%M')}"
            )
        return "—"

    @property
    def work_start_str(self) -> str:
        return self.work_start_time.strftime("%H:%M") if self.work_start_time else ""

    @property
    def work_end_str(self) -> str:
        return self.work_end_time.strftime("%H:%M") if self.work_end_time else ""

    # ── Stats de agendamentos ────────────────────────────────
    @property
    def total_appointments(self) -> int:
        return self.appointments.count()

    @property
    def completed_appointments(self) -> int:
        return self.appointments.filter_by(status="completed").count()

    @property
    def pending_appointments(self) -> int:
        return self.appointments.filter_by(status="pending").count()

    def appointments_today(self) -> int:
        return self.appointments.filter_by(scheduled_date=date.today()).count()

    def appointments_this_month(self) -> int:
        from app.models.appointment import Appointment
        today = date.today()
        return self.appointments.filter(
            Appointment.scheduled_date >= today.replace(day=1)
        ).count()

    # ── Iniciais (fallback de foto) ──────────────────────────
    @property
    def initials(self) -> str:
        parts = self.name.strip().split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return self.name[:2].upper()

    def __repr__(self) -> str:
        return f"<Barber {self.name}>"
