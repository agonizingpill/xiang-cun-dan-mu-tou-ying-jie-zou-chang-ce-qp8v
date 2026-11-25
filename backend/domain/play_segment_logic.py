"""实播段补报的纯领域逻辑：不依赖数据库与 Web 框架，便于离线核验。"""
from statistics import median

# 单拍实播与样板的吻合容差（秒）：各拍偏差都在容差内即判吻合
BEAT_TOLERANCE = 0.2
# 各拍偏差减去整体平移后的残差极差上限（秒）：极差内视为整体延迟，超出即逐拍走偏
DRIFT_LIMIT = 0.2
# 与试投轨迹一致的实播时间范围（秒）
TIME_MIN, TIME_MAX = 0.0, 180.0

PENDING, CONFIRMED = '待连接', '已确认'
MATCH, LAGGED, DRIFTED = '吻合', '整体延迟', '逐拍走偏'


def validate_beats(beats, template_len):
    """段内自洽校验。接续编号在排水连接时按当时锚点另行核验。"""
    if not beats:
        raise ValueError('每段至少补报一个拍点')
    numbers = [x['beat'] for x in beats]
    if any(b < 1 for b in numbers):
        raise ValueError('拍号需从 1 起编')
    if any(a >= b for a, b in zip(numbers, numbers[1:])):
        raise ValueError('拍号需严格递增')
    if any(not (TIME_MIN <= x['time'] <= TIME_MAX) for x in beats):
        raise ValueError('实播时间需在 0 到 180 秒之间')
    times = [x['time'] for x in beats]
    if any(a >= b for a, b in zip(times, times[1:])):
        raise ValueError('实播时间需严格递增')
    if numbers[-1] > template_len:
        raise ValueError('拍号超出签认样板的拍点范围')


def judge(template, beats):
    """对齐签认样板：按拍号取样板时间，区分整体延迟与逐拍走偏。"""
    deltas = [x['time'] - template[x['beat'] - 1] for x in beats]
    shift = median(deltas)
    residuals = [d - shift for d in deltas]
    drift = max(residuals) - min(residuals)
    if all(abs(d) <= BEAT_TOLERANCE for d in deltas):
        verdict = MATCH
    elif drift <= DRIFT_LIMIT:
        verdict = LAGGED
    else:
        verdict = DRIFTED
    return {'verdict': verdict, 'shift': round(shift, 3), 'drift': round(drift, 3)}


def _reminder_code(routing, segment):
    return f'RM-{routing}-S{segment:03d}'


def _drain(working, reminders, routing, template, events):
    """缺段先等：从已确认段之后逐段连接，连上的段随到随判，直到遇到缺段或断档。"""
    judged = []
    while True:
        confirmed = [s for s in working if s['status'] == CONFIRMED]
        next_segment = confirmed[-1]['segment'] + 1 if confirmed else 1
        pending = next((s for s in working if s['status'] == PENDING
                        and s['segment'] == next_segment), None)
        if pending is None:
            waiting = next_segment if any(s['status'] == PENDING for s in working) else None
            return judged, waiting
        anchor = confirmed[-1]['beats'][-1]['beat'] if confirmed else 0
        # 每段从上段确认的样板拍点往后接，编号断档则保持挂起、等前序段补齐
        if pending['beats'][0]['beat'] != anchor + 1:
            return judged, next_segment
        result = judge(template, pending['beats'])
        if result['verdict'] != MATCH and not any(r['segment'] == pending['segment']
                                                   for r in reminders):
            events.append(('insert_reminder', {
                'code': _reminder_code(routing, pending['segment']), 'routing': routing,
                'segment': pending['segment'], 'verdict': result['verdict'],
                'shift': result['shift'], 'drift': result['drift'],
                'template_beats': [{'beat': x['beat'], 'time': template[x['beat'] - 1]}
                                   for x in pending['beats']],
                'play_beats': pending['beats']}))
        events.append(('confirm_segment', pending['code'], result))
        pending['status'] = CONFIRMED
        pending.update(result)
        judged.append({'segment': pending['segment'], **result})


def apply_report(segments, conflicts, reminders, *, routing, segment, code, beats, template):
    """在纯内存状态上处理一次补报，返回 (事件, 响应)。事件由持久化层落地。"""
    if segment < 1:
        raise ValueError('段号需从 1 起编')
    validate_beats(beats, len(template))
    events = []
    existing = next((s for s in segments if s['segment'] == segment), None)

    if existing is not None:
        common = {'code': existing['code'], 'routing': routing, 'segment': segment,
                  'status': existing['status'], 'verdict': existing['verdict'],
                  'shift': existing['shift'], 'drift': existing['drift'],
                  'confirmed': [], 'waiting': None}
        if existing['beats'] == beats:
            return events, {**common, 'outcome': 'duplicate',
                            'note': '同稿并发补报只采纳一份，未重复写入'}
        if not any(c['segment'] == segment and c['code'] == code for c in conflicts):
            events.append(('insert_conflict', {'routing': routing, 'segment': segment,
                                               'code': code, 'beats': beats}))
        return events, {**common, 'outcome': 'conflict',
                        'note': f"该段已采纳 {existing['code']}，异稿仅登记为冲突"}

    new_seg = {'code': code, 'routing': routing, 'segment': segment, 'beats': beats,
               'status': PENDING, 'verdict': None, 'shift': None, 'drift': None}
    events.append(('insert_segment', new_seg))
    working = segments + [new_seg]
    judged, waiting = _drain(working, reminders, routing, template, events)
    mine = next((x for x in judged if x['segment'] == segment), None)
    return events, {'code': code, 'routing': routing, 'segment': segment, 'outcome': 'accepted',
                    'status': CONFIRMED if mine else PENDING,
                    'verdict': mine and mine['verdict'], 'shift': mine and mine['shift'],
                    'drift': mine and mine['drift'], 'confirmed': judged, 'waiting': waiting,
                    'note': (f'缺段等待，下一个可连接段号为 {waiting}' if waiting is not None
                             else '本段已连接判定')}
