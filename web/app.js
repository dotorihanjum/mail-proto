'use strict';

const $ = (s) => document.querySelector(s);
const SRC = () => $('#source').value;
const esc = (s) => String(s ?? '').replace(/[&<>"]/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

let VIEW = null;

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
    <div class="title">${esc(it.title)}</div>
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
      <div class="title">${esc(it.title)}</div>
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

  $('#today-top').innerHTML = v.today_top.length
    ? v.today_top.map(card).join('')
    : `<div class="empty">지금 급한 할 일이 없습니다.</div>`;

  const put = (id, arr, kind, emptyMsg) => {
    $(id).innerHTML = arr.length
      ? arr.map((it) => row(it, kind)).join('')
      : `<div class="empty">${emptyMsg}</div>`;
  };
  put('#review', v.needs_review, 'rev', '확인이 필요한 항목이 없습니다.');
  put('#upcoming', v.upcoming, '', '다가오는 마감이 없습니다.');
  put('#anytime', v.anytime || [], 'anytime', '기한 없는 할 일이 없습니다.');
  put('#overdue', v.overdue, 'over', '지난 마감이 없습니다.');

  $('#n-review').textContent = v.counts['확인 필요'];
  $('#n-upcoming').textContent = v.upcoming.length;
  $('#n-anytime').textContent = (v.anytime || []).length;
  $('#n-verification').textContent = (v.verification || []).length;
  $('#n-overdue').textContent = v.counts['지남'];

  $('#verification').innerHTML = (v.verification || []).map((r) => `<div class="row verif">
      <div class="grow"><div class="title">${esc(r.subject)}</div>
      <div class="meta">${esc(r.account)} · ${esc(r.received_at)}</div>
      <div class="meta">${esc(r.summary)}</div>
      <div><button class="link" data-email="${esc(r.email_id)}">원문에서 코드 확인</button></div>
      </div></div>`).join('') || '<div class="empty">인증 메일이 없습니다.</div>';
  $('#n-reference').textContent = v.counts['참고용'];
  $('#n-failed').textContent = v.counts['정리 실패'];

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
}

// ── 서버 통신 ─────────────────────────────────────────────────────
async function load() {
  const r = await fetch(`/api/view?source=${SRC()}`);
  const v = await r.json();
  if (!v.ready) {
    say('아직 정리된 결과가 없습니다. [AI로 정리] 를 눌러주세요.');
    return;
  }
  VIEW = v;
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
  const n = $('#notice');
  if (ev.target.value === 'imap') {
    n.innerHTML = '주의: 메일 내용이 AI 서비스(Anthropic)로 전송됩니다. ' +
      '<label><input type="checkbox" id="agree"> 이해했고 동의합니다</label>';
    n.classList.remove('hidden');
  } else n.classList.add('hidden');
});

load();
