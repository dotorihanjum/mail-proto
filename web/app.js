'use strict';

const $ = (s) => document.querySelector(s);
const SRC = () => $('#source').value;
const esc = (s) => String(s ?? '').replace(/[&<>"]/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

let VIEW = null;

// ── "안 본 메일" 표시 ────────────────────────────────────────────
// 이 브라우저에서 아직 펼쳐 보지 않은 메일을 NEW 로 띄운다.
// localStorage 라서 이 브라우저에만 남는다. 지워져도 화면은 정상 동작한다.
let SEEN = new Set();
let FIRST_TIME = false;

function seenKey() { return `seen:${SRC()}`; }

function loadSeen() {
  try {
    const raw = localStorage.getItem(seenKey());
    FIRST_TIME = raw === null;
    SEEN = new Set(raw ? JSON.parse(raw) : []);
  } catch (e) { FIRST_TIME = false; SEEN = new Set(); }
}

function saveSeen() {
  try { localStorage.setItem(seenKey(), JSON.stringify([...SEEN])); } catch (e) {}
}

// 항목이 어떤 메일에서 왔는지 (중복 병합된 것은 여러 개)
function idsOf(x) {
  if (x.sources && x.sources.length) return x.sources.map((s) => s.email_id);
  return x.email_id ? [x.email_id] : [];
}

function isNew(x) {
  if (FIRST_TIME) return false;   // 처음 여는 브라우저라면 전부 NEW 로 뜨면 곤란하다
  return idsOf(x).some((id) => !SEEN.has(id));
}

function newTag(x) {
  return isNew(x) ? '<span class="new-badge">NEW</span>' : '';
}

function markSeen(list) {
  list.forEach((x) => idsOf(x).forEach((id) => SEEN.add(id)));
  saveSeen();
}

// ── 공통 ──────────────────────────────────────────────────────────
function say(msg, isErr) {
  const el = $('#status');
  el.textContent = msg;
  el.className = 'status' + (isErr ? ' err' : '');
  el.classList.remove('hidden');
}
function clearSay() { $('#status').classList.add('hidden'); }

function ddayText(d) {
  if (d === null || d === undefined) return '마감 미정';
  if (d === 0) return 'D-DAY';
  return d > 0 ? `D-${d}` : `${-d}일 지남`;
}

function deadlineText(it) {
  if (!it.deadline_iso) return '마감 미정';
  const s = it.deadline_iso.replace('T', ' ');
  return it.time_specified === false ? `${s} (시각 미기재)` : s;
}

// ── 그리기 ────────────────────────────────────────────────────────
function card(it) {
  return `<div class="card p${it.priority}">
    <div class="dday p${it.priority}">${ddayText(it.dday)} · ${esc(it.priority_text)}</div>
    <div class="title">${newTag(it)}${esc(it.title)}</div>
    <div class="meta">${esc(deadlineText(it))}</div>
    <div class="meta">원문 표현: ${esc(it.deadline_text || '—')}</div>
    <div class="evidence">${esc(it.evidence)}</div>
    <div class="src">${esc(it.account)} · ${esc(it.subject)}
      <button class="link" data-email="${esc(it.email_id)}">원문 보기</button></div>
  </div>`;
}

function row(it, kind) {
  const tags = [];
  if (it.is_merged) tags.push(`<span class="tag merge">여러 계정에서 온 같은 공지</span>`);
  (it.review_text || []).forEach((t) => tags.push(`<span class="tag rev">${esc(t)}</span>`));
  if (it.deadline_ai && it.deadline_rule && it.deadline_ai !== it.deadline_rule) {
    tags.push(`<span class="tag warn">AI는 ${esc(it.deadline_ai)}로 봄</span>`);
  }

  const srcs = (it.sources || []).map((s) =>
    `${esc(s.account)} · ${esc(s.subject)}
     <button class="link" data-email="${esc(s.email_id)}">원문 보기</button>`).join('<br>');

  const cls = ['row', kind, it.status === 'done' ? 'done' : ''].filter(Boolean).join(' ');
  return `<div class="${cls}">
    <input type="checkbox" ${it.status === 'done' ? 'checked' : ''}
           data-key='${esc(JSON.stringify(it.member_keys))}'
           data-title="${esc(it.title)}"
           data-deadline="${esc((it.deadline_iso || '').slice(0, 10))}">
    <div class="grow">
      <div class="title">${newTag(it)}${esc(it.title)}</div>
      <div class="meta">${esc(deadlineText(it))} · 원문 표현: ${esc(it.deadline_text || '—')}</div>
      <div>${tags.join('')}</div>
      <div class="evidence">${esc(it.evidence)}</div>
      <div class="src">${srcs}</div>
    </div>
    <div class="dday p${it.priority}">${it.deadline_iso ? ddayText(it.dday) : '기한 없음'}</div>
  </div>`;
}

function render() {
  const v = VIEW;
  $('#today').textContent = `기준일 ${v.today}`;
  $('#model').textContent = v.model;
  $('#counts').innerHTML = Object.entries(v.counts)
    .map(([k, n]) => `${k} <b>${n}</b>`).join(' · ');

  const put = (id, arr, kind, emptyMsg) => {
    $(id).innerHTML = arr.length
      ? arr.map((it) => row(it, kind)).join('')
      : `<div class="empty">${emptyMsg}</div>`;
  };
  $('#today-top').innerHTML = v.today_top.length
    ? v.today_top.map(card).join('')
    : `<div class="empty">지금 급한 할 일이 없습니다.</div>`;
  put('#review', v.needs_review, 'rev', '확인이 필요한 항목이 없습니다.');
  put('#upcoming', v.upcoming, '', '다가오는 마감이 없습니다.');
  put('#anytime', v.anytime || [], 'anytime', '기한 없는 할 일이 없습니다.');
  put('#overdue', v.overdue, 'over', '지난 마감이 없습니다.');

  $('#verification').innerHTML = (v.verification || []).map((r) => `<div class="row verif">
      <div class="grow"><div class="title">${newTag(r)}${esc(r.subject)}</div>
      <div class="meta">${esc(r.account)} · ${esc(r.received_at)}</div>
      <div class="meta">${esc(r.summary)}</div>
      <div><button class="link" data-email="${esc(r.email_id)}">원문에서 코드 확인</button></div>
      </div></div>`).join('') || '<div class="empty">인증 메일이 없습니다.</div>';

  $('#reference').innerHTML = v.reference.map((r) => `<div class="row">
      <div class="grow"><div class="title">${esc(r.subject)}</div>
      <div class="meta">${esc(r.account)} · ${esc(r.received_at)} · ${esc(r.category)}</div>
      <div class="meta">${esc(r.summary)}</div>
      ${r.injection ? '<span class="tag warn">본문에 AI 대상 지시 문구가 있었습니다 (따르지 않음)</span>' : ''}
      <div><button class="link" data-email="${esc(r.email_id)}">원문 보기</button></div>
      </div></div>`).join('') || '<div class="empty">참고용 메일이 없습니다.</div>';

  $('#failed').innerHTML = v.failed.map((f) => `<div class="row">
      <div class="grow"><div class="title">${esc(f.subject)}</div>
      <div class="meta">정리 실패(${esc(f.fail_kind)}) — ${esc(f.error_message)}</div>
      <div><button class="link" data-email="${esc(f.email_id)}">직접 확인하기</button></div>
      </div></div>`).join('') || '<div class="empty">정리에 실패한 메일이 없습니다.</div>';

  // 섹션별 개수와 NEW 배지.
  // 참고용·정리 실패는 NEW 를 띄우지 않는다 (알림 가치가 없다).
  const sections = {
    today: v.today_top,
    review: v.needs_review,
    upcoming: v.upcoming,
    anytime: v.anytime || [],
    verification: v.verification || [],
    overdue: v.overdue,
    reference: v.reference,
    failed: v.failed,
  };
  const noNew = new Set(['reference', 'failed']);

  Object.entries(sections).forEach(([key, arr]) => {
    const c = document.querySelector(`[data-count="${key}"]`);
    if (c) c.textContent = arr.length;
    const badge = document.querySelector(`[data-new="${key}"]`);
    if (!badge) return;
    const n = noNew.has(key) ? 0 : arr.filter(isNew).length;
    badge.textContent = n > 1 ? `NEW ${n}` : 'NEW';
    badge.classList.toggle('hidden', n === 0);
  });

  // 펼쳐 둔 섹션의 항목은 본 것으로 친다.
  // 지금 화면의 배지는 그대로 두고, 다음에 열 때 사라진다.
  document.querySelectorAll('details.sec[open]').forEach((d) => {
    if (!noNew.has(d.dataset.sec)) markSectionSeen(d.dataset.sec);
  });

  // 처음 여는 브라우저면 지금 것을 전부 본 것으로 기록해 둔다
  if (FIRST_TIME) {
    Object.entries(sections).forEach(([k, arr]) => {
      if (!noNew.has(k)) markSeen(arr);
    });
    FIRST_TIME = false;
  }
}

// ── 섹션 접기/펼치기 ─────────────────────────────────────────────
// 화면을 열 때는 언제나 '오늘 할 일'만 펼쳐 둔다.
// 접어 둔 상태를 기억하면, 지난번에 펼쳐 둔 섹션 때문에
// 새 메일이 와도 NEW 가 바로 지워져 버린다.
function resetOpen() {
  document.querySelectorAll('details.sec').forEach((d) => {
    d.open = d.dataset.sec === 'today';
  });
}

// 펼치면 그 섹션을 본 것으로 기록한다.
// 여기서 다시 그리지 않는다. 다시 그리면 이미 펼친 다른 섹션의
// NEW 배지가 그 자리에서 사라져 버린다.
function markSectionSeen(key) {
  if (!VIEW) return;
  const map = {
    today: VIEW.today_top, review: VIEW.needs_review, upcoming: VIEW.upcoming,
    anytime: VIEW.anytime || [], verification: VIEW.verification || [],
    overdue: VIEW.overdue,
  };
  if (map[key]) markSeen(map[key]);
}

document.querySelectorAll('details.sec').forEach((d) => {
  d.addEventListener('toggle', () => {
    if (d.open) markSectionSeen(d.dataset.sec);
  });
});

$('#btn-checknew').addEventListener('click', () => {
  const targets = [...document.querySelectorAll('[data-new]')]
    .filter((b) => !b.classList.contains('hidden'))
    .map((b) => b.closest('details.sec'))
    .filter(Boolean);

  if (!targets.length) {
    say('새 메일이 없습니다.');
    return;
  }
  targets.forEach((d) => { d.open = true; });
  targets[0].scrollIntoView({ behavior: 'smooth', block: 'start' });
  const names = targets
    .map((d) => d.querySelector('.stitle').textContent).join(', ');
  say(`새 메일이 있는 분류를 펼쳤습니다 — ${names}`);
});

// ── 서버 통신 ─────────────────────────────────────────────────────
async function load() {
  const r = await fetch(`/api/view?source=${SRC()}`);
  const v = await r.json();
  if (!v.ready) {
    say('아직 정리된 결과가 없습니다. [AI로 정리] 를 눌러주세요.');
    return;
  }
  VIEW = v;
  loadSeen();   // 데이터를 바꿀 때마다 그 소스의 '본 목록'을 읽는다
  resetOpen();  // 언제나 '오늘 할 일'만 펼친 상태로 시작한다
  clearSay();
  render();
}

async function runExtract() {
  const btn = $('#btn-extract');
  btn.disabled = true;
  say('AI로 정리하는 중입니다… 캐시가 없으면 1분 정도 걸립니다.');
  try {
    const r = await fetch(`/api/extract?source=${SRC()}`, { method: 'POST' });
    if (!r.ok) throw new Error((await r.json()).detail || '서버 오류');
    const d = await r.json();
    await load();
    say(`정리 완료 — 메일 ${d.요약['메일']}통, 할 일 ${d.요약['항목']}개, ` +
        `확인 필요 ${d.요약['확인 필요']}개, 정리 실패 ${d.요약['정리 실패']}건 ` +
        (d['실제 호출'] === 0
          ? '(전부 캐시, 0원)'
          : `(새로 처리 ${d['실제 호출']}건, ${d.비용원}원)`));
  } catch (e) {
    say(`정리에 실패했습니다: ${e.message}`, true);
  } finally {
    btn.disabled = false;
  }
}

async function toggle(cb) {
  const targets = JSON.parse(cb.dataset.key);
  const status = cb.checked ? 'done' : 'open';
  cb.closest('.row').classList.toggle('done', cb.checked);
  try {
    const r = await fetch('/api/status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ targets, status, title: cb.dataset.title,
                             deadline_date: cb.dataset.deadline || null }),
    });
    if (!r.ok) throw new Error('저장 실패');
  } catch (e) {
    cb.checked = !cb.checked;
    cb.closest('.row').classList.toggle('done', cb.checked);
    say('완료 상태를 저장하지 못했습니다.', true);
  }
}

// ── 원문 보기 ─────────────────────────────────────────────────────
let DETAIL = null;

async function openEmail(id) {
  const r = await fetch(`/api/email/${id}?source=${SRC()}`);
  if (!r.ok) { say('원문을 불러오지 못했습니다.', true); return; }
  DETAIL = await r.json();
  $('#m-subject').textContent = DETAIL.subject;
  $('#m-meta').innerHTML =
    `${esc(DETAIL.account)} · ${esc(DETAIL.sender)} · ${esc(DETAIL.received_at.slice(0, 10))}` +
    (DETAIL.attachment_names.length ? ` · 첨부: ${esc(DETAIL.attachment_names.join(', '))}` : '') +
    (DETAIL.masked_kinds.length
      ? `<br><span class="tag warn">AI에 보내기 전 가림: ${esc(DETAIL.masked_kinds.join(', '))}</span>` : '');
  showTab('raw');
  $('#modal').classList.remove('hidden');
}

function showTab(which) {
  document.querySelectorAll('.tab').forEach((t) =>
    t.classList.toggle('active', t.dataset.tab === which));
  const body = which === 'raw' ? DETAIL.body_raw : DETAIL.body_masked;
  // 근거 문장이 어디인지 표시한다
  const evid = (VIEW ? [...VIEW.today_top, ...VIEW.needs_review, ...VIEW.upcoming, ...VIEW.overdue] : [])
    .flatMap((it) => (it.sources || []).filter((s) => s.email_id === DETAIL.email_id))
    .map((s) => s.evidence).filter(Boolean);
  let html = esc(body);
  evid.forEach((e) => {
    const t = esc(e).trim();
    if (t && html.includes(t)) html = html.split(t).join(`<mark>${t}</mark>`);
  });
  $('#m-body').innerHTML = html;
}

// ── 이벤트 ────────────────────────────────────────────────────────
document.addEventListener('click', (ev) => {
  const link = ev.target.closest('[data-email]');
  if (link) { openEmail(link.dataset.email); return; }
  const tab = ev.target.closest('.tab');
  if (tab && DETAIL) { showTab(tab.dataset.tab); return; }
  if (ev.target.id === 'm-close' || ev.target.id === 'modal') {
    $('#modal').classList.add('hidden');
  }
});
document.addEventListener('change', (ev) => {
  if (ev.target.matches('input[type=checkbox][data-key]')) toggle(ev.target);
});
$('#btn-extract').addEventListener('click', runExtract);
$('#btn-fetch').addEventListener('click', async () => {
  const btn = $('#btn-fetch');
  btn.disabled = true;
  say(SRC() === 'imap'
    ? '메일을 가져오는 중입니다… 읽음 표시는 건드리지 않습니다.'
    : '샘플을 불러오는 중입니다…');
  try {
    const r = await fetch(`/api/fetch?source=${SRC()}`, { method: 'POST' });
    if (!r.ok) throw new Error((await r.json()).detail || '서버 오류');
    const d = await r.json();
    await load();
    say(d['새 메일'] > 0
      ? `${d['말']} [AI로 정리] 를 누르면 새 메일만 처리합니다.`
      : d['말']);
  } catch (e) {
    say(`메일을 가져오지 못했습니다: ${e.message}`, true);
  } finally {
    btn.disabled = false;
  }
});
$('#source').addEventListener('change', (ev) => {
  load();
  showWatchUi(ev.target.value === 'imap');
  const n = $('#notice');
  if (ev.target.value === 'imap') {
    n.innerHTML = '주의: 메일 내용이 AI 서비스(Anthropic)로 전송됩니다. ' +
      '<label><input type="checkbox" id="agree"> 이해했고 동의합니다</label>';
    n.classList.remove('hidden');
  } else n.classList.add('hidden');
});


// ── 새 메일 실시간 감시 (IMAP IDLE) ─────────────────────────────
let watchTimer = null;

function showWatchUi(on) {
  $('#watch-wrap').classList.toggle('hidden', !on);
  $('#watch-state').classList.toggle('hidden', !on);
  if (!on) {
    $('#newmail').classList.add('hidden');
    if (watchTimer) { clearInterval(watchTimer); watchTimer = null; }
  }
}

async function pollWatch() {
  try {
    const s = await (await fetch('/api/watch/status')).json();
    $('#watch-state').textContent = `감시: ${s['상태']}`;
    const box = $('#newmail');
    if ((s['새 메일 신호'] || 0) > 0) {
      box.textContent = '새 메일이 도착했습니다. ';
      const b = document.createElement('button');
      b.textContent = '지금 가져오기';
      b.onclick = () => $('#btn-fetch').click();
      box.appendChild(b);
      box.classList.remove('hidden');
    } else {
      box.classList.add('hidden');
    }
  } catch (e) { /* 서버가 잠깐 응답하지 않을 수 있다 */ }
}

$('#watch').addEventListener('change', async (ev) => {
  if (ev.target.checked) {
    const s = await (await fetch('/api/watch/start', { method: 'POST' })).json();
    if (!s['켜짐']) {
      say(`감시를 켜지 못했습니다: ${s['상태']}`, true);
      ev.target.checked = false;
      return;
    }
    say('새 메일 감시를 켰습니다. 메일 서버가 알려주면 바로 표시합니다.');
    pollWatch();
    watchTimer = setInterval(pollWatch, 10000);
  } else {
    await fetch('/api/watch/stop', { method: 'POST' });
    if (watchTimer) { clearInterval(watchTimer); watchTimer = null; }
    $('#watch-state').textContent = '감시: 꺼짐';
    $('#newmail').classList.add('hidden');
  }
});

load();
