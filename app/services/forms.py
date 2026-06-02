from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, DecimalField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError


class ServiceForm(FlaskForm):
    name = StringField(
        "Nome do serviço",
        validators=[
            DataRequired(message="Nome é obrigatório."),
            Length(min=2, max=100, message="Nome deve ter entre 2 e 100 caracteres."),
        ],
    )
    description = TextAreaField(
        "Descrição",
        validators=[Optional(), Length(max=500, message="Máximo 500 caracteres.")],
    )
    price = DecimalField(
        "Preço (R$)",
        places=2,
        validators=[
            DataRequired(message="Preço é obrigatório."),
            NumberRange(
                min=0.01, max=9999.99,
                message="Preço deve estar entre R$ 0,01 e R$ 9.999,99.",
            ),
        ],
    )
    duration_minutes = IntegerField(
        "Duração (minutos)",
        validators=[
            DataRequired(message="Duração é obrigatória."),
            NumberRange(
                min=5, max=480,
                message="Duração deve ser entre 5 minutos e 8 horas (480 min).",
            ),
        ],
    )
    is_active = BooleanField("Serviço ativo")

    def __init__(self, service_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._service_id = service_id

    def validate_name(self, field):
        from app.models.service import Service
        from app.extensions import db
        query = Service.query.filter(
            db.func.lower(Service.name) == field.data.strip().lower()
        )
        if self._service_id:
            query = query.filter(Service.id != self._service_id)
        if query.first():
            raise ValidationError("Já existe um serviço com este nome.")
