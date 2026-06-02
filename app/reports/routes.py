from datetime import date

from flask import (
    Blueprint, render_template, request,
    send_file, flash, redirect, url_for,
)
from flask_login import login_required

from app.utils.decorators import admin_required
from app.reports.generators import (
    build_appointments, build_revenue,
    build_services, build_barbers,
    to_excel, to_pdf,
)

reports_bp = Blueprint("reports", __name__)

# Mapeia o parâmetro `report=` ao builder correspondente
_BUILDERS = {
    "appointments": build_appointments,
    "revenue":      build_revenue,
    "services":     build_services,
    "barbers":      build_barbers,
}

_MIMETYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf":  "application/pdf",
}


@reports_bp.route("/")
@login_required
@admin_required
def index():
    today = date.today()
    month_start = today.replace(day=1)
    return render_template(
        "reports/index.html",
        default_from=month_start.isoformat(),
        default_to=today.isoformat(),
    )


@reports_bp.route("/export")
@login_required
@admin_required
def export():
    report_type = request.args.get("report", "appointments")
    fmt         = request.args.get("fmt", "xlsx").lower()
    date_from_s = request.args.get("date_from", "")
    date_to_s   = request.args.get("date_to", "")

    # Valida formato
    if fmt not in _MIMETYPES:
        flash("Formato inválido. Use xlsx ou pdf.", "danger")
        return redirect(url_for("reports.index"))

    # Valida tipo de relatório
    builder = _BUILDERS.get(report_type)
    if not builder:
        flash("Tipo de relatório inválido.", "danger")
        return redirect(url_for("reports.index"))

    # Parseia datas (default: mês atual)
    today = date.today()
    try:
        date_from = date.fromisoformat(date_from_s) if date_from_s else today.replace(day=1)
    except ValueError:
        date_from = today.replace(day=1)
    try:
        date_to = date.fromisoformat(date_to_s) if date_to_s else today
    except ValueError:
        date_to = today

    if date_from > date_to:
        flash("A data inicial não pode ser posterior à data final.", "warning")
        return redirect(url_for("reports.index"))

    # Constrói dados do relatório
    report_data = builder(date_from, date_to)

    # Gera arquivo
    try:
        if fmt == "xlsx":
            buf = to_excel(report_data)
        else:
            buf = to_pdf(report_data)
    except ImportError as exc:
        flash(f"Dependência ausente: {exc}. Verifique as bibliotecas instaladas.", "danger")
        return redirect(url_for("reports.index"))
    except Exception as exc:
        flash(f"Erro ao gerar relatório: {exc}", "danger")
        return redirect(url_for("reports.index"))

    return send_file(
        buf,
        download_name=f"{report_data['filename']}.{fmt}",
        as_attachment=True,
        mimetype=_MIMETYPES[fmt],
    )


# Mantém compatibilidade com referências antigas ao endpoint export_appointments
@reports_bp.route("/appointments/export")
@login_required
@admin_required
def export_appointments():
    return redirect(url_for(
        "reports.export",
        report="appointments",
        fmt=request.args.get("format", "xlsx"),
        date_from=request.args.get("date_from", ""),
        date_to=request.args.get("date_to", ""),
    ))
