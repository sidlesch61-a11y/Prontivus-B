import csv
import io
import json
from typing import Iterable, Tuple, Dict, Any, List, Optional
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.migration import MigrationJob, MigrationStatus, MigrationType
from app.services.migration_validators import (
    standardize_patient as std_patient,
    standardize_appointment as std_appt,
    deduplicate as dd,
    missing_report,
    privacy_issues,
)


async def create_job(db: AsyncSession, clinic_id: int, user_id: int, job_type: str, input_format: str, source_name: Optional[str], params: Optional[dict]) -> MigrationJob:
    job = MigrationJob(
        clinic_id=clinic_id,
        created_by=user_id,
        type=MigrationType(job_type),
        status=MigrationStatus.PENDING,
        input_format=input_format,
        source_name=source_name,
        params=params or {},
        stats={},
        errors={},
    )
    db.add(job)
    await db.flush()
    return job


def _parse_csv(content: bytes) -> List[Dict[str, Any]]:
    text = content.decode('utf-8-sig', errors='ignore')
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def _parse_json(content: bytes) -> List[Dict[str, Any]]:
    data = json.loads(content.decode('utf-8'))
    return data if isinstance(data, list) else [data]


def _standardize(records: List[Dict[str, Any]], job_type: MigrationType) -> List[Dict[str, Any]]:
    if job_type == MigrationType.PATIENTS:
        return [std_patient(r) for r in records]
    if job_type == MigrationType.APPOINTMENTS:
        return [std_appt(r) for r in records]
    return records


async def run_job(db: AsyncSession, job: MigrationJob, content: bytes) -> Tuple[int, Dict[str, Any], Dict[str, Any]]:
    start = datetime.now(timezone.utc)
    await db.execute(update(MigrationJob).where(MigrationJob.id == job.id).values(status=MigrationStatus.RUNNING, started_at=start))
    await db.flush()

    # Parse
    if job.input_format == 'csv':
        records = _parse_csv(content)
    else:
        records = _parse_json(content)

    original_count = len(records)

    # Standardize & validate
    records = _standardize(records, job.type)
    if job.type == MigrationType.PATIENTS:
        records, dups = dd(records, ['first_name', 'last_name', 'date_of_birth'])
        miss = missing_report(records, ['first_name', 'last_name', 'date_of_birth'])
        privacy = sum(([privacy_issues(r) for r in records]), [])
        errors = {'duplicates': dups[:100], 'missing': miss, 'privacy': privacy[:100]}
        imported = len(records)
        # TODO: Persist into Patient table in batches and map IDs
    elif job.type == MigrationType.APPOINTMENTS:
        miss = missing_report(records, ['patient_id', 'doctor_id', 'scheduled_datetime'])
        errors = {'missing': miss}
        imported = len(records)
        dups = []
    else:
        # basic pass-through; extend per domain
        dups = []
        errors = {}
        imported = len(records)

    end = datetime.now(timezone.utc)
    stats = {
        'original_count': original_count,
        'imported': imported,
        'duplicates': len(dups),
        'duration_sec': max(0, (end - start).total_seconds()),
        'incremental': bool((job.params or {}).get('since') or (job.params or {}).get('cursor')),
    }

    status = MigrationStatus.COMPLETED
    await db.execute(update(MigrationJob).where(MigrationJob.id == job.id).values(
        status=status,
        completed_at=end,
        stats=stats,
        errors=errors,
    ))
    await db.flush()
    return imported, stats, errors


