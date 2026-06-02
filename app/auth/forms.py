from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, BooleanField,
    SubmitField, SelectField, TextAreaField,
)
from wtforms.validators import (
    DataRequired, Email, Length, EqualTo, Optional, ValidationError,
)


# ── Login ────────────────────────────────────────────────────────────────────
class LoginForm(FlaskForm):
    username = StringField(
        "Usuário",
        validators=[DataRequired(message="Informe o usuário."), Length(3, 64)],
    )
    password = PasswordField(
        "Senha",
        validators=[DataRequired(message="Informe a senha.")],
    )
    remember_me = BooleanField("Lembrar-me por 30 dias")
    submit = SubmitField("Entrar")


# ── Alterar senha (usuário logado) ────────────────────────────────────────────
class ChangePasswordForm(FlaskForm):
    current_password = PasswordField(
        "Senha atual",
        validators=[DataRequired(message="Informe a senha atual.")],
    )
    new_password = PasswordField(
        "Nova senha",
        validators=[
            DataRequired(),
            Length(6, 128, message="A senha deve ter no mínimo 6 caracteres."),
        ],
    )
    confirm_password = PasswordField(
        "Confirmar nova senha",
        validators=[
            DataRequired(),
            EqualTo("new_password", message="As senhas não coincidem."),
        ],
    )
    submit = SubmitField("Alterar senha")


# ── Perfil do usuário (email + barber profile) ────────────────────────────────
class ProfileForm(FlaskForm):
    email = StringField(
        "E-mail",
        validators=[Optional(), Email(message="E-mail inválido.")],
    )
    # Campos exclusivos do perfil barbeiro
    name = StringField("Nome completo", validators=[Optional(), Length(max=100)])
    phone = StringField("Telefone", validators=[Optional(), Length(max=20)])
    specialty = StringField("Especialidade", validators=[Optional(), Length(max=100)])
    bio = TextAreaField("Bio", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Salvar perfil")

    def __init__(self, user_id: int = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._user_id = user_id

    def validate_email(self, field):
        if not field.data:
            return
        from app.models.user import User
        existing = User.query.filter(
            User.email == field.data.strip(),
            User.id != self._user_id,
        ).first()
        if existing:
            raise ValidationError("Este e-mail já está em uso por outro usuário.")


# ── Criar usuário (admin) ─────────────────────────────────────────────────────
class RegisterUserForm(FlaskForm):
    username = StringField(
        "Nome de usuário",
        validators=[DataRequired(), Length(3, 64, message="Entre 3 e 64 caracteres.")],
    )
    email = StringField(
        "E-mail",
        validators=[DataRequired(), Email(message="E-mail inválido.")],
    )
    password = PasswordField(
        "Senha",
        validators=[
            DataRequired(),
            Length(6, 128, message="Mínimo 6 caracteres."),
        ],
    )
    confirm_password = PasswordField(
        "Confirmar senha",
        validators=[
            DataRequired(),
            EqualTo("password", message="As senhas não coincidem."),
        ],
    )
    role = SelectField(
        "Perfil de acesso",
        choices=[("barber", "Barbeiro"), ("admin", "Administrador")],
        default="barber",
    )
    # Campos do perfil barbeiro (obrigatórios quando role=barber)
    name = StringField("Nome completo", validators=[DataRequired(), Length(max=100)])
    phone = StringField("Telefone", validators=[Optional(), Length(max=20)])
    specialty = StringField("Especialidade", validators=[Optional(), Length(max=100)])
    submit = SubmitField("Criar usuário")

    def validate_username(self, field):
        from app.models.user import User
        if User.query.filter_by(username=field.data.strip()).first():
            raise ValidationError("Este nome de usuário já está em uso.")

    def validate_email(self, field):
        from app.models.user import User
        if User.query.filter_by(email=field.data.strip()).first():
            raise ValidationError("Este e-mail já está cadastrado.")


# ── Editar usuário (admin) ────────────────────────────────────────────────────
class EditUserForm(FlaskForm):
    username = StringField(
        "Nome de usuário",
        validators=[DataRequired(), Length(3, 64)],
    )
    email = StringField(
        "E-mail",
        validators=[DataRequired(), Email(message="E-mail inválido.")],
    )
    role = SelectField(
        "Perfil de acesso",
        choices=[("barber", "Barbeiro"), ("admin", "Administrador")],
    )
    is_active = BooleanField("Conta ativa")
    submit = SubmitField("Salvar alterações")

    def __init__(self, user_id: int = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._user_id = user_id

    def validate_username(self, field):
        from app.models.user import User
        existing = User.query.filter(
            User.username == field.data.strip(),
            User.id != self._user_id,
        ).first()
        if existing:
            raise ValidationError("Nome de usuário já em uso.")

    def validate_email(self, field):
        from app.models.user import User
        existing = User.query.filter(
            User.email == field.data.strip(),
            User.id != self._user_id,
        ).first()
        if existing:
            raise ValidationError("E-mail já cadastrado.")


# ── Redefinir senha (admin redefine para outro usuário) ───────────────────────
class AdminResetPasswordForm(FlaskForm):
    new_password = PasswordField(
        "Nova senha",
        validators=[
            DataRequired(),
            Length(6, 128, message="Mínimo 6 caracteres."),
        ],
    )
    confirm_password = PasswordField(
        "Confirmar senha",
        validators=[
            DataRequired(),
            EqualTo("new_password", message="As senhas não coincidem."),
        ],
    )
    submit = SubmitField("Redefinir senha")
