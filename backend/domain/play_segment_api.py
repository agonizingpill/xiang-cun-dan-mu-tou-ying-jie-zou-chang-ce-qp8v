from fastapi import APIRouter, Depends

from core.auth import actor, allow
from core.audit import record
from core.db import transaction
from domain import play_segment_service as service
from domain.play_segment_schemas import ReportSegment

router = APIRouter()


@router.get('/play_segments')
def list_play_segments(user=Depends(actor)):
    with transaction() as conn:
        return service.list_segments(conn)


@router.get('/segment_conflicts')
def list_segment_conflicts(user=Depends(actor)):
    with transaction() as conn:
        return service.list_conflicts(conn)


@router.get('/segment_reminders')
def list_segment_reminders(user=Depends(actor)):
    with transaction() as conn:
        return service.list_reminders(conn)


@router.post('/play_segments/report-segment')
def report_segment(data: ReportSegment, user=Depends(actor)):
    allow(user, ('operator', 'reviewer'))
    with transaction() as conn:
        output = service.report_segment(conn, user, data)
        record(conn, user, 'play_segments.report')
        return output
