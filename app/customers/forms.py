import re
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, DateField
from wtforms.validators import DataRequired, Length, Optional, Email, ValidationError


def _digits(phone: str) -> str:
    return re.sub(r'\D', '', phone or '')


def _validate_cpf_digits(cpf: str) -> bool:
    d = re.sub(r'\D', '', cpf or '')
    if len(d) != 11 or len(set(d)) == 1:
        return False

    def _check(n):
        total = sum(int(d[i]) * (n - i) for i in range(n - 1))
        r = (total * 10) % 11
        return r if r < 10 else 0

    return _check(10) == int(d[9]) and _check(11) == int(d[10])


class CustomerForm(FlaskForm):
    name = StringField(
        "Nome completo",
        validators=[
            DataRequired(message="Nome é obrigatório."),
            Length(min=2, max=100, message="Nome deve ter entre 2 e 100 caracteres."),
        ],
    )
    phone = StringField(
        "Telefone",
        validators=[Optional(), Length(max=20, message="Telefone muito longo.")],
    )
    cpf = StringField(
        "CPF",
        validators=[Optional(), Length(max=14)],
    )
    email = StringField(
        "E-mail",
        validators=[
            Optional(),
            Email(message="E-mail inválido."),
            Length(max=120),
        ],
    )
    birth_date = DateField(
        "Data de nascimento",
        validators=[Optional()],
        format="%Y-%m-%d",
    )
    notes = TextAreaField(
        "Observações",
        validators=[Optional(), Length(max=1000, message="Máximo 1000 caracteres.")],
    )

    def __init__(self, customer_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._customer_id = customer_id

    def validate_phone(self, field):
        """Rejeita telefone se já existir outro cliente com os mesmos dígitos."""
        if not field.data or not field.data.strip():
            return
        digits = _digits(field.data)
        if not digits:
            return
        from app.models.customer import Customer
        for c in Customer.query.filter(Customer.phone.isnot(None)).all():
            if self._customer_id and c.id == self._customer_id:
                continue
            if _digits(c.phone) == digits:
                raise ValidationError(
                    f"Telefone já cadastrado para '{c.name}'. "
                    "Use o cliente existente ou corrija o número."
                )

    def validate_cpf(self, field):
        if not field.data or not field.data.strip():
            return
        if not _validate_cpf_digits(field.data):
            raise ValidationError("CPF inválido. Verifique os dígitos verificadores.")
        from app.models.customer import Customer
        clean = re.sub(r'\D', '', field.data)
        formatted = f'{clean[:3]}.{clean[3:6]}.{clean[6:9]}-{clean[9:]}'
        existing = Customer.query.filter_by(cpf=formatted).first()
        if existing and (not self._customer_id or existing.id != self._customer_id):
            raise ValidationError(f"CPF já cadastrado para '{existing.name}'.")
