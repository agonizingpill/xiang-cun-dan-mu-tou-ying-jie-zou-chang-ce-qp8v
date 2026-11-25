        import {workspace} from '../workspace.js';
        import {request} from '../api.js';
        import {el} from '../dom.js';
        import {dataView, status} from '../widgets.js';

        const page = {
  "title": "对场合用与分路提示",
  "module": "交场分路回单",
  "caption": "交场分路回单",
  "detail": "同协议的签验场地可合用。异协议要留下一条本场分路提醒。",
  "path": "/cue_routing",
  "columns": [
    {
      "name": "code",
      "label": "编号"
    },
    {
      "name": "cluster",
      "label": "节奏簇"
    },
    {
      "name": "destination",
      "label": "目标场地"
    },
    {
      "name": "route",
      "label": "物理分路"
    },
    {
      "name": "status",
      "label": "交场状态"
    }
  ],
  "layout": "flip",
  "view": "stack",
  "actions": [
    {
      "name": "share_cue",
      "label": "签回跨场合用",
      "path": "/cue_routing/share-cue",
      "fields": [
        {
          "name": "code",
          "label": "分路回单",
          "kind": "text",
          "initial": "ROUTE-24"
        },
        {
          "name": "cluster",
          "label": "节奏簇",
          "kind": "text",
          "initial": "BEAT-24"
        },
        {
          "name": "destination",
          "label": "目的场地",
          "kind": "text",
          "initial": "HALL-C"
        },
        {
          "name": "route",
          "label": "分路",
          "kind": "text",
          "initial": "C-1"
        }
      ],
      "help": "签认前核对不同场地的计量协议。",
      "roles": [
        "reviewer"
      ],
      "success": "已写入"
    },
    {
      "name": "record_separate",
      "label": "记录异协议分路提示",
      "path": "/cue_routing/record-separate",
      "fields": [
        {
          "name": "code",
          "label": "提醒编号",
          "kind": "text",
          "initial": "ROUTE-25"
        },
        {
          "name": "cluster",
          "label": "节奏簇",
          "kind": "text",
          "initial": "BEAT-24"
        },
        {
          "name": "destination",
          "label": "目的场地",
          "kind": "text",
          "initial": "HALL-B"
        },
        {
          "name": "route",
          "label": "本地替代分路",
          "kind": "text",
          "initial": "B-2"
        }
      ],
      "help": "保存本场分路编号给当地值守。",
      "roles": [
        "operator",
        "reviewer"
      ],
      "success": "已写入"
    }
  ]
};

        export const {title} = page;
        export const key = "cue_routing";

        const SEGMENT_COLUMNS = [
          {name: 'routing', label: '交场回单'},
          {name: 'segment', label: '段号'},
          {name: 'beats', label: '带编号拍点'},
          {name: 'status', label: '连接状态'},
          {name: 'verdict', label: '判定'},
          {name: 'shift', label: '整体延迟秒'},
          {name: 'drift', label: '逐拍走偏秒'}
        ];
        const REMINDER_COLUMNS = [
          {name: 'code', label: '提醒编号'},
          {name: 'routing', label: '交场回单'},
          {name: 'segment', label: '段号'},
          {name: 'verdict', label: '判定'},
          {name: 'shift', label: '整体延迟秒'},
          {name: 'drift', label: '走偏极差秒'},
          {name: 'template', label: '样板拍点'},
          {name: 'play', label: '实播拍点'}
        ];
        const CONFLICT_COLUMNS = [
          {name: 'routing', label: '交场回单'},
          {name: 'segment', label: '段号'},
          {name: 'code', label: '异稿凭证'},
          {name: 'beats', label: '异稿拍点'}
        ];

        const fmtBeats = beats => beats.map(b => `#${b.beat} ${b.time}s`).join('，');
        const segmentRows = rows => rows.map(r => ({...r, beats: fmtBeats(r.beats)}));
        const reminderRows = rows => rows.map(r => ({
          code: r.code, routing: r.routing, segment: r.segment, verdict: r.verdict,
          shift: r.shift, drift: r.drift,
          template: fmtBeats(r.template_beats), play: fmtBeats(r.play_beats)
        }));
        const conflictRows = rows => rows.map(r => ({...r, beats: fmtBeats(r.beats)}));

        function ledgerCard(heading, rows, columns) {
          return el('section', {class: 'ledger'}, el('h2', {}, heading), dataView(rows, columns, 'table'));
        }

        function field(label, inputNode) {
          return el('label', {}, el('span', {}, label), inputNode);
        }

        function reportCard(refresh, canWrite) {
          const notice = status('');
          const routing = el('input', {name: 'routing', required: '', type: 'text', value: 'ROUTE-30'});
          const segment = el('input', {name: 'segment', required: '', type: 'number', value: '1'});
          const code = el('input', {name: 'code', required: '', type: 'text', value: 'SEG-100'});
          const beats = el('textarea', {name: 'beats', required: ''});
          beats.value = JSON.stringify([{beat: 1, time: 0.65}, {beat: 2, time: 1.3}, {beat: 3, time: 1.95}], null, 2);
          const button = el('button', {type: 'submit'}, '补报本段');
          const form = el('form', {class: 'action', id: 'report_segment'},
            el('h3', {}, '按回单补报带编号拍点'),
            el('p', {}, '乱序实播记录按回单与段号补报。缺段先挂起，前序连上后本段随到随判；同段并发同稿只采纳一份，异稿登记为冲突。'),
            el('div', {class: 'fields'},
              field('交场回单', routing), field('段号', segment), field('本段凭证号', code)),
            field('带编号拍点（beat 为样板拍号，time 为实播秒）', beats),
            button, notice);
          form.addEventListener('submit', async event => {
            event.preventDefault();
            button.disabled = true;
            notice.className = 'status';
            try {
              const data = await request('/play_segments/report-segment', {
                routing: routing.value.trim(), segment: Number(segment.value),
                code: code.value.trim(), beats: JSON.parse(beats.value)
              });
              const judged = (data.confirmed || []).map(x => `S${x.segment} ${x.verdict}`).join('，');
              notice.textContent = data.note + (judged ? `（${judged}）` : '');
              notice.classList.add('ok');
              await refresh();
            } catch (error) {
              notice.textContent = error.message;
              notice.classList.add('error');
            } finally { button.disabled = false; }
          });
          return canWrite ? form : null;
        }

        export async function render(root, role) {
          await workspace(root, role, page);

          const segmentsSlot = el('div', {});
          const remindersSlot = el('div', {});
          const conflictsSlot = el('div', {});
          const boardNotice = status('');

          const refresh = async () => {
            try {
              const [segments, reminders, conflicts] = await Promise.all([
                request('/play_segments'), request('/segment_reminders'), request('/segment_conflicts')
              ]);
              segmentsSlot.replaceChildren(
                ledgerCard('实播段台账（缺段先等，连上随判）', segmentRows(segments), SEGMENT_COLUMNS));
              remindersSlot.replaceChildren(
                ledgerCard('段提醒（每条保留样板与实播两组拍点）', reminderRows(reminders), REMINDER_COLUMNS));
              conflictsSlot.replaceChildren(
                ledgerCard('异稿冲突（同段只采纳首份，异稿留痕）', conflictRows(conflicts), CONFLICT_COLUMNS));
              boardNotice.textContent = '';
            } catch (error) {
              boardNotice.textContent = error.message;
              boardNotice.className = 'status error';
            }
          };

          const canWrite = ['operator', 'reviewer'].includes(role);
          const board = el('div', {class: 'segment-board'},
            el('header', {class: 'title'},
              el('span', {class: 'kicker'}, '实播补报'),
              el('h1', {}, '乱序实播段补报与判定'),
              el('p', {class: 'intro'},
                '按交场回单补报带编号拍点，系统对齐签认样板：各拍偏差在容差内为吻合，整体平移为整体延迟，残差发散为逐拍走偏。')),
            el('div', {class: 'board-grid'}, segmentsSlot, reportCard(refresh, canWrite)),
            remindersSlot,
            conflictsSlot,
            el('div', {class: 'actions'},
              el('button', {class: 'quiet', onclick: refresh}, '刷新补报台账')),
            boardNotice);
          root.append(board);
          await refresh();
        }
