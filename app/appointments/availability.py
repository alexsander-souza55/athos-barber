"""
Lógica de cálculo de disponibilidade de horários.

Algoritmo:
  1. Verifica se existe exceção de agenda para o barbeiro nesta data.
     - day_off  → retorna lista vazia
     - custom_hours → usa os horários da exceção em vez do horário fixo
  2. Gera slots a cada SLOT_INTERVAL_MINUTES dentro do horário de trabalho.
  3. Para cada slot candidato, calcula o intervalo [slot_start, slot_start + duration).
     - Se kit_id fornecido: duration = soma das durações dos serviços do kit
     - Se service_id fornecido: duration = serviço.duration_minutes
  4. Verifica se esse intervalo colide com algum agendamento ativo existente.
     - Agendamentos com kit_id usam a duração total do kit como bloqueio.
     (cancelled e no_show não bloqueiam horários)
  5. Retorna apenas os slots sem colisão.

Colisão: dois intervalos [A, B) e [C, D) colidem se A < D e B > C.
"""
from datetime import date, time, datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo


def _now_local() -> datetime:
    from flask import current_app
    try:
        tz_name = current_app.config.get("TIMEZONE", "America/Campo_Grande")
    except RuntimeError:
        tz_name = "America/Campo_Grande"
    return datetime.now(ZoneInfo(tz_name)).replace(tzinfo=None)


SLOT_INTERVAL_MINUTES = 60
DEFAULT_WORK_START = time(8, 0)
DEFAULT_WORK_END = time(18, 0)

BLOCKING_STATUSES = {"pending", "confirmed", "completed"}


def _get_barber_exception(barber_id: int, target_date: date):
    from app.models.barber_schedule_exception import BarberScheduleException
    return BarberScheduleException.query.filter_by(
        barber_id=barber_id, date=target_date
    ).first()


def _appt_duration(appt) -> int:
    """Retorna a duração real de um agendamento existente (kit-aware)."""
    if appt.kit_id and appt.kit:
        return appt.kit.total_duration_minutes
    svc = appt.service
    return svc.duration_minutes if svc else 60


def _resolve_duration(service_id, kit_id) -> int | None:
    """Retorna a duração para o novo agendamento, ou None se inválido."""
    if kit_id:
        from app.models.service_kit import ServiceKit
        kit = ServiceKit.query.get(kit_id)
        return kit.total_duration_minutes if kit else None
    if service_id:
        from app.models.service import Service
        svc = Service.query.get(service_id)
        return svc.duration_minutes if svc else None
    return None


def get_available_slots(
    barber_id: int,
    service_id: int | None,
    target_date: date,
    exclude_appointment_id: int | None = None,
    kit_id: int | None = None,
) -> List[time]:
    """
    Retorna lista de horários de início disponíveis para o barbeiro na data.
    Passa service_id OU kit_id (não ambos). Se nenhum for válido, retorna [].
    exclude_appointment_id ignora um agendamento específico (usado em remarcações).
    """
    from app.models.barber import Barber
    from app.models.appointment import Appointment

    barber = Barber.query.get(barber_id)
    if not barber:
        return []

    duration = _resolve_duration(service_id, kit_id)
    if duration is None:
        return []

    work_start = barber.work_start_time or DEFAULT_WORK_START
    work_end = barber.work_end_time or DEFAULT_WORK_END

    exc = _get_barber_exception(barber_id, target_date)
    if exc:
        if exc.exception_type == "day_off":
            return []
        if exc.exception_type == "custom_hours":
            if exc.start_time:
                work_start = exc.start_time
            if exc.end_time:
                work_end = exc.end_time

    existing = (
        Appointment.query
        .filter_by(barber_id=barber_id, scheduled_date=target_date)
        .filter(Appointment.status.in_(list(BLOCKING_STATUSES)))
        .all()
    )

    blocked: list[tuple[datetime, datetime]] = []
    for appt in existing:
        if exclude_appointment_id and appt.id == exclude_appointment_id:
            continue
        dur = _appt_duration(appt)
        a_start = datetime.combine(target_date, appt.scheduled_time)
        blocked.append((a_start, a_start + timedelta(minutes=dur)))

    if barber.lunch_start and barber.lunch_end:
        blocked.append((
            datetime.combine(target_date, barber.lunch_start),
            datetime.combine(target_date, barber.lunch_end),
        ))

    available: List[time] = []
    cursor = datetime.combine(target_date, work_start)
    deadline = datetime.combine(target_date, work_end)

    while cursor + timedelta(minutes=duration) <= deadline:
        cursor_end = cursor + timedelta(minutes=duration)
        has_conflict = any(
            cursor < b_end and cursor_end > b_start
            for b_start, b_end in blocked
        )
        if not has_conflict:
            available.append(cursor.time())
        cursor += timedelta(minutes=SLOT_INTERVAL_MINUTES)

    if target_date == date.today():
        now = _now_local()
        available = [t for t in available if datetime.combine(target_date, t) > now]

    return available


def is_slot_available(
    barber_id: int,
    service_id: int | None,
    target_date: date,
    slot_time: time,
    exclude_appointment_id: int | None = None,
    kit_id: int | None = None,
) -> bool:
    """
    Verifica se um slot específico está disponível.
    Passa service_id OU kit_id. Considera exceções e colisões.
    """
    from app.models.barber import Barber
    from app.models.appointment import Appointment

    barber = Barber.query.get(barber_id)
    if not barber:
        return False

    duration = _resolve_duration(service_id, kit_id)
    if duration is None:
        return False

    work_start = barber.work_start_time or DEFAULT_WORK_START
    work_end = barber.work_end_time or DEFAULT_WORK_END

    exc = _get_barber_exception(barber_id, target_date)
    if exc:
        if exc.exception_type == "day_off":
            return False
        if exc.exception_type == "custom_hours":
            if exc.start_time:
                work_start = exc.start_time
            if exc.end_time:
                work_end = exc.end_time

    slot_start = datetime.combine(target_date, slot_time)
    slot_end = slot_start + timedelta(minutes=duration)
    deadline = datetime.combine(target_date, work_end)

    if slot_start < datetime.combine(target_date, work_start) or slot_end > deadline:
        return False

    if barber.lunch_start and barber.lunch_end:
        lunch_s = datetime.combine(target_date, barber.lunch_start)
        lunch_e = datetime.combine(target_date, barber.lunch_end)
        if slot_start < lunch_e and slot_end > lunch_s:
            return False

    existing = (
        Appointment.query
        .filter_by(barber_id=barber_id, scheduled_date=target_date)
        .filter(Appointment.status.in_(list(BLOCKING_STATUSES)))
        .all()
    )

    for appt in existing:
        if exclude_appointment_id and appt.id == exclude_appointment_id:
            continue
        dur = _appt_duration(appt)
        a_start = datetime.combine(target_date, appt.scheduled_time)
        a_end = a_start + timedelta(minutes=dur)
        if slot_start < a_end and slot_end > a_start:
            return False

    return True
