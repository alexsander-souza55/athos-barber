from app.extensions import db


class SubscriptionPlan(db.Model):
    __tablename__ = "subscription_plan"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

    credits = db.relationship(
        "SubscriptionPlanCredit",
        back_populates="plan",
        cascade="all, delete-orphan",
        lazy="select",
    )
    subscriptions = db.relationship(
        "CustomerSubscription",
        back_populates="plan",
        lazy="dynamic",
    )

    @property
    def price_formatted(self) -> str:
        try:
            return (
                f"R$ {float(self.price):,.2f}"
                .replace(",", "X").replace(".", ",").replace("X", ".")
            )
        except (TypeError, ValueError):
            return "R$ 0,00"

    def __repr__(self):
        return f"<SubscriptionPlan {self.name}>"


class SubscriptionPlanCredit(db.Model):
    __tablename__ = "subscription_plan_credit"

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("subscription_plan.id"), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    plan = db.relationship("SubscriptionPlan", back_populates="credits")
    service = db.relationship("Service", foreign_keys=[service_id])
