"""Helpers para consumo e estorno de créditos do Clube Athos."""
from datetime import date
from app.extensions import db


def get_active_subscription(customer_id: int):
    """
    Retorna a assinatura ativa do cliente ou None.
    Considera ativa: status=active + (prazo não vencido OU créditos restantes).
    """
    from app.models.subscription import CustomerSubscription
    today = date.today()

    # Primeiro: assinatura dentro do prazo
    sub = (
        CustomerSubscription.query
        .filter_by(customer_id=customer_id, status="active")
        .filter(CustomerSubscription.end_date >= today)
        .first()
    )
    if sub:
        return sub

    # Segundo: assinatura vencida mas com créditos remanescentes
    expired_subs = (
        CustomerSubscription.query
        .filter_by(customer_id=customer_id, status="active")
        .filter(CustomerSubscription.end_date < today)
        .all()
    )
    for expired in expired_subs:
        if expired.has_remaining_credits:
            return expired

    return None


def check_credit(customer_id: int, service_id: int) -> dict:
    """Verifica se o cliente tem crédito disponível para o serviço."""
    from app.models.subscription import SubscriptionCreditBalance
    sub = get_active_subscription(customer_id)
    if not sub:
        return {"has_credit": False}
    balance = SubscriptionCreditBalance.query.filter_by(
        subscription_id=sub.id, service_id=service_id,
    ).first()
    if not balance or balance.remaining_credits <= 0:
        return {"has_credit": False}
    return {
        "has_credit": True,
        "plan_name": sub.plan.name,
        "remaining": balance.remaining_credits,
    }


def check_credit_kit(customer_id: int, kit_id: int) -> dict:
    """Verifica se o cliente tem crédito para todos os serviços do kit."""
    from app.models.service_kit import ServiceKit
    from app.models.subscription import SubscriptionCreditBalance
    sub = get_active_subscription(customer_id)
    if not sub:
        return {"has_credit": False}
    kit = ServiceKit.query.get(kit_id)
    if not kit:
        return {"has_credit": False}
    for item in kit.items:
        bal = SubscriptionCreditBalance.query.filter_by(
            subscription_id=sub.id, service_id=item.service_id,
        ).first()
        if not bal or bal.remaining_credits <= 0:
            return {"has_credit": False}
    return {
        "has_credit": True,
        "plan_name": sub.plan.name,
        "kit_name": kit.name,
    }


def consume_credit(customer_id: int, service_id: int, appointment_id: int) -> bool:
    """Deduz 1 crédito de um serviço. Retorna True se consumido."""
    from app.models.subscription import SubscriptionCreditBalance, SubscriptionCreditUsage
    sub = get_active_subscription(customer_id)
    if not sub:
        return False
    balance = SubscriptionCreditBalance.query.filter_by(
        subscription_id=sub.id, service_id=service_id,
    ).first()
    if not balance or balance.remaining_credits <= 0:
        return False
    balance.used_credits += 1
    db.session.add(SubscriptionCreditUsage(
        subscription_id=sub.id,
        appointment_id=appointment_id,
        service_id=service_id,
    ))
    return True


def consume_credit_kit(customer_id: int, kit, appointment_id: int) -> bool:
    """
    Deduz 1 crédito de cada serviço do kit de forma atômica.
    Se algum serviço não tiver crédito, não deduz nenhum (retorna False).
    """
    from app.models.subscription import SubscriptionCreditBalance, SubscriptionCreditUsage
    sub = get_active_subscription(customer_id)
    if not sub:
        return False

    # Verificar que todos os serviços do kit têm crédito
    balances = []
    for item in kit.items:
        bal = SubscriptionCreditBalance.query.filter_by(
            subscription_id=sub.id, service_id=item.service_id,
        ).first()
        if not bal or bal.remaining_credits <= 0:
            return False
        balances.append((bal, item.service_id))

    # Deduzir todos atomicamente
    for bal, service_id in balances:
        bal.used_credits += 1
        db.session.add(SubscriptionCreditUsage(
            subscription_id=sub.id,
            appointment_id=appointment_id,
            service_id=service_id,
        ))
    return True


def refund_credit(appointment_id: int) -> bool:
    """
    Estorna todos os créditos usados por este agendamento.
    Suporta kits (múltiplos SubscriptionCreditUsage por appointment_id).
    Retorna True se ao menos um crédito foi estornado.
    """
    from app.models.subscription import SubscriptionCreditUsage, SubscriptionCreditBalance
    usages = SubscriptionCreditUsage.query.filter_by(appointment_id=appointment_id).all()
    if not usages:
        return False
    for usage in usages:
        balance = SubscriptionCreditBalance.query.filter_by(
            subscription_id=usage.subscription_id,
            service_id=usage.service_id,
        ).first()
        if balance:
            balance.used_credits = max(0, balance.used_credits - 1)
        db.session.delete(usage)
    return True
