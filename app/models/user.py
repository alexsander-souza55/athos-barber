from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from datetime import datetime, timezone, timedelta

_LOCK_THRESHOLD = 5       # tentativas antes de bloquear
_LOCK_MINUTES   = 15      # minutos de bloqueio


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="barber")  # admin | barber
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime, nullable=True)
    login_count = db.Column(db.Integer, default=0, nullable=False)

    # Proteção brute-force
    failed_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)

    barber_profile = db.relationship(
        "Barber",
        backref="user",
        cascade="all, delete-orphan",
        uselist=False,
        lazy=True,
    )

    # ── Senha ──────────────────────────────────────────
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    # ── Roles ───────────────────────────────────────────
    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_barber(self) -> bool:
        return self.role == "barber"

    # ── Bloqueio por tentativas ──────────────────────────
    @property
    def is_locked(self) -> bool:
        if self.locked_until:
            return datetime.now(timezone.utc) < self.locked_until.replace(tzinfo=timezone.utc)
        return False

    @property
    def lock_remaining_minutes(self) -> int:
        if self.is_locked:
            delta = self.locked_until.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
            return max(1, int(delta.total_seconds() // 60) + 1)
        return 0

    def handle_failed_login(self) -> None:
        self.failed_attempts += 1
        if self.failed_attempts >= _LOCK_THRESHOLD:
            self.locked_until = datetime.now(timezone.utc) + timedelta(minutes=_LOCK_MINUTES)

    def reset_login_attempts(self) -> None:
        self.failed_attempts = 0
        self.locked_until = None

    def record_login(self) -> None:
        self.reset_login_attempts()
        self.last_login = datetime.now(timezone.utc)
        self.login_count = (self.login_count or 0) + 1

    # ── Display ─────────────────────────────────────────
    @property
    def display_name(self) -> str:
        if self.is_barber and self.barber_profile:
            return self.barber_profile.name
        return self.username

    @property
    def role_label(self) -> str:
        return "Administrador" if self.is_admin else "Barbeiro"

    @property
    def role_badge_color(self) -> str:
        return "gold" if self.is_admin else "info"

    def __repr__(self) -> str:
        return f"<User {self.username} [{self.role}]>"
