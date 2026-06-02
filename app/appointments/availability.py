"""
Lógica de cálculo de disponibilidade de horários.

Algoritmo:
  1. Gera slots a cada SLOT_INTERVAL_MINUTES dentro do horário de trabalho do barbeiro.
  2. Para cada slot candidato, calcula o intervalo [slot_start, slot_start + duration).
  3. Verifica se esse intervalo colide com algum agendamento ativo existente
     (cancelled e no_show não bloqueiam horários).
  4. Retorna apenas os slots sem colisão.

Colisão: dois intervalos [A, B) e [C, D) colidem se A < D e B > C.
"""
from datetime import date, time, datetime, timedelta
from typing import List

SLOT_INTERVAL_MINUTES = 30
DEFAULT_WORK_START = time(8, 0)
DEFAULT_WORK_END = time(18, 0)

# Statuses that block a time slot
BLOCKING_STATUSES = {"pending", "confirmed", "completed"}


def get_available_slots(
    barber_id: int,
    service_id: int,
    target_date: date,
    exclude_appointment_id: int | None = None,
) -> List[time]:
    """
    Retorna lista de horários de início disponíveis (objetos time) para o
    barbeiro prestar o serviço na data especificada.
    exclude_appointment_id ignora um agendamento específico (usado em remarcações).
    Retorna lista vazia se barbeiro ou serviço não existirem.
    """
    from app.models.barber import Barber
    from app.models.service import Service
    from app.models.appointment import Appointment

    barber = Barber.query.get(barber_id)
    service = Service.query.get(service_id)
    if not barber or not service:
        return []

    work_start = barber.work_start_time or DEFAULT_WORK_START
    work_end = barber.work_end_time or DEFAULT_WORK_END
    duration = service.duration_minutes

    # Agendamentos ativos do barbeiro nesta data
    existing = (
        Appointment.query
        .filter_by(barber_id=barber_id, scheduled_date=target_date)
        .filter(Appointment.status.in_(list(BLOCKING_STATUSES)))
        .all()
    )

    # Pré-calcula intervalos bloqueados [a_start, a_end)
    blocked: list[tuple[datetime, datetime]] = []
    for appt in existing:
        if exclude_appointment_id and appt.id == exclude_appointment_id:
            continue
        svc = appt.service
        dur = svc.duration_minutes if svc else 60
        a_start = datetime.combine(target_date, appt.scheduled_time)
        blocked.append((a_start, a_start + timedelta(minutes=dur)))

    # Gera e filtra slots
    available: List[time] = []
    cursor = datetime.combine(target_date, work_start)
    deadline = datetime.combine(target_date, work_end)

    while cursor + timedelta(minutes=duration) <= deadline:
        cursor_end = cursor + timedelta(minutes=duration)
        # Colisão: cursor < b_end AND cursor_end > b_start
        has_conflict = any(
            cursor < b_end and cursor_end > b_start
            for b_start, b_end in blocked
        )
        if not has_conflict:
            available.append(cursor.time())
        cursor += timedelta(minutes=SLOT_INTERVAL_MINUTES)

    return available


def is_slot_available(
    barber_id: int,
    service_id: int,
    target_date: date,
    slot_time: time,
    exclude_appointment_id: int | None = None,
) -> bool:
    """
    Verifica se um slot específico está disponível.
    exclude_appointment_id ignora o próprio agendamento (usado em edições).
    """
    from app.models.barber import Barber
    from app.models.service import Service
    from app.models.appointment import Appointment

    barber = Barber.query.get(barber_id)
    service = Service.query.get(service_id)
    if not barber or not service:
        return False

    duration = service.duration_minutes
    slot_start = datetime.combine(target_date, slot_time)
    slot_end = slot_start + timedelta(minutes=duration)

    existing = (
        Appointment.query
        .filter_by(barber_id=barber_id, scheduled_date=target_date)
        .filter(Appointment.status.in_(list(BLOCKING_STATUSES)))
        .all()
    )

    for appt in existing:
        if exclude_appointment_id and appt.id == exclude_appointment_id:
            continue
        svc = appt.service
        dur = svc.duration_minutes if svc else 60
        a_start = datetime.combine(target_date, appt.scheduled_time)
        a_end = a_start + timedelta(minutes=dur)
        if slot_start < a_end and slot_end > a_start:
            return False

    return True
