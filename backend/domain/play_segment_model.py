from sqlalchemy import Boolean, CheckConstraint, Column, Float, ForeignKey, Integer, JSON, String, Table, UniqueConstraint

from core.db import metadata


# 交场回单下按序补报的实播段：一段携带带编号的拍点，缺段先挂起，连上样板后随到随判
play_segments = Table('play_segments', metadata,
    Column('code', String(64), primary_key=True),
    Column('routing', String(64), ForeignKey('cue_routing.code'), nullable=False),
    Column('segment', Integer, nullable=False),
    Column('beats', JSON, nullable=False),
    Column('status', String(32), nullable=False),
    Column('verdict', String(32), nullable=True),
    Column('shift', Float, nullable=True),
    Column('drift', Float, nullable=True),
    UniqueConstraint('routing', 'segment', name='uq_play_segment_order'),
    CheckConstraint("status in ('待连接','已确认')", name='ck_play_segment_status'),
    CheckConstraint("verdict is null or verdict in ('吻合','整体延迟','逐拍走偏')",
                    name='ck_play_segment_verdict'),
)


# 同一段并发/再次上报且拍点异稿时留痕，只采纳第一份
segment_conflicts = Table('segment_conflicts', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('routing', String(64), ForeignKey('cue_routing.code'), nullable=False),
    Column('segment', Integer, nullable=False),
    Column('code', String(64), nullable=False),
    Column('beats', JSON, nullable=False),
    UniqueConstraint('routing', 'segment', 'code', name='uq_segment_conflict_draft'),
)


# 已发提醒照旧：每条提醒保留样板与实播两组拍点，供值守回查
segment_reminders = Table('segment_reminders', metadata,
    Column('code', String(64), primary_key=True),
    Column('routing', String(64), ForeignKey('cue_routing.code'), nullable=False),
    Column('segment', Integer, nullable=False),
    Column('verdict', String(32), nullable=False),
    Column('shift', Float, nullable=True),
    Column('drift', Float, nullable=True),
    Column('template_beats', JSON, nullable=False),
    Column('play_beats', JSON, nullable=False),
    UniqueConstraint('routing', 'segment', name='uq_segment_reminder'),
)
