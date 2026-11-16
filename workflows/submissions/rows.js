'use strict';
const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
let pin, selected, generation = 0;
const label = s => String(s || '').replaceAll('__',' · ').replaceAll('_',' ');
async function req(path, options) {
  const response = await fetch(path, options), data = await response.json();
  if (!response.ok) throw Error(data.error || 'Request failed');
  return data;
}
function options(id, values, first) {
  $(id).replaceChildren(new Option(first,''));
  for (const v of values) $(id).add(new Option(label(v), v));
}
function mode() {
  const rating=$('kind').value==='rating', spatial=$('table').value==='T4';
  $('vote').hidden=!rating; $('words').hidden=rating;
  $('word-label').textContent=spatial?'Justification for this mapping':'Mechanism';
  $('conditional').hidden=$('conditional-label').hidden=spatial;
}
async function load(record='', desired='') {
  const gen=++generation;
  selected=null; $('card').hidden=true; $('status').replaceChildren();
  const p=$('practice').value,t=$('table').value;
  if (!p) {options('record',[],'Select a practice');return;}
  const query=new URLSearchParams({practice:p,table:t});
  if (!record) {
    const {records}=await req('/api/rows?'+query);
    if(gen!==generation)return;
    options('record',records,'Select a row');
    if(desired) {if (!records.includes(desired)) throw Error('Linked row does not exist in this edition.');
      $('record').value=desired; await load(desired);}
    return;
  }
  query.set('record',record);
  const d=await req('/api/rows?'+query);
  if(gen!==generation)return;
  const r=d.row; selected=d.target;
  $('decision').value=$('reason').value=$('note').value='';
  $('rating').textContent=[r.mitigation_potential,r.asset_sensitivity,r.effect_direction,r.relationship_type,r.effect_confidence||r.confidence].filter(Boolean).map(label).join(' · ') || 'See economic indicators below.';
  $('mechanism').value=t==='T4' ? (r.justification || '') : (r.mitigation_mechanism || r.effect_mechanism || '');
  $('conditional').value=r.caveats || r.conditionality || '';
  $('current').textContent=[$('mechanism').value,$('conditional').value].filter(Boolean).join(' ');
  $('warning').textContent=d.stale.map(w=>'Wording needs review: '+w.reason).join('; ');
  $('evidence').replaceChildren();
  for(const id of selected.evidence_ids) {const li=document.createElement('li'),a=document.createElement('a');
    a.href='https://ruralscan.github.io/method/#review-evidence='+encodeURIComponent(id);a.textContent=id;li.append(a);$('evidence').append(li);}
  $('data').textContent=JSON.stringify(r,null,2);$('card').hidden=false;mode();
}
function err(e){$('status').textContent=e.message;}
async function init(){
  const d=await req('/api/rows');pin=d.revision;
  $('edition').textContent='RuralScan/evidence · '+pin+' · Signed in as '+d.actor;
  if(params.has('revision')&&params.get('revision')!==pin) throw Error('Linked edition differs from this desk. Reopen the desk at the revision you reviewed.');
  options('practice',d.practices,'Select a practice');
  if(['rating','wording'].includes(params.get('kind'))) $('kind').value=params.get('kind');
  if (params.has('table')) $('table').value=params.get('table');
  if (params.has('practice')) $('practice').value=params.get('practice');
  await load('',params.get('record'));
}
for(const id of ['practice','table']) $(id).onchange=()=>load().catch(err);
$('record').onchange=()=>load($('record').value).catch(err); $('kind').onchange=mode;
$('action').onsubmit=async e=>{
  e.preventDefault(); if(!selected)return;
  const kind=$('kind').value, entry={...selected,revision:pin,kind};
  if(kind==='rating') Object.assign(entry,{decision:$('decision').value,reason:$('reason').value,note:$('note').value});
  else entry.wording=selected.table==='T4'?{justification:$('mechanism').value}:{mechanism:$('mechanism').value,conditionality:$('conditional').value};
  $('submit').disabled=true;
  try {const r=await req('/api/rows',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(entry)});
    const a=document.createElement('a');a.href=r.url;a.textContent='Open your receipt';$('status').replaceChildren('Submitted. ',a);}
  catch(e){err(e);}finally{$('submit').disabled=false;}
};
init().catch(err);
