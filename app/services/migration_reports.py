from typing import Dict, Any, List


def pre_migration_quality(records: List[dict]) -> Dict[str, Any]:
    total = len(records)
    missing_name = sum(1 for r in records if not (r.get('first_name') and r.get('last_name')))
    missing_dob = sum(1 for r in records if not r.get('date_of_birth'))
    return {
        'total_records': total,
        'missing_name': missing_name,
        'missing_dob': missing_dob,
        'completeness_pct': round(100.0 * (total - (missing_name + missing_dob)) / max(total, 1), 2)
    }


def post_migration_validation(imported: int, stats: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'imported': imported,
        'duplicates_filtered': stats.get('duplicates', 0),
        'duration_sec': stats.get('duration_sec', 0)
    }


def reconcile(source_count: int, target_count: int) -> Dict[str, Any]:
    return {
        'source_count': source_count,
        'target_count': target_count,
        'delta': target_count - source_count
    }


