import re
from datetime import datetime, date
from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, SelectField, HiddenField, DateField, IntegerField
)
from wtforms.validators import DataRequired, Length, Optional, ValidationError


def _validate_cpf_digits(cpf: str) -> bool:
    d = re.sub(r'\D', '', cpf or '')
    if len(d) != 11 or len(set(d)) == 1:
        return False

    def _check(n):
        total = sum(int(d[i]) * (n - i) for i in range(n - 1))
        r = (total * 10) % 11
        return r if r < 10 else 0

    return _check(10) == int(d[9]) and _check(11) == int(d[10])


# ── Formulário interno (admin cria agendamento) ───────────────────────────────
class AppointmentAdminForm(FlaskForm):
    customer_id = SelectField("Cliente", coerce=int, validators=[DataRequired()])
    barber_id   = SelectField("Barbeiro", coerce=int, validators=[DataRequired()])
    service_id  = SelectField("Serviço",  coerce=int, validators=[DataRequired()])
    scheduled_date = DateField("Data", validators=[DataRequired()])
    scheduled_time = StringField("Horário (HH:MM)", validators=[DataRequired()])
    notes = TextAreaField("Observações", validators=[Optional(), Length(max=500)])

    def validate_scheduled_time(self, field):
        if not field.data:
            return
        try:
            datetime.strptime(field.data.strip(), "%H:%M")
        except ValueError:
            raise ValidationError("Use o formato HH:MM (ex: 09:30).")


# ── Formulário público (cliente agenda online) ────────────────────────────────
class BookingForm(FlaskForm):
    # Preenchidos pelo wizard JS — valores vindos dos hidden inputs
    service_id     = HiddenField()
    barber_id      = HiddenField()
    scheduled_date = HiddenField()
    scheduled_time = HiddenField()

    # Preenchidos manualmente pelo cliente
    customer_name  = StringField(
        "Seu nome",
        validators=[DataRequired(message="Nome é obrigatório."), Length(2, 100)],
    )
    customer_phone = StringField(
        "Seu telefone",
        validators=[DataRequired(message="Telefone é obrigatório."), Length(max=20)],
    )
    customer_cpf = StringField(
        "Seu CPF",
        validators=[DataRequired(message="CPF é obrigatório."), Length(max=14)],
    )
    notes = TextAreaField("Observações", validators=[Optional(), Length(max=500)])

    def validate_customer_cpf(self, field):
        if not field.data or not field.data.strip():
            return
        if not _validate_cpf_digits(field.data):
            raise ValidationError("CPF inválido. Verifique os dígitos.")

    def validate_scheduled_date(self, field):
        if not field.data:
            return
        try:
            d = date.fromisoformat(field.data)
        except ValueError:
            raise ValidationError("Data inválida.")
        if d < date.today():
            raise ValidationError("Data no passado não é permitida.")

    def validate_scheduled_time(self, field):
        if not field.data:
            return
        try:
            datetime.strptime(field.data, "%H:%M")
        except ValueError:
            raise ValidationError("Horário inválido.")
