from datetime import datetime
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, PasswordField, TextAreaField,
    BooleanField, SubmitField, SelectField, DateField,
)
from wtforms.validators import (
    DataRequired, Email, Length, EqualTo, Optional, ValidationError,
)


def _parse_time(value: str):
    """Converte string 'HH:MM' para objeto time. Lança ValueError se inválido."""
    return datetime.strptime(value.strip(), "%H:%M").time()


# ── Formulário de criação (admin cria usuário + perfil barbeiro) ──────────────
class CreateBarberForm(FlaskForm):

    # — Credenciais de acesso ————————————————————————————
    username = StringField(
        "Usuário (login)",
        validators=[DataRequired(), Length(3, 64, message="Entre 3 e 64 caracteres.")],
    )
    email = StringField(
        "E-mail",
        validators=[DataRequired(), Email(message="E-mail inválido.")],
    )
    password = PasswordField(
        "Senha",
        validators=[DataRequired(), Length(6, 128, message="Mínimo 6 caracteres.")],
    )
    confirm_password = PasswordField(
        "Confirmar senha",
        validators=[DataRequired(), EqualTo("password", message="As senhas não coincidem.")],
    )

    # — Perfil do barbeiro ————————————————————————————————
    name = StringField(
        "Nome completo",
        validators=[DataRequired(message="Nome é obrigatório."), Length(2, 100)],
    )
    phone = StringField("Telefone", validators=[Optional(), Length(max=20)])
    whatsapp = StringField("WhatsApp", validators=[Optional(), Length(max=20)])
    specialty = StringField("Especialidade", validators=[Optional(), Length(max=100)])
    bio = TextAreaField("Bio / Apresentação", validators=[Optional(), Length(max=500)])

    # — Horários ——————————————————————————————————————————
    work_start_time = StringField("Início do atendimento", validators=[Optional()])
    work_end_time = StringField("Fim do atendimento", validators=[Optional()])

    # — Foto ——————————————————————————————————————————————
    photo = FileField(
        "Foto do barbeiro",
        validators=[FileAllowed(["jpg", "jpeg", "png", "webp", "gif"], "Apenas imagens.")],
    )

    submit = SubmitField("Cadastrar barbeiro")

    # — Validadores de unicidade ——————————————————————————
    def validate_username(self, field):
        from app.models.user import User
        if User.query.filter_by(username=field.data.strip()).first():
            raise ValidationError("Este nome de usuário já está em uso.")

    def validate_email(self, field):
        from app.models.user import User
        if User.query.filter_by(email=field.data.strip()).first():
            raise ValidationError("Este e-mail já está cadastrado.")

    def validate_name(self, field):
        from app.models.barber import Barber
        from app.extensions import db
        if Barber.query.filter(
            db.func.lower(Barber.name) == field.data.strip().lower()
        ).first():
            raise ValidationError("Já existe um barbeiro com este nome.")

    # — Validadores de horário ————————————————————————————
    def validate_work_start_time(self, field):
        if not field.data:
            return
        try:
            _parse_time(field.data)
        except ValueError:
            raise ValidationError("Use o formato HH:MM  (ex: 08:00).")

    def validate_work_end_time(self, field):
        if not field.data:
            return
        try:
            end = _parse_time(field.data)
        except ValueError:
            raise ValidationError("Use o formato HH:MM  (ex: 18:00).")
        if self.work_start_time.data:
            try:
                start = _parse_time(self.work_start_time.data)
                if end <= start:
                    raise ValidationError("Horário de fim deve ser posterior ao de início.")
            except ValueError:
                pass


# ── Formulário de edição (somente perfil, sem credenciais) ────────────────────
class EditBarberForm(FlaskForm):

    name = StringField(
        "Nome completo",
        validators=[DataRequired(message="Nome é obrigatório."), Length(2, 100)],
    )
    phone = StringField("Telefone", validators=[Optional(), Length(max=20)])
    whatsapp = StringField("WhatsApp", validators=[Optional(), Length(max=20)])
    specialty = StringField("Especialidade", validators=[Optional(), Length(max=100)])
    bio = TextAreaField("Bio / Apresentação", validators=[Optional(), Length(max=500)])

    work_start_time = StringField("Início do atendimento", validators=[Optional()])
    work_end_time = StringField("Fim do atendimento", validators=[Optional()])

    photo = FileField(
        "Nova foto",
        validators=[FileAllowed(["jpg", "jpeg", "png", "webp", "gif"], "Apenas imagens.")],
    )
    remove_photo = BooleanField("Remover foto atual")

    is_active = BooleanField("Barbeiro ativo")

    submit = SubmitField("Salvar alterações")

    def __init__(self, barber_id: int = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._barber_id = barber_id

    def validate_name(self, field):
        from app.models.barber import Barber
        from app.extensions import db
        existing = Barber.query.filter(
            db.func.lower(Barber.name) == field.data.strip().lower(),
            Barber.id != self._barber_id,
        ).first()
        if existing:
            raise ValidationError("Já existe um barbeiro com este nome.")

    def validate_work_start_time(self, field):
        if not field.data:
            return
        try:
            _parse_time(field.data)
        except ValueError:
            raise ValidationError("Use o formato HH:MM  (ex: 08:00).")

    def validate_work_end_time(self, field):
        if not field.data:
            return
        try:
            end = _parse_time(field.data)
        except ValueError:
            raise ValidationError("Use o formato HH:MM  (ex: 18:00).")
        if self.work_start_time.data:
            try:
                start = _parse_time(self.work_start_time.data)
                if end <= start:
                    raise ValidationError("Horário de fim deve ser posterior ao de início.")
            except ValueError:
                pass


# ── Exceção de agenda ─────────────────────────────────────────────────────────
class ScheduleExceptionForm(FlaskForm):

    date = DateField("Data", validators=[DataRequired(message="Selecione uma data.")])
    exception_type = SelectField(
        "Tipo",
        choices=[("day_off", "Folga"), ("custom_hours", "Horário especial")],
        validators=[DataRequired()],
    )
    start_time = StringField("Início", validators=[Optional()])
    end_time = StringField("Fim", validators=[Optional()])
    reason = StringField("Motivo (opcional)", validators=[Optional(), Length(max=255)])

    submit = SubmitField("Salvar exceção")

    def validate_date(self, field):
        from datetime import date
        if field.data and field.data < date.today():
            raise ValidationError("A data não pode ser no passado.")

    def validate_start_time(self, field):
        if self.exception_type.data != "custom_hours":
            return
        if not field.data:
            raise ValidationError("Informe o horário de início.")
        try:
            _parse_time(field.data)
        except ValueError:
            raise ValidationError("Use o formato HH:MM.")

    def validate_end_time(self, field):
        if self.exception_type.data != "custom_hours":
            return
        if not field.data:
            raise ValidationError("Informe o horário de fim.")
        try:
            end = _parse_time(field.data)
        except ValueError:
            raise ValidationError("Use o formato HH:MM.")
        if self.start_time.data:
            try:
                start = _parse_time(self.start_time.data)
                if end <= start:
                    raise ValidationError("Horário de fim deve ser posterior ao de início.")
            except ValueError:
                pass
