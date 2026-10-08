const adminAccess = {catalog:null, detail:null, csrf:'', loading:0};
function accessEscape(v) { return String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
async function accessRequest(url, options={}) {
  const res=await fetch(url,options);if(res.redirected)throw new Error('Session expired. Sign in again.');
  const data=await res.json();if(!res.ok || !data.success)throw new Error(data.error || 'Unable to update access.');return data;
}
async function loadAccessCatalog() {
  const status=document.getElementById('accessStatus');status.textContent='Loading access settings…';
  try {
    const data=await accessRequest('/api/admin/access/catalog');adminAccess.catalog=data;adminAccess.csrf=data.csrf_token;
    document.getElementById('accessMetrics').innerHTML=Object.entries(data.modules).map(([key,label])=>`<div class="access-metric"><b>${accessEscape(label)}</b><strong>${data.accounts.filter(a=>a.modules[key].allowed).length}</strong><span>Customer accounts with access</span></div>`).join('');
    document.getElementById('customPlanAccount').innerHTML=data.accounts.map(a=>`<option value="${accessEscape(a.id)}">${accessEscape(a.name)} · ${accessEscape(a.email)}</option>`).join('');
    document.getElementById('customPlanModules').innerHTML=Object.entries(data.modules).map(([key,label])=>`<label><input type="checkbox" name="modules" value="${key}"> ${accessEscape(label)}</label>`).join('');
    renderAccessTargets();renderAccessDirectory();status.textContent='Changes take effect on the next request, including existing signed-in sessions.';
  }catch(e){status.textContent=e.message;}
}
function renderAccessTargets() {
  if(!adminAccess.catalog)return;
  const scope=document.getElementById('accessScope').value;
  const rows=adminAccess.catalog[{account:'accounts',company:'companies',plan:'plans'}[scope]];
  document.getElementById('accessTarget').innerHTML=rows.map(r=>`<option value="${accessEscape(r.id)}">${accessEscape(r.name)}${r.email?' · '+accessEscape(r.email):''}</option>`).join('');
  document.getElementById('accessOpen').disabled=rows.length===0;
}
function renderAccessDirectory() {
  if(!adminAccess.catalog)return;
  const q=document.getElementById('accessSearch').value.toLowerCase();
  const rows=adminAccess.catalog.accounts.filter(a=>[a.name,a.email,a.plan].join(' ').toLowerCase().includes(q));
  const body=document.getElementById('accessDirectory');
  body.innerHTML=rows.map(a=>`<tr><td><strong>${accessEscape(a.name)}</strong><br><span class="access-note">${accessEscape(a.email)}${a.active?'':' · Suspended'}</span></td><td>${accessEscape(a.plan || 'No plan')}${a.trial_end?`<br><span class="access-note">${a.trial_expired?'Expired':'Trial ends'} ${accessEscape(a.trial_end)}</span>`:''}</td>${['crm','repair','orderflow','core','hr','bi'].map(key=>`<td><span class="access-chip ${a.modules[key].allowed?'on':''}" title="${accessEscape(a.modules[key].reason)}">${a.modules[key].allowed?'Allowed':'Blocked'}</span></td>`).join('')}<td><button class="access-button" data-account-id="${accessEscape(a.id)}">Manage</button></td></tr>`).join('') || '<tr><td colspan="7">No matching customer accounts.</td></tr>';
  body.querySelectorAll('[data-account-id]').forEach(b=>b.addEventListener('click',()=>openAccessDetail('account',b.dataset.accountId)));
}
function openSelectedAccess() { openAccessDetail(document.getElementById('accessScope').value,document.getElementById('accessTarget').value); }
async function openAccessDetail(scope,target) {
  if(!target)return;const requestId=++adminAccess.loading;const box=document.getElementById('accessDetail');box.hidden=false;box.textContent='Loading…';
  try {
    const data=await accessRequest('/api/admin/access/'+encodeURIComponent(scope)+'/'+encodeURIComponent(target));
    if(requestId!==adminAccess.loading)return;adminAccess.detail=data;renderAccessDetail();box.scrollIntoView({behavior:'smooth',block:'start'});
  }catch(e){if(requestId===adminAccess.loading)box.textContent=e.message;}
}
function accessChanges(h) {
  const result=[];
  for(const [key,label] of Object.entries(adminAccess.catalog.modules)) {
    const before=h.before.overrides?.[key],after=h.after.overrides?.[key];
    const labelOf=v=>v===true?'Allow':v===false?'Block':'Follow plan';
    if(before!==after)result.push(label+': '+labelOf(before)+' → '+labelOf(after));
  }
  if(h.before.trial_end!==h.after.trial_end)result.push('Trial end: '+(h.before.trial_end || 'Original date')+' → '+h.after.trial_end);
  return result.join(' · ') || 'Settings saved';
}
function renderAccessDetail() {
  const d=adminAccess.detail;const box=document.getElementById('accessDetail');
  box.innerHTML=`<div class="access-hero"><div><h3>${accessEscape(d.name)}</h3><p class="access-note">${accessEscape(d.scope==='user'?'Team member':d.scope)} · Plan: ${accessEscape(d.plan || 'None')}</p></div>${d.scope==='company'?'<button class="access-button" id="accessWorkspace">Open Company Workspace</button>':''}</div>
    <p class="access-note">Follow plan removes this override. Allow can add a module missing from the plan. Block overrides plan access. An account or company block cannot be bypassed by a team-member Allow.</p>
    ${d.scope==='plan'?'<p class="access-note">Plan changes apply to customers following this plan. Existing account, company and team-member overrides are retained.</p>':''}
    <form id="accessEditor">
      <div class="access-toolbar"><button type="button" class="access-button" data-access-bulk="allow">Allow All</button><button type="button" class="access-button" data-access-bulk="block">Block All</button><button type="button" class="access-button" data-access-bulk="inherit">Follow Plan for All</button></div>
      <div class="access-table-wrap"><table class="access-table"><thead><tr><th>Workspace</th><th>Access setting</th><th>Effective access now</th></tr></thead><tbody>${Object.entries(d.modules).map(([key,label])=>{
        const value=d.state.overrides[key]===true?'allow':d.state.overrides[key]===false?'block':'inherit';
        return `<tr><td><strong>${accessEscape(label)}</strong></td><td><select class="access-input" name="${key}" aria-label="${accessEscape(label)} access">${[['inherit','Follow plan / parent'],['allow','Allow'],['block','Block']].map(([v,l])=>`<option value="${v}" ${v===value?'selected':''}>${l}</option>`).join('')}</select></td><td><span class="access-chip ${d.effective[key].allowed?'on':''}">${d.effective[key].allowed?'Allowed':'Blocked'}</span><br><span class="access-note">${accessEscape(d.effective[key].reason)}</span></td></tr>`;
      }).join('')}</tbody></table></div>
      ${d.trial_end?`<div class="access-trial"><h3>Extend Trial</h3><p>Current end date: <strong>${accessEscape(d.trial_end)}</strong> · ${d.trial_days_left<0?'Expired':d.trial_days_left+' days remaining'}</p><div class="access-toolbar"><div><label for="accessExtendDays">Additional days</label><input id="accessExtendDays" name="extend_days" class="access-input" type="number" min="0" max="3650" step="1" value="0"></div><span id="accessTrialPreview" class="access-note"></span></div><p class="access-note">Extensions start from the later of today or the current end date. Paid plans are unchanged. ${d.scope==='account'?'Companies with their own trial end date keep that date.':''}</p></div>`:'<p class="access-note" style="margin-top:16px;">Trial extension is available for trial accounts and trial companies only.</p>'}
      <label class="access-form-label" for="accessReason" style="margin-top:20px;">Reason / notes</label><input id="accessReason" class="access-input" name="reason" maxlength="1000" style="width:100%;" placeholder="Optional note for the access history">
      <div class="access-save-bar"><span class="access-note">Selections apply only after you save.</span><button id="accessSave" class="access-button primary" type="submit">Save Access & Trial</button></div><p id="accessSaveStatus" role="status" class="access-note" style="margin-top:12px;"></p>
    </form>
    ${d.scope==='company'?`<div class="access-history"><h3>Individual Team Access</h3>${d.team_error?`<p>${accessEscape(d.team_error)}</p>`:d.members.length?`<div class="access-toolbar"><select class="access-input" id="accessTeam">${d.members.map(m=>`<option value="${accessEscape(m.id)}">${accessEscape(m.name)} · ${accessEscape(m.role)}</option>`).join('')}</select><button id="accessTeamOpen" class="access-button">Manage Team Member</button></div>`:'<p class="access-note">No non-owner team members found. Owner access is managed at account level.</p>'}</div>`:''}
    <div class="access-history"><h3>Access History</h3>${d.history.map(h=>`<div class="access-history-item"><strong>${accessEscape(accessChanges(h))}</strong><br>${accessEscape(h.actor)} · ${accessEscape(new Date(h.time).toLocaleString())}${h.reason?'<br>'+accessEscape(h.reason):''}</div>`).join('') || '<p class="access-note">No access changes recorded yet.</p>'}</div>`;
  document.getElementById('accessEditor').onsubmit=saveAccessDetail;
  box.querySelectorAll('[data-access-bulk]').forEach(b=>b.addEventListener('click',()=>Object.keys(d.modules).forEach(k=>document.getElementById('accessEditor').elements[k].value=b.dataset.accessBulk)));
  document.getElementById('accessTeamOpen')?.addEventListener('click',()=>openAccessDetail('user',document.getElementById('accessTeam').value));
  document.getElementById('accessWorkspace')?.addEventListener('click',openAdminWorkspace);
  document.getElementById('accessExtendDays')?.addEventListener('input',()=>{
    const days=Number(document.getElementById('accessExtendDays').value);const end=new Date(d.trial_end+'T00:00:00Z');
    const today=new Date((adminAccess.catalog.today || new Date().toISOString().slice(0,10))+'T00:00:00Z');const base=end>today?end:today;base.setUTCDate(base.getUTCDate()+days);
    document.getElementById('accessTrialPreview').textContent=Number.isInteger(days)&&days>0&&days<=3650?'New end date: '+base.toISOString().slice(0,10):'No trial extension selected';
  });
}
async function saveAccessDetail(event) {
  event.preventDefault();const d=adminAccess.detail;const form=event.target;const button=document.getElementById('accessSave');button.disabled=true;
  const overrides={};for(const key of Object.keys(d.modules)){const v=form.elements[key].value;if(v!=='inherit')overrides[key]=v==='allow';}
  try {
    const data=await accessRequest('/api/admin/access/'+encodeURIComponent(d.scope)+'/'+encodeURIComponent(d.target),{method:'PUT',headers:{'Content-Type':'application/json','X-Admin-CSRF':adminAccess.csrf},body:JSON.stringify({overrides,revision:d.state.revision,extend_days:Number(form.elements.extend_days?.value || 0),reason:form.elements.reason.value})});
    adminAccess.detail=data;renderAccessDetail();document.getElementById('accessSaveStatus').textContent='Saved. Effective access and trial dates are updated.';await loadAccessCatalog();
  }catch(e){document.getElementById('accessSaveStatus').textContent=e.message;button.disabled=false;}
}
async function openAdminWorkspace() {
  const button=document.getElementById('accessWorkspace');button.disabled=true;
  try{const data=await accessRequest('/api/admin/access/open-company/'+encodeURIComponent(adminAccess.detail.target),{method:'POST',headers:{'X-Admin-CSRF':adminAccess.csrf}});window.location.href=data.redirect;}
  catch(e){document.getElementById('accessSaveStatus').textContent=e.message;button.disabled=false;}
}

async function assignCustomPlan(event) {
  event.preventDefault();
  const form=event.target, button=form.querySelector('button[type="submit"]'), status=document.getElementById('customPlanStatus');
  const data=Object.fromEntries(new FormData(form));
  data.modules=new FormData(form).getAll('modules');
  for(const key of ['users','companies','branches','years']) data[key]=Number(data[key]);
  button.disabled=true;status.textContent='Assigning private plan…';
  try {
    const result=await accessRequest('/api/admin/custom-plan/'+encodeURIComponent(document.getElementById('customPlanAccount').value),{method:'POST',headers:{'Content-Type':'application/json','X-Admin-CSRF':adminAccess.csrf},body:JSON.stringify(data)});
    status.textContent=result.message;await loadAccessCatalog();
  } catch(error) {status.textContent=error.message;} finally {button.disabled=false;}
}
