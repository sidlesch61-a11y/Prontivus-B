from __future__ import annotations
from typing import List, Dict, Any, Tuple
from datetime import datetime


def standardize_string(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def parse_iso_date(value: Any) -> str | None:
    if not value:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            continue
    try:
        return datetime.fromisoformat(s).date().isoformat()
    except Exception:
        return None


def standardize_patient(r: Dict[str, Any]) -> Dict[str, Any]:
    out = {k.strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
    out['first_name'] = standardize_string(out.get('first_name') or out.get('nome'))
    out['last_name'] = standardize_string(out.get('last_name') or out.get('sobrenome'))
    out['date_of_birth'] = parse_iso_date(out.get('date_of_birth') or out.get('dob') or out.get('nascimento'))
    out['email'] = standardize_string(out.get('email'))
    out['phone'] = standardize_string(out.get('phone') or out.get('telefone'))
    return out


def standardize_appointment(r: Dict[str, Any]) -> Dict[str, Any]:
    out = {k.strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
    dt = out.get('scheduled_datetime') or out.get('datetime')
    try:
        out['scheduled_datetime'] = datetime.fromisoformat(str(dt)).isoformat()
    except Exception:
        out['scheduled_datetime'] = None
    out['doctor_id'] = out.get('doctor_id') or out.get('medico_id')
    out['patient_id'] = out.get('patient_id') or out.get('paciente_id')
    return out


def deduplicate(records: List[Dict[str, Any]], key_fields: List[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    seen = set()
    uniques: List[Dict[str, Any]] = []
    dups: List[Dict[str, Any]] = []
    for r in records:
        key = tuple((str(r.get(k) or '')).lower() for k in key_fields)
        if key in seen:
            dups.append(r)
        else:
            seen.add(key)
            uniques.append(r)
    return uniques, dups


def missing_report(records: List[Dict[str, Any]], required: List[str]) -> Dict[str, int]:
    report: Dict[str, int] = {k: 0 for k in required}
    for r in records:
        for k in required:
            if not r.get(k):
                report[k] += 1
    return report


def privacy_issues(r: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    for k in ('ssn', 'social_security_number', 'credit_card', 'cc_number'):
        if r.get(k):
            issues.append(f"Field '{k}' present; remove before import")
    return issues


