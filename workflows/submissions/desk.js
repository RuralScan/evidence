'use strict';
const byId = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
let session;
async function request(path, options) {
  const res = await fetch(path, options);
  const data = await res.json();
  if (!res.ok) throw Error(data.error || 'Connection failed');
  return data;
}
function showError(error) { byId('status').textContent = error.message; }
function finding() {
  const id = byId('eid').value.trim();
  const source = byId('source');
  source.hidden = !id || session.test;
  source.href = 'https://ruralscan.github.io/method/#review-evidence=' + encodeURIComponent(id);
  byId('quote').textContent = session.test ? 'Synthetic finding for checking submission and attribution.' : '';
}
async function history() {
  const data = await request('/api/history');
  const list = byId('receipts');
  list.replaceChildren();
  for (const row of data.receipts) {
    const item = document.createElement('li');
    item.textContent = (session.test ? 'Test receipt #' : 'Receipt #') + row.receipt + ' · ' + row.lane + ' · ' +
      (row.kind === 'csv' ? 'CSV received' : row.payload.evidence_id + ' · ' + row.payload.decision);
    if (row.url) {
      const link = document.createElement('a');
      link.href = row.url; link.textContent = ' View public receipt';
      item.append(link);
    }
    list.append(item);
  }
}
async function submit(kind, payload) {
  if (!session) throw Error('Wait for sign-in');
  const result = await request('/api/submit', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({kind, payload, lane:byId('lane').value, revision:session.revision})});
  byId('status').textContent = result.test ? 'Test receipt #' + result.receipt + ' saved for ' + session.actor :
    'Submitted to RuralScan/evidence. ';
  if (result.url) {
    const link = document.createElement('a');
    link.href = result.url; link.textContent = 'View public receipt';
    byId('status').append(link);
  }
  await history();
}
async function init() {
  session = await request('/api/session');
  if (params.has('revision') && params.get('revision') !== session.revision)
    throw Error('This desk is serving another revision. Restart it at the revision on the finding link.');
  byId('account').textContent = 'Signed in as ' + session.actor;
  byId('mode').textContent = session.local_only ? 'Local test · synthetic findings only' : session.test ? 'Public GitHub test · synthetic findings only' :
    'Your submission and GitHub name will be public in RuralScan/evidence · source ' + session.revision.slice(0,8);
  if (['T4','T3/T6'].includes(params.get('lane'))) byId('lane').value = params.get('lane');
  const selectId = () => {
    byId('eid').value = session.test ? session.fixtures[byId('lane').value] : (params.get('finding') || '');
    byId('decision').value = ''; byId('reason').value = ''; byId('note').value = '';
    finding();
  };
  selectId();
  byId('lane').addEventListener('change', selectId);
  byId('eid').addEventListener('input', finding);
  for (const code of session.reasons) {
    const option = document.createElement('option');
    option.value = code; option.textContent = code.replaceAll('_', ' ');
    byId('reason').append(option);
  }
  byId('vote').addEventListener('submit', async e => {
    e.preventDefault();
    const button = e.submitter; button.disabled = true;
    try { await submit('vote', {evidence_id:byId('eid').value.trim(), decision:byId('decision').value,
      reason:byId('reason').value, note:byId('note').value}); } catch (err) { showError(err); }
    finally { button.disabled = false; }
  });
  byId('upload').addEventListener('click', async () => {
    const file = byId('file').files[0];
    if (!file) return showError(Error('Choose an evidence review CSV'));
    try { await submit('csv', await file.text()); } catch (err) { showError(err); }
  });
  byId('history').addEventListener('click', () => history().catch(showError));
  if (params.get('view') === 'mine') await history();
}
init().catch(showError);
