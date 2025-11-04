"""
Notifications Endpoints
Synthesizes notifications from existing database entities (appointments, stock alerts)
and provides actions to resolve/acknowledge them.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_session
from app.core.auth import get_current_user
from app.models import User, UserRole, Appointment
from app.models.stock import StockAlert


router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def list_notifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Return synthesized notifications for the current user.
    - Staff (admin/secretary/doctor): unresolved stock alerts and recent appointments
    - Patient: upcoming appointments
    """
    notifications: list[dict] = []

    now = datetime.now(timezone.utc)

    # Patients: upcoming appointments within next 7 days
    if current_user.role == UserRole.PATIENT:
        appt_stmt = (
            select(Appointment)
            .where(
                and_(
                    Appointment.clinic_id == current_user.clinic_id,
                    Appointment.patient_id.isnot(None),
                    Appointment.scheduled_datetime >= now,
                    Appointment.scheduled_datetime <= now + timedelta(days=7),
                )
            )
            .order_by(Appointment.scheduled_datetime)
            .limit(50)
        )
        appts = (await db.execute(appt_stmt)).scalars().all()
        for a in appts:
            notifications.append(
                {
                    "id": f"appt:{a.id}",
                    "kind": "appointment",
                    "source_id": a.id,
                    "title": "Lembrete de consulta",
                    "message": "Você tem uma consulta agendada em breve.",
                    "type": "appointment",
                    "priority": "high",
                    "read": False,
                    "timestamp": (a.scheduled_datetime or now).isoformat(),
                    "source": "Agendamentos",
                    "actionUrl": "/portal/appointments",
                    "actionText": "Ver consulta",
                }
            )
        return {"data": notifications}

    # Staff: unresolved stock alerts
    alerts_stmt = (
        select(StockAlert)
        .where(
            and_(
                StockAlert.clinic_id == current_user.clinic_id,
                StockAlert.is_resolved == False,  # noqa: E712
            )
        )
        .order_by(desc(StockAlert.created_at))
        .limit(100)
    )
    alerts = (await db.execute(alerts_stmt)).scalars().all()
    for alert in alerts:
        priority = "urgent" if getattr(alert, "severity", "").lower() in {"high", "critical"} else "high"
        notifications.append(
            {
                "id": f"stock:{alert.id}",
                "kind": "stock",
                "source_id": alert.id,
                "title": getattr(alert, "title", "Alerta de estoque"),
                "message": getattr(alert, "message", "Produto com baixo estoque"),
                "type": "warning",
                "priority": priority,
                "read": False,
                "timestamp": (getattr(alert, "created_at", now) or now).isoformat(),
                "source": "Estoque",
                "actionUrl": "/estoque",
                "actionText": "Abrir estoque",
            }
        )

    # Staff: upcoming appointments today (overview)
    appt_stmt = (
        select(Appointment)
        .where(
            and_(
                Appointment.clinic_id == current_user.clinic_id,
                Appointment.scheduled_datetime >= now.replace(hour=0, minute=0, second=0, microsecond=0),
                Appointment.scheduled_datetime < (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)),
            )
        )
        .order_by(Appointment.scheduled_datetime)
        .limit(50)
    )
    appts = (await db.execute(appt_stmt)).scalars().all()
    for a in appts:
        notifications.append(
            {
                "id": f"appt:{a.id}",
                "kind": "appointment",
                "source_id": a.id,
                "title": "Consulta de hoje",
                "message": "Consulta agendada para hoje.",
                "type": "info",
                "priority": "medium",
                "read": False,
                "timestamp": (a.scheduled_datetime or now).isoformat(),
                "source": "Agendamentos",
                "actionUrl": "/secretaria/agendamentos",
                "actionText": "Ver agenda",
            }
        )

    return {"data": notifications}


@router.post("/{kind}/{source_id}/read")
async def mark_notification_read(
    kind: str,
    source_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    For stock alerts, mark as resolved in DB. For other kinds, no-op success.
    """
    if kind == "stock":
        alert = await db.get(StockAlert, source_id)
        if not alert or alert.clinic_id != current_user.clinic_id:
            raise HTTPException(status_code=404, detail="Alert not found")
        alert.is_resolved = True
        await db.commit()
        return {"status": "ok", "resolved": True}
    # For appointment kind we don't persist read state yet
    return {"status": "ok"}


@router.delete("/{kind}/{source_id}")
async def delete_notification(
    kind: str,
    source_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    For stock alerts, resolve them (treated as delete). Other kinds: no-op.
    """
    if kind == "stock":
        alert = await db.get(StockAlert, source_id)
        if not alert or alert.clinic_id != current_user.clinic_id:
            raise HTTPException(status_code=404, detail="Alert not found")
        alert.is_resolved = True
        await db.commit()
        return {"status": "ok", "resolved": True}
    return {"status": "ok"}


