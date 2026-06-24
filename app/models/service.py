from app.extensions import db
from datetime import datetime, timezone


class Service(db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=30)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    # null = qualquer barbeiro pode realizar; preenchido = exclusivo daquele barbeiro
    assigned_barber_id = db.Column(
        db.Integer, db.ForeignKey("barbers.id", ondelete="SET NULL"), nullable=True
    )
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    appointments = db.relationship("Appointment", backref="service", lazy="dynamic")
    assigned_barber = db.relationship(
        "Barber", foreign_keys=[assigned_barber_id], backref="exclusive_services"
    )

    @property
    def price_formatted(self) -> str:
        return f"R$ {self.price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    @property
    def duration_formatted(self) -> str:
        if self.duration_minutes < 60:
            return f"{self.duration_minutes} min"
        hours = self.duration_minutes // 60
        mins = self.duration_minutes % 60
        return f"{hours}h{mins:02d}" if mins else f"{hours}h"

    def __repr__(self) -> str:
        return f"<Service {self.name} R${self.price}>"
