from app.extensions import db
from datetime import datetime, timezone


class Raffle(db.Model):
    __tablename__ = "raffles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    prize = db.Column(db.String(200), nullable=True)

    # Período de busca de clientes elegíveis
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

    # Quantidade de vencedores desejada
    winner_count = db.Column(db.Integer, nullable=False, default=1)

    # Preenchido no momento do sorteio
    pool_size = db.Column(db.Integer, nullable=True)
    drawn_at = db.Column(db.DateTime, nullable=True)

    status = db.Column(db.String(20), nullable=False, default="pending")  # pending | drawn
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    winners = db.relationship(
        "RaffleWinner",
        backref="raffle",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    # ── Helpers ──────────────────────────────────────────────────────────

    @property
    def period_str(self) -> str:
        return f"{self.start_date.strftime('%d/%m/%Y')} – {self.end_date.strftime('%d/%m/%Y')}"

    @property
    def status_label(self) -> str:
        return {"pending": "Pendente", "drawn": "Sorteado"}.get(self.status, self.status)

    @property
    def status_color(self) -> str:
        return {"pending": "warning", "drawn": "success"}.get(self.status, "secondary")

    @property
    def drawn_winners_count(self) -> int:
        return self.winners.count()

    def winners_ordered(self):
        """Retorna vencedores ordenados por posição."""
        return self.winners.order_by(RaffleWinner.position).all()

    def __repr__(self) -> str:
        return f"<Raffle {self.name!r} [{self.status}]>"


class RaffleWinner(db.Model):
    __tablename__ = "raffle_winners"

    id = db.Column(db.Integer, primary_key=True)
    raffle_id = db.Column(db.Integer, db.ForeignKey("raffles.id"), nullable=False)

    # FK opcional — preserva o registro mesmo se o cliente for excluído
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)

    position = db.Column(db.Integer, nullable=False, default=1)

    # Snapshot imutável no momento do sorteio
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(30), nullable=True)

    drawn_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    customer = db.relationship("Customer", foreign_keys=[customer_id], back_populates="raffle_winners")

    # ── Helpers ──────────────────────────────────────────────────────────

    @property
    def initials(self) -> str:
        parts = self.customer_name.strip().split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return self.customer_name[:2].upper() if self.customer_name else "?"

    @property
    def position_label(self) -> str:
        ordinals = {1: "1º lugar", 2: "2º lugar", 3: "3º lugar"}
        return ordinals.get(self.position, f"{self.position}º lugar")

    @property
    def medal_class(self) -> str:
        return {1: "gold", 2: "silver", 3: "bronze"}.get(self.position, "default")

    def __repr__(self) -> str:
        return f"<RaffleWinner {self.customer_name!r} pos={self.position}>"
