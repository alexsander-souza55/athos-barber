from datetime import date, datetime
from app.extensions import db


class CustomerSubscription(db.Model):
    __tablename__ = "customer_subscription"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey("subscription_plan.id"), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default="active", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    renewed_at = db.Column(db.DateTime, nullable=True)

    plan = db.relationship("SubscriptionPlan", back_populates="subscriptions")
    customer = db.relationship("Customer", back_populates="subscriptions")
    credit_balances = db.relationship(
        "SubscriptionCreditBalance",
        back_populates="subscription",
        cascade="all, delete-orphan",
        lazy="select",
    )
    credit_usages = db.relationship(
        "SubscriptionCreditUsage",
        back_populates="subscription",
        lazy="dynamic",
    )

    @property
    def is_deadline_passed(self) -> bool:
        return self.end_date < date.today()

    @property
    def has_remaining_credits(self) -> bool:
        return any(bal.remaining_credits > 0 for bal in self.credit_balances)

    @property
    def is_expired(self) -> bool:
        """Vencida pelo prazo — independente de créditos. Usado para exibição."""
        return self.end_date < date.today()

    @property
    def days_remaining(self) -> int:
        return max(0, (self.end_date - date.today()).days)

    @property
    def is_expiring_soon(self) -> bool:
        return not self.is_expired and self.days_remaining <= 3

    @property
    def effective_status(self) -> str:
        if self.status == "cancelled":
            return "cancelled"
        if self.is_deadline_passed:
            if self.has_remaining_credits:
                return "expired_with_credits"
            return "expired"
        return "active"

    @property
    def status_label(self) -> str:
        return {
            "active": "Ativa",
            "expired": "Vencida",
            "expired_with_credits": "Vencida c/ créditos",
            "cancelled": "Cancelada",
        }.get(self.effective_status, self.effective_status)

    @property
    def status_badge(self) -> str:
        return {
            "active": "badge-confirmed",
            "expired": "badge-no_show",
            "expired_with_credits": "badge-pending",
            "cancelled": "badge-cancelled",
        }.get(self.effective_status, "badge-pending")

    def credits_summary(self) -> list:
        return [
            {
                "service_name": bal.service.name if bal.service else "—",
                "service_id": bal.service_id,
                "remaining": bal.remaining_credits,
                "used": bal.used_credits,
                "total": bal.total_credits,
            }
            for bal in self.credit_balances
        ]


class SubscriptionCreditBalance(db.Model):
    __tablename__ = "subscription_credit_balance"

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("customer_subscription.id"), nullable=False
    )
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)
    total_credits = db.Column(db.Integer, nullable=False, default=0)
    used_credits = db.Column(db.Integer, nullable=False, default=0)

    subscription = db.relationship("CustomerSubscription", back_populates="credit_balances")
    service = db.relationship("Service", foreign_keys=[service_id])

    @property
    def remaining_credits(self) -> int:
        return max(0, self.total_credits - self.used_credits)


class SubscriptionCreditUsage(db.Model):
    __tablename__ = "subscription_credit_usage"

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("customer_subscription.id"), nullable=False
    )
    appointment_id = db.Column(
        db.Integer, db.ForeignKey("appointments.id"), nullable=True
    )
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)
    used_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.String(255), nullable=True)

    subscription = db.relationship("CustomerSubscription", back_populates="credit_usages")
    service = db.relationship("Service", foreign_keys=[service_id])
    appointment = db.relationship("Appointment", foreign_keys=[appointment_id])
