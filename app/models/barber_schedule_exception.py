from datetime import datetime
from app.extensions import db


class BarberScheduleException(db.Model):
    __tablename__ = "barber_schedule_exception"

    id = db.Column(db.Integer, primary_key=True)
    barber_id = db.Column(db.Integer, db.ForeignKey("barbers.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    exception_type = db.Column(db.String(20), nullable=False)  # day_off | custom_hours
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    barber = db.relationship("Barber", back_populates="schedule_exceptions")

    __table_args__ = (
        db.UniqueConstraint("barber_id", "date", name="uq_barber_exception_date"),
    )

    @property
    def type_label(self) -> str:
        return "Folga" if self.exception_type == "day_off" else "Horário especial"

    @property
    def type_badge(self) -> str:
        return "badge-cancelled" if self.exception_type == "day_off" else "badge-pending"

    @property
    def hours_str(self) -> str:
        if self.exception_type == "custom_hours" and self.start_time and self.end_time:
            return f"{self.start_time.strftime('%H:%M')} – {self.end_time.strftime('%H:%M')}"
        return "—"
