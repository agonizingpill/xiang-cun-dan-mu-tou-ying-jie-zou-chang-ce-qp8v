"""实播段补报纯逻辑的离线核验（仅标准库，python3 -I 运行）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.play_segment_logic import (  # noqa: E402
    apply_report, judge, validate_beats, CONFIRMED, PENDING, MATCH, LAGGED, DRIFTED)

TEMPLATE = [0.65, 1.3, 1.95, 2.6, 3.25, 3.9]
ROUTING = 'ROUTE-30'
checks = 0


def check(condition, label):
    global checks
    assert condition, label
    checks += 1


def raises(fn, fragment):
    try:
        fn()
    except ValueError as exc:
        check(fragment in str(exc), f'错误信息包含 {fragment}: {exc}')
        return
    raise AssertionError(f'应抛出包含 {fragment} 的 ValueError')


def new_state():
    return [], [], []


def run(state, segment, code, beats, routing=ROUTING, template=TEMPLATE):
    segments, conflicts, reminders = state
    events, result = apply_report(segments, conflicts, reminders, routing=routing,
                                  segment=segment, code=code, beats=beats, template=template)
    for event in events:
        kind = event[0]
        if kind == 'insert_segment':
            segments.append(event[1])
        elif kind == 'insert_conflict':
            conflicts.append(event[1])
        elif kind == 'insert_reminder':
            reminders.append(event[1])
        elif kind == 'confirm_segment':
            seg = next(s for s in segments if s['code'] == event[1])
            seg['status'] = CONFIRMED
            seg.update(event[2])
    segments.sort(key=lambda s: s['segment'])
    return events, result


def b(*pairs):
    return [{'beat': x, 'time': t} for x, t in pairs]


# ---- judge：三种判定与容差边界 ----
check(judge(TEMPLATE, b((1, 0.65), (2, 1.3)))['verdict'] == MATCH, '完全吻合判吻合')
edge = judge(TEMPLATE, b((1, 0.85), (2, 1.5)))  # 各拍恰 +0.20，容差边界
check(edge['verdict'] == MATCH and edge['shift'] == 0.2, '偏差 0.2 边界仍判吻合')
lag = judge(TEMPLATE, b((1, 1.15), (2, 1.8), (3, 2.45)))  # 整体 +0.5
check(lag['verdict'] == LAGGED and lag['shift'] == 0.5 and lag['drift'] == 0.0,
      '整体平移判整体延迟')
walk = judge(TEMPLATE, b((1, 0.65), (2, 1.6), (3, 2.55)))  # 偏差 0/0.3/0.6
check(walk['verdict'] == DRIFTED and walk['drift'] == 0.6, '残差发散判逐拍走偏')

# ---- 校验 ----
raises(lambda: validate_beats([], len(TEMPLATE)), '至少')
raises(lambda: validate_beats(b((7, 1.0)), len(TEMPLATE)), '超出')
raises(lambda: validate_beats(b((1, 200.0)), len(TEMPLATE)), '0 到 180')
raises(lambda: validate_beats(b((2, 1.0), (1, 2.0)), len(TEMPLATE)), '严格递增')
raises(lambda: validate_beats(b((1, 2.0), (2, 1.0)), len(TEMPLATE)), '实播时间')

# ---- 顺序补报：吻合段直接确认且无提醒 ----
state = new_state()
events, r1 = run(state, 1, 'SEG-001', b((1, 0.65), (2, 1.3), (3, 1.95)))
check(r1['outcome'] == 'accepted' and r1['status'] == CONFIRMED and r1['verdict'] == MATCH,
      '首段吻合即确认')
check(r1['waiting'] is None and not any(e[0] == 'insert_reminder' for e in events),
      '吻合不产生提醒')
check(len(events) == 2 and events[0][0] == 'insert_segment' and events[1][0] == 'confirm_segment',
      '事件为插入段+确认')

# ---- 乱序：先到的段挂起，前序连上后随到随判 ----
state = new_state()
_, r3 = run(state, 3, 'SEG-003', b((6, 4.1)))
check(r3['status'] == PENDING and r3['waiting'] == 1, '缺段时先到段挂起并指向段 1')
check(state[0][0]['status'] == PENDING, '挂起段保持待连接')
_, r1 = run(state, 1, 'SEG-001', b((1, 0.65), (2, 1.3), (3, 1.95)))
check(r1['status'] == CONFIRMED and r1['waiting'] == 2, '段 1 连接后等待段 2，段 3 仍挂起')
_, r2 = run(state, 2, 'SEG-002', b((4, 2.6), (5, 3.25)))
check(r2['status'] == CONFIRMED and r2['waiting'] is None, '前序补齐后连接推进')
check([x['segment'] for x in r2['confirmed']] == [2, 3], '段 2、3 随到随判且按序')
check(all(s['status'] == CONFIRMED for s in state[0]), '挂起段已补判确认')

# ---- 接续编号断档：必须从上段确认拍点往后接 ----
state = new_state()
run(state, 1, 'SEG-001', b((1, 0.65), (2, 1.3), (3, 1.95)))
_, gap = run(state, 2, 'SEG-002', b((5, 3.25), (6, 3.9)))  # 跳过拍 4
check(gap['status'] == PENDING and gap['waiting'] == 2, '编号断档保持挂起等段 2 修正')

# ---- 整体延迟产生提醒，且保留样板与实播两组拍点 ----
state = new_state()
events, r = run(state, 1, 'SEG-010', b((1, 1.15), (2, 1.8), (3, 2.45)))
check(r['verdict'] == LAGGED, '整体延迟判定')
reminder_events = [e for e in events if e[0] == 'insert_reminder']
check(len(reminder_events) == 1, '非吻合段发出一条提醒')
rm = reminder_events[0][1]
check(rm['code'] == 'RM-ROUTE-30-S001' and rm['verdict'] == LAGGED, '提醒编号与判定')
check([x['time'] for x in rm['template_beats']] == [0.65, 1.3, 1.95], '提醒含样板拍点')
check([x['time'] for x in rm['play_beats']] == [1.15, 1.8, 2.45], '提醒含实播拍点')
check([x['beat'] for x in rm['template_beats']] == [x['beat'] for x in rm['play_beats']],
      '两组拍点按同一拍号对齐')

# ---- 逐拍走偏同样留提醒 ----
state = new_state()
_, r = run(state, 1, 'SEG-011', b((1, 0.65), (2, 1.6), (3, 2.55)))
check(r['verdict'] == DRIFTED and len(state[2]) == 1, '逐拍走偏留一条提醒')

# ---- 同段并发：同稿只采纳一份 ----
state = new_state()
beats_a = b((1, 0.65), (2, 1.3))
run(state, 1, 'SEG-001', beats_a)
events, dup = run(state, 1, 'SEG-001DUP', beats_a)
check(dup['outcome'] == 'duplicate' and events == [], '同稿并发不重复写入')
check(len(state[0]) == 1, '仍只有一份段记录')

# ---- 异稿留作冲突，且同异稿凭证不重复登记 ----
state = new_state()
run(state, 1, 'SEG-001', beats_a)
events, conflict = run(state, 1, 'SEG-001X', b((1, 0.7), (2, 1.4)))
check(conflict['outcome'] == 'conflict' and len(events) == 1
      and events[0][0] == 'insert_conflict', '异稿登记为冲突')
check(state[0][0]['code'] == 'SEG-001', '首份照旧采纳')
events2, conflict2 = run(state, 1, 'SEG-001X', b((1, 0.7), (2, 1.4)))
check(conflict2['outcome'] == 'conflict' and events2 == [], '同一异稿凭证不重复留痕')
check(len(state[1]) == 1, '冲突表只有一条异稿')

# ---- 已发提醒照旧：提醒已存在时不重复发 ----
state = new_state()
state[0].append({'code': 'SEG-001', 'routing': ROUTING, 'segment': 1,
                 'beats': b((1, 1.15), (2, 1.8)), 'status': PENDING,
                 'verdict': None, 'shift': None, 'drift': None})
state[2].append({'code': 'RM-ROUTE-30-S001', 'routing': ROUTING, 'segment': 1,
                 'verdict': LAGGED, 'shift': 0.5, 'drift': 0.0,
                 'template_beats': [], 'play_beats': []})
events, _ = run(state, 2, 'SEG-002', b((3, 2.45), (4, 3.1)))
new_reminders = [e[1] for e in events if e[0] == 'insert_reminder']
check(all(rm['segment'] != 1 for rm in new_reminders), '段 1 已有提醒不重复发')
check(len(new_reminders) == 1 and new_reminders[0]['segment'] == 2, '段 2 作为新段照常发提醒')
check(any(e[0] == 'confirm_segment' for e in events), '段照常连接判定')

# ---- 段号合法性 ----
state = new_state()
raises(lambda: run(state, 0, 'SEG-X', b((1, 0.65))), '段号')

print(f'全部 {checks} 项核验通过')
