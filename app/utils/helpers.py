import os
from werkzeug.utils import secure_filename
from flask import current_app
import uuid
from PIL import Image


def allowed_file(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]
    )


def _is_valid_image(file) -> bool:
    """Verifica via Pillow que o arquivo é realmente uma imagem (conteúdo, não só extensão)."""
    try:
        file.seek(0)
        img = Image.open(file)
        img.verify()
        file.seek(0)
        return True
    except Exception:
        file.seek(0)
        return False


def save_upload(file, subfolder: str = "") -> str:
    """Salva um arquivo no diretório de uploads. Retorna o caminho relativo ao UPLOAD_FOLDER."""
    if not file or not file.filename:
        raise ValueError("Nenhum arquivo fornecido.")
    if not allowed_file(file.filename):
        raise ValueError("Tipo de arquivo não permitido.")
    if not _is_valid_image(file):
        raise ValueError("O arquivo enviado não é uma imagem válida.")
    safe_name = secure_filename(file.filename)
    ext = safe_name.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    if subfolder:
        upload_dir = os.path.join(upload_dir, subfolder)
    os.makedirs(upload_dir, exist_ok=True)
    try:
        file.save(os.path.join(upload_dir, filename))
    except OSError as exc:
        raise RuntimeError(f"Falha ao salvar arquivo: {exc}") from exc
    return f"{subfolder}/{filename}" if subfolder else filename


def delete_upload(relative_path: str) -> None:
    """Remove um arquivo do diretório de uploads. relative_path é relativo ao UPLOAD_FOLDER."""
    if not relative_path:
        return
    full_path = os.path.join(
        current_app.config["UPLOAD_FOLDER"],
        relative_path.lstrip("/"),
    )
    if os.path.isfile(full_path):
        os.remove(full_path)


def format_currency(value) -> str:
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "R$ 0,00"
