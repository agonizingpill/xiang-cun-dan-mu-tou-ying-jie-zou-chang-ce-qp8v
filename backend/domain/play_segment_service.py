from fastapi import HTTPException
from sqlalchemy import select

from core.records import get, insert
from domain.cue_tracks_model import cue_tracks
from domain.cue_clusters_model import cue_clusters
from domain.cue_routing_model import cue_routing
from domain.play_segment_model import play_segments, segment_conflicts, segment_reminders
from domain.play_segment_logic import apply_report


def _template_timings(conn, routing_code):
    route = get(conn, cue_routing, routing_code)
    group = get(conn, cue_clusters, route['cluster'])
    return get(conn, cue_tracks, group['representative'])['timings']


def _ordered(conn, table, routing_code):
    rows = conn.execute(select(table).where(table.c.routing == routing_code)
                        .order_by(table.c.segment)).mappings().all()
    return [dict(row) for row in rows]


def report_segment(conn, user, data):
    # 锁住回单行，把同一回单的并发补报串行化；不同回单互不阻塞
    get(conn, cue_routing, data.routing, lock=True)
    template = _template_timings(conn, data.routing)
    beats = [x.model_dump() for x in data.beats]

    state = (_ordered(conn, play_segments, data.routing),
             _ordered(conn, segment_conflicts, data.routing),
             _ordered(conn, segment_reminders, data.routing))
    try:
        events, result = apply_report(*state, routing=data.routing, segment=data.segment,
                                      code=data.code, beats=beats, template=template)
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc))

    for event in events:
        kind = event[0]
        if kind == 'insert_segment':
            insert(conn, play_segments, **event[1])
        elif kind == 'insert_conflict':
            insert(conn, segment_conflicts, **event[1])
        elif kind == 'insert_reminder':
            insert(conn, segment_reminders, **event[1])
        elif kind == 'confirm_segment':
            _, seg_code, judged = event
            conn.execute(play_segments.update().where(play_segments.c.code == seg_code).values(
                status='已确认', verdict=judged['verdict'], shift=judged['shift'],
                drift=judged['drift']))
    return result


def list_segments(conn):
    return [dict(row) for row in conn.execute(
        select(play_segments).order_by(play_segments.c.routing, play_segments.c.segment)).mappings()]


def list_conflicts(conn):
    return [dict(row) for row in conn.execute(
        select(segment_conflicts).order_by(segment_conflicts.c.routing,
                                           segment_conflicts.c.segment, segment_conflicts.c.id)
    ).mappings()]


def list_reminders(conn):
    return [dict(row) for row in conn.execute(
        select(segment_reminders).order_by(segment_reminders.c.routing,
                                           segment_reminders.c.segment)).mappings()]
