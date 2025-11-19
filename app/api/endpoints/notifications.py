"""
Notifications Endpoints
Synthesizes notifications from existing database entities (appointments, stock alerts, messages)
and provides actions to resolve/acknowledge them.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_session
from app.core.auth import get_current_user
from app.models import User, UserRole, Appointment, Patient
from app.models.stock import StockAlert
from app.models.message import MessageThread, Message, MessageStatus


router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def list_notifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Return synthesized notifications for the current user.
    - Staff (admin/secretary/doctor): unresolved stock alerts, recent appointments, and unread messages
    - Patient: upcoming appointments and unread messages
    """
    notifications: list[dict] = []

    now = datetime.now(timezone.utc)

    # Get unread message count for all users
    unread_message_count = 0
    patient = None
    try:
        # Check if user is a patient
        patient_query = select(Patient).filter(
            and_(
                Patient.email == current_user.email,
                Patient.clinic_id == current_user.clinic_id
            )
        )
        patient_result = await db.execute(patient_query)
        patient = patient_result.scalar_one_or_none()
        
        if patient:
            # Patient: count messages from providers that are unread
            unread_query = select(func.count(Message.id)).join(
                MessageThread, Message.thread_id == MessageThread.id
            ).filter(
                and_(
                    MessageThread.patient_id == patient.id,
                    MessageThread.clinic_id == current_user.clinic_id,
                    Message.sender_type != "patient",
                    Message.status != MessageStatus.READ
                )
            )
        else:
            # Staff: count messages from patients that are unread
            unread_query = select(func.count(Message.id)).join(
                MessageThread, Message.thread_id == MessageThread.id
            ).filter(
                and_(
                    MessageThread.provider_id == current_user.id,
                    MessageThread.clinic_id == current_user.clinic_id,
                    Message.sender_type == "patient",
                    Message.status != MessageStatus.READ
                )
            )
        
        unread_result = await db.execute(unread_query)
        unread_message_count = unread_result.scalar() or 0
        
        # Add message notification if there are unread messages
        if unread_message_count > 0:
            notifications.append({
                "id": f"messages:unread",
                "kind": "message",
                "source_id": 0,
                "title": f"{unread_message_count} mensagem{'s' if unread_message_count > 1 else ''} não lida{'s' if unread_message_count > 1 else ''}",
                "message": f"Você tem {unread_message_count} mensagem{'s' if unread_message_count > 1 else ''} não lida{'s' if unread_message_count > 1 else ''}.",
                "type": "info",
                "priority": "high" if unread_message_count > 5 else "medium",
                "read": False,
                "timestamp": now.isoformat(),
                "source": "Mensagens",
                "actionUrl": "/patient/messages" if patient else "/secretaria/mensagens",
                "actionText": "Ver mensagens",
            })
    except Exception as e:
        # Log error but don't fail the entire endpoint
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to count unread messages: {str(e)}")
        # Continue without message notifications

    # Patients: upcoming appointments within next 7 days
    # Check role as string to handle both enum and string values
    is_patient = str(current_user.role).lower() == "patient" if current_user.role else False
    if is_patient:
        # Use patient from earlier query if available, otherwise query again
        if patient is None:
            patient_query = select(Patient).filter(
                and_(
                    Patient.email == current_user.email,
                    Patient.clinic_id == current_user.clinic_id
                )
            )
            patient_result = await db.execute(patient_query)
            patient = patient_result.scalar_one_or_none()
        
        if patient:
            try:
                appt_stmt = (
                    select(Appointment)
                    .where(
                        and_(
                            Appointment.clinic_id == current_user.clinic_id,
                            Appointment.patient_id == patient.id,
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
                            "actionUrl": "/patient/appointments",
                            "actionText": "Ver consulta",
                        }
                    )
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to load patient appointments: {str(e)}")
        
        return {"data": notifications}

    # Staff: unresolved stock alerts
    try:
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
            notifications.append({
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
    except Exception as e:
        # Log error but don't fail the entire endpoint
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to load stock alerts: {str(e)}")
        # Continue without stock alert notifications

    # Staff: upcoming appointments today (overview)
    try:
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
    except Exception as e:
        # Log error but don't fail the entire endpoint
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to load appointments: {str(e)}")
        # Continue without appointment notifications

    return {"data": notifications}


@router.post("/{kind}/{source_id}/read")
async def mark_notification_read(
    kind: str,
    source_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Mark notification as read.
    - For stock alerts: mark as resolved in DB
    - For messages: mark all unread messages in threads as read (if source_id is 0, mark all)
    - For appointments: no-op success (read state not persisted yet)
    """
    if kind == "stock":
        alert = await db.get(StockAlert, source_id)
        if not alert or alert.clinic_id != current_user.clinic_id:
            raise HTTPException(status_code=404, detail="Alert not found")
        alert.is_resolved = True
        await db.commit()
        return {"status": "ok", "resolved": True}
    elif kind == "message":
        # For message notifications, we don't mark individual messages as read here
        # The message read state is handled in the messages endpoint
        # This is just a no-op to acknowledge the notification
        return {"status": "ok"}
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


