from app.extensions import db
from datetime import datetime, timezone

APPOINTMENT_STATUSES = {
    "pending": "Pendente",
    "confirmed": "Confirmado",
    "completed": "Concluído",
    "cancelled": "Cancelado",
    "no_show": "Não compareceu",
}

STATUS_COLORS = {
    "pending": "warning",
    "confirmed": "info",
    "completed": "success",
    "cancelled": "danger",
    "no_show": "secondary",
}


class Appointment(db.Model):
    __tablename__ = "appointments"
    __table_args__ = (
        db.Index("ix_appt_barber_date", "barber_id", "scheduled_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    barber_id = db.Column(db.Integer, db.ForeignKey("barbers.id"), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)
    kit_id = db.Column(db.Integer, db.ForeignKey("service_kit.id"), nullable=True)
    scheduled_date = db.Column(db.Date, nullable=False)
    scheduled_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    kit = db.relationship("ServiceKit", foreign_keys=[kit_id])

    @property
    def status_label(self) -> str:
        return APPOINTMENT_STATUSES.get(self.status, self.status)

    @property
    def status_color(self) -> str:
        return STATUS_COLORS.get(self.status, "secondary")

    @property
    def scheduled_datetime_str(self) -> str:
        return f"{self.scheduled_date.strftime('%d/%m/%Y')} às {self.scheduled_time.strftime('%H:%M')}"

    @property
    def effective_duration_minutes(self) -> int:
        """Duração real: kit total se for kit, senão duração do serviço."""
        if self.kit_id and self.kit:
            return self.kit.total_duration_minutes
        if self.service:
            return self.service.duration_minutes
        return 60

    @property
    def end_time(self):
        if self.scheduled_time and self.scheduled_date:
            from datetime import datetime, timedelta
            dt = datetime.combine(self.scheduled_date, self.scheduled_time)
            return (dt + timedelta(minutes=self.effective_duration_minutes)).time()
        return None

    @property
    def end_time_str(self) -> str:
        t = self.end_time
        return t.strftime("%H:%M") if t else ""

    def __repr__(self) -> str:
        return f"<Appointment #{self.id} [{self.status}]>"
