/* CRM modules use the workspace's existing theme and components. */
const workspaceState = {contacts: [], accounts: [], projects: [], formKind: '', editId: null, preferences: {}, canEdit: false};
function crmEscape(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
async function crmRequest(url, options={}) {
  const response = await fetch(url, options);
  if (response.redirected) throw new Error('Your session expired. Please sign in again.');
  const data = await response.json();
  if (!response.ok || !data.success) throw new Error(data.error || 'Unable to complete the request.');
  return data;
}
const crmJson = data => ({method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
async function loadWorkspaceMetrics() {
  const box = document.getElementById('workspaceMetrics');
  try {
    const [m, p] = await Promise.all([crmRequest('/api/crm/workspace/metrics'), crmRequest('/api/crm/workspace/preferences')]);
    box.hidden = p.preferences.show_metrics === false;
    box.style.display = box.hidden ? 'none' : '';
    const labels = {accounts:'Accounts',contacts:'Contacts',open_deals:'Open Deals',active_projects:'Active Projects',open_tasks:'Open Tasks',scheduled_calls:'Pending Calls',scheduled_meetings:'Pending Meetings',overdue:'Overdue Activities'};
    box.innerHTML = Object.entries(labels).map(([key,label]) => `<div class="stat-card" style="--stat-color:var(--primary);"><div class="stat-label">${label}</div><div class="stat-val">${Number(m[key] || 0)}</div><div class="stat-sub">Current company</div></div>`).join('');
  } catch(e) { box.textContent = e.message; }
}
async function loadWorkspacePane(tab) {
  const target = document.getElementById({contacts:'workspaceContacts',projects:'workspaceProjects',reports:'workspaceReports',setup:'crmSetupGrid'}[tab]);
  target.replaceChildren();
  try {
    if (tab === 'setup') {
      const result = await crmRequest('/api/crm/workspace/preferences');
      workspaceState.preferences = result.preferences; workspaceState.canEdit = result.can_edit;
      renderCrmSetup(); return;
    }
    if (tab === 'reports') { await renderWorkspaceReports(); return; }
    const [records, accounts] = await Promise.all([crmRequest('/api/crm/' + tab),crmRequest('/api/crm/clients')]);
    workspaceState.accounts = accounts.clients;
    workspaceState[tab] = records[tab];
    if (tab === 'contacts') renderWorkspaceContacts(); else renderWorkspaceProjects();
  } catch(e) {
    if (target.tagName === 'TBODY') target.innerHTML = `<tr><td colspan="6">${crmEscape(e.message)}</td></tr>`;
    else target.textContent = e.message;
  }
}
function accountName(id) { return workspaceState.accounts.find(a => String(a.id) === String(id))?.name || 'Unassigned'; }
function renderWorkspaceContacts() {
  const search = document.getElementById('contactSearch').value.toLowerCase();
  const rows = workspaceState.contacts.filter(c => [c.name,c.email,c.phone,accountName(c.client_id)].join(' ').toLowerCase().includes(search));
  document.getElementById('workspaceContacts').innerHTML = rows.map(c => `<tr>${[c.name,accountName(c.client_id),c.designation,c.phone,c.email,c.is_primary?'Yes':'No'].map(v=>`<td>${crmEscape(v || '—')}</td>`).join('')}</tr>`).join('') || '<tr><td colspan="6">No contacts found.</td></tr>';
}
function renderWorkspaceProjects() {
  const body = document.getElementById('workspaceProjects');
  body.innerHTML = workspaceState.projects.map((p,i) => `<tr>${[p.name,accountName(p.client_id),p.owner,p.due_date,p.status].map(v=>`<td>${crmEscape(v || '—')}</td>`).join('')}<td><button class="btn btn-ghost" data-project-index="${i}">Edit</button></td></tr>`).join('') || '<tr><td colspan="6">No projects yet.</td></tr>';
  body.querySelectorAll('[data-project-index]').forEach(b => b.addEventListener('click',()=>openWorkspaceForm('project', workspaceState.projects[Number(b.dataset.projectIndex)])));
}
async function renderWorkspaceReports() {
  const data = await crmRequest('/api/crm/reports');
  const money = v => new Intl.NumberFormat(window.qiyadahCurrency === 'INR' ? 'en-IN' : 'en-US', {style:'currency', currency:window.qiyadahCurrency || 'INR'}).format(Number(v || 0));
  const q = data.quotations_summary;
  document.getElementById('workspaceReports').innerHTML = `<div class="stats-grid">${[['Total Leads',data.total_leads],['Quotations',q.total],['Accepted',q.accepted],['Pending Quotes',q.pending]].map(([label,value])=>`<div class="stat-card" style="--stat-color:var(--primary);"><div class="stat-label">${label}</div><div class="stat-val">${Number(value || 0)}</div></div>`).join('')}</div><div class="table-container"><div class="table-header-bar"><h3>Pipeline by Stage</h3></div><table class="data-table"><thead><tr><th>Stage</th><th>Count</th><th>Estimated Value</th></tr></thead><tbody>${(data.stage_order || Object.keys(data.stage_breakdown)).map(stage => [stage, data.stage_breakdown[stage]]).map(([stage,v])=>`<tr><td>${crmEscape(stage)}</td><td>${Number(v.count)}</td><td>${money(v.total_val)}</td></tr>`).join('')}</tbody></table></div><div class="table-container" style="margin-top:16px;"><div class="table-header-bar"><h3>Lead Sources</h3></div><table class="data-table"><thead><tr><th>Source</th><th>Leads</th></tr></thead><tbody>${Object.entries(data.source_distribution).map(([source,count])=>`<tr><td>${crmEscape(source)}</td><td>${Number(count)}</td></tr>`).join('') || '<tr><td colspan="2">No leads yet.</td></tr>'}</tbody></table></div>`;
}
function workspaceField(name, label, type='text', value='', options=null, required=false) {
  const input = options ? `<select class="input" id="crm-field-${name}" name="${name}" ${required?'required':''}>${options.map(([v,l])=>`<option value="${crmEscape(v)}" ${String(v)===String(value)?'selected':''}>${crmEscape(l)}</option>`).join('')}</select>` : `<input class="input" id="crm-field-${name}" name="${name}" type="${type}" value="${crmEscape(value)}" ${required?'required':''} maxlength="${name==='summary'||name==='description'?10000:200}">`;
  return `<div class="form-group"><label for="crm-field-${name}">${label}${required?' *':''}</label>${input}</div>`;
}
async function openWorkspaceForm(kind, row={}) {
  workspaceState.formKind = kind; workspaceState.editId = row.id || null;
  document.getElementById('workspaceFormError').textContent = '';
  document.getElementById('workspaceFormTitle').textContent = (row.id?'Edit ':'New ') + ({contact:'Contact',project:'Project',activity:'Activity'})[kind];
  document.getElementById('workspaceFormModal').style.display = 'flex';
  const fields = document.getElementById('workspaceFormFields'); fields.textContent = 'Loading accounts…';
  const submit = document.querySelector('#workspaceForm button[type=submit]'); submit.disabled = true;
  try {
    workspaceState.accounts = (await crmRequest('/api/crm/clients')).clients;
    const options = [['','Select account'],...workspaceState.accounts.map(a=>[a.id,a.name])];
    let html = workspaceField('client_id','Account','text',row.client_id || '',options,kind==='contact');
    if (kind === 'contact') {
      html += workspaceField('name','Name','text','',null,true)+workspaceField('designation','Designation')+workspaceField('phone','Phone','tel')+workspaceField('email','Email','email');
      html += '<div class="form-group"><label><input type="checkbox" name="is_primary"> Primary contact</label></div>';
    } else if (kind === 'project') {
      html += workspaceField('name','Project Name','text',row.name || '',null,true)+workspaceField('owner','Owner','text',row.owner || '')+workspaceField('due_date','Due Date','date',row.due_date || '')+workspaceField('status','Status','text',row.status || 'Planned',['Planned','In Progress','On Hold','Completed','Archived'].map(v=>[v,v]))+workspaceField('description','Description','text',row.description || '');
    } else {
      const type = document.getElementById('actTypeFilter').value;
      html += workspaceField('type','Activity Type','text',type==='all'?'task':type,['task','call','meeting','email','whatsapp','followup','note'].map(v=>[v,v]))+workspaceField('title','Title')+workspaceField('summary','Description','text','',null,true)+workspaceField('due_date','Due Date','date')+workspaceField('priority','Priority','text','normal',['low','normal','high'].map(v=>[v,v]));
    }
    fields.innerHTML = html; submit.disabled = false;
  } catch(e) { fields.textContent = e.message; }
}
function openNewActivityModal() { openWorkspaceForm('activity'); }
async function saveWorkspaceForm(event) {
  event.preventDefault(); const button = event.target.querySelector('button[type=submit]'); button.disabled = true;
  try {
    const kind = workspaceState.formKind;
    const data = Object.fromEntries(new FormData(event.target));
    if (kind === 'contact') data.is_primary = data.is_primary === 'on';
    const module = {contact:'contacts',project:'projects',activity:'activities'}[kind];
    const options = crmJson(data); let url = '/api/crm/' + module;
    if (kind === 'project' && workspaceState.editId) { url += '/' + encodeURIComponent(workspaceState.editId); options.method='PUT'; }
    await crmRequest(url,options); closeModal('workspaceFormModal');
    if (kind === 'activity') loadActivities(); else loadWorkspacePane(module);
    loadWorkspaceMetrics();
  } catch(e) { document.getElementById('workspaceFormError').textContent = e.message; }
  finally { button.disabled = false; }
}
const crmSetupGroups = {
  'General': [['Personal Settings','/profile'],['Users','/company/settings?tab=team'],['Company Settings','/company/settings']],
  'Security Control': [['Profiles','/company/settings?tab=access'],['Roles and Sharing','/company/settings?tab=access'],['Compliance Settings','compliance'],['Support Access','support']],
  'Channels': [['Email','email'],['Notification SMS','sms'],['Webforms','webforms'],['Chat / Visitor Tracking','chat']],
  'Customization': [['Modules and Fields','fields'],['Customize Home Page','home'],['Templates','templates']],
  'Automation': [['Workflow Rules','workflows'],['Actions','actions']],
  'Data Administration': [['Import','import'],['Export','export'],['Data Backup','/backup'],['Remove Sample Data','sample'],['Storage','storage'],['Recycle Bin','recycle']],
  'Marketplace': [['Zoho','zoho'],['Microsoft','microsoft'],['Extension Builder','extensions']],
  'Developer Hub': [['APIs and SDKs','api']]
};
function renderCrmSetup() {
  const grid = document.getElementById('crmSetupGrid');
  grid.innerHTML = Object.entries(crmSetupGroups).map(([group,items])=>`<section class="table-container" data-setup-group style="padding:20px;"><h3 style="font-size:15px;margin-bottom:14px;">${crmEscape(group)}</h3>${items.map(([label,target])=> target.startsWith('/') ? `<a class="btn btn-ghost" data-setup-label="${crmEscape(label.toLowerCase())}" href="${crmEscape(target)}" style="display:flex;margin-bottom:8px;">${crmEscape(label)}</a>` : `<button class="btn btn-ghost" data-setup-label="${crmEscape(label.toLowerCase())}" data-setup-option="${target}" style="display:flex;width:100%;margin-bottom:8px;text-align:left;">${crmEscape(label)}</button>`).join('')}</section>`).join('');
  grid.querySelectorAll('[data-setup-option]').forEach(b=>b.addEventListener('click',()=>openCrmSetup(b.dataset.setupOption)));
}
function filterCrmSetup(search) {
  search = search.trim().toLowerCase();
  document.querySelectorAll('[data-setup-group]').forEach(group=>{
    const title = group.querySelector('h3').textContent.toLowerCase(); let found = false;
    group.querySelectorAll('[data-setup-label]').forEach(item=>{const show = title.includes(search) || item.dataset.setupLabel.includes(search);item.style.display = show?'flex':'none';found ||= show;});
    group.hidden = !found;
  });
}
function openCrmSetup(option) {
  const detail = document.getElementById('crmSetupDetail'); detail.hidden = false;
  const titles = Object.values(crmSetupGroups).flat();
  const title = titles.find(v=>v[1]===option)?.[0] || 'Setup';
  detail.innerHTML = `<h3 style="margin-bottom:14px;">${crmEscape(title)}</h3>`;
  const info = {
    compliance:'Company access controls are available under Roles and Sharing. A separate compliance policy engine is not installed.',
    support:'Support access is not enabled. Manage authorized company users and their roles in Company Settings; no external support account is granted access automatically.',
    email:'Email delivery requires a configured mail provider. You can record email interactions in Activities; this screen does not connect an inbox or send messages.',
    sms:'SMS notifications require a messaging provider and sender configuration. No SMS integration is connected.',
    webforms:'Public website lead capture requires a validated form integration. Use New Lead for manual capture; this workspace does not publish an unauthenticated lead endpoint.',
    templates:'Quotation creation is available in the Quotations module. Custom CRM email templates require an email provider integration.',
    workflows:'Tasks and follow-ups can be scheduled in Activities. An automatic workflow rule engine is not installed; saving an activity does not send messages automatically.',
    actions:'Create a task, call, meeting or follow-up and track its completion in Activities.',
    sample:'CRM records are not marked as sample data. Automatic sample removal is unavailable to avoid deleting real customer records.',
    storage:'CRM records are stored in your company database. Use Data Backup for downloadable backups; database capacity information is managed by your hosting provider.',
    recycle:'Projects can be archived and reopened through their status. Legacy CRM delete actions permanently remove records and do not have a recycle bin.',
    zoho:'Zoho is not connected. A provider authorization and field mapping are required before CRM data can be synchronized. The modules here operate on your Qiyadah records.',
    microsoft:'Microsoft is not connected. Mail and calendar synchronization require provider authorization and a configured integration.',
    extensions:'Custom extensions need a server-side integration and review. No third-party extension is loaded from this page.',
    import:'Use the company Import workspace for its supported formats. CRM-specific bulk import is not yet available; contacts and projects can be entered using their forms.'
  };
  if (info[option]) {
    const p=document.createElement('p'); p.textContent=info[option];p.style.color='var(--text-muted)';detail.append(p);
    const buttons = {actions:['Open Activities',()=>switchCrmTab('activities')],workflows:['Schedule a Follow-up',()=>{switchCrmTab('activities');openNewActivityModal();}],templates:['Open Quotations',()=>switchCrmTab('quotations')],recycle:['Manage Projects',()=>switchCrmTab('projects')]};
    if (buttons[option]) {const b=document.createElement('button');b.className='btn btn-primary';b.style.marginTop='16px';b.textContent=buttons[option][0];b.onclick=buttons[option][1];detail.append(b);}
    if (option==='import') {const a=document.createElement('a');a.className='btn btn-primary';a.href='/import';a.textContent='Open Company Import';detail.append(a);}
  } else if (option==='export') {
    detail.insertAdjacentHTML('beforeend','<p style="margin-bottom:12px;">Download current-company CRM records as CSV.</p>'+['contacts','leads','activities','projects'].map(m=>`<a class="btn btn-ghost" href="/api/crm/workspace/export/${m}" style="margin:4px;">${m[0].toUpperCase()+m.slice(1)}</a>`).join(''));
  } else if (option==='fields') {
    const rows={Leads:'Title, account, stage, estimated value, source, expected close date',Contacts:'Name, account, designation, phone, email, primary contact',Accounts:'Name, phone, email, city, tax number',Deals:'Qualified and later lead stages; same account and sales records',Activities:'Type, account, title, summary, priority, due date, status',Projects:'Name, account, owner, status, due date, description'};
    detail.insertAdjacentHTML('beforeend','<p>Current CRM fields. Custom field editing is not enabled.</p><table class="data-table"><tbody>'+Object.entries(rows).map(([k,v])=>`<tr><th>${k}</th><td>${v}</td></tr>`).join('')+'</tbody></table>');
  } else if (option==='api') {
    detail.insertAdjacentHTML('beforeend','<p>CRM APIs use the current signed-in company session. No public API key or SDK is provisioned here.</p><table class="data-table"><thead><tr><th>Endpoint</th><th>Methods</th></tr></thead><tbody>'+[['/api/crm/contacts','GET, POST'],['/api/crm/leads','GET, POST'],['/api/crm/activities','GET, POST'],['/api/crm/projects','GET, POST'],['/api/crm/projects/{id}','PUT'],['/api/crm/reports','GET'],['/api/crm/workspace/metrics','GET']].map(([u,m])=>`<tr><td><code>${u}</code></td><td>${m}</td></tr>`).join('')+'</tbody></table>');
  } else if (option==='home' || option==='chat') {
    const prefs=workspaceState.preferences;
    let fields = option==='home' ? `<label><input type="checkbox" name="show_metrics" ${prefs.show_metrics!==false?'checked':''}> Show account, activity and project metrics on Home</label>` :
      `<p style="grid-column:1/-1;color:var(--text-muted);">Configure a provider-hosted chat/visitor widget for your website. This saves installation details only; it does not verify the provider connection or collect visitor metrics in CRM.</p>${workspaceField('chat_provider','Provider','text',prefs.chat_provider || '')}${workspaceField('chat_account','Account','text',prefs.chat_account || '')}${workspaceField('chat_department','Department','text',prefs.chat_department || '')}${workspaceField('chat_widget_url','Provider Widget Script URL','url',prefs.chat_widget_url || '')}<label><input type="checkbox" name="chat_enabled" ${prefs.chat_enabled?'checked':''}> Enable installation snippet</label>`;
    detail.insertAdjacentHTML('beforeend',`<form id="crmSetupForm"><fieldset ${workspaceState.canEdit?'':'disabled'} style="border:0;"><div class="form-grid">${fields}</div><button class="btn btn-primary" style="margin-top:16px;" type="submit">Save Settings</button></fieldset><p id="crmSetupMessage" role="status" style="margin-top:12px;">${workspaceState.canEdit?'':'Only owners can edit setup.'}</p></form>`);
    document.getElementById('crmSetupForm').onsubmit = async event=>{
      event.preventDefault();const form=event.target;const button=form.querySelector('button');button.disabled=true;
      const values=Object.fromEntries(new FormData(form));const flag=option==='home'?'show_metrics':'chat_enabled';values[flag]=values[flag]==='on';
      try {await crmRequest('/api/crm/workspace/preferences',crmJson(values));workspaceState.preferences={...prefs,...values};document.getElementById('crmSetupMessage').textContent='Settings saved.';loadWorkspaceMetrics();if(option==='chat') renderChatSnippet();}
      catch(e){document.getElementById('crmSetupMessage').textContent=e.message;}finally{button.disabled=false;}
    };
    if(option==='chat') {detail.insertAdjacentHTML('beforeend','<div id="crmChatSnippet" style="margin-top:16px;"></div>');renderChatSnippet();}
  }
  detail.scrollIntoView({behavior:'smooth',block:'nearest'});
}
function renderChatSnippet() {
  const box=document.getElementById('crmChatSnippet');box.replaceChildren();const p=workspaceState.preferences;
  const status=document.createElement('p');status.textContent=p.chat_enabled?'Snippet enabled · Provider connection not verified':'Not configured / snippet disabled';box.append(status);
  if(p.chat_enabled && p.chat_widget_url) {
    const label=document.createElement('p');label.textContent='Add to your website only if your provider supports a single script embed. For providers needing extra configuration, use their full installation code.';box.append(label);
    const area=document.createElement('textarea');area.className='input';area.readOnly=true;area.rows=4;area.setAttribute('aria-label','Chat widget installation snippet');
    area.value='<script async src="'+crmEscape(p.chat_widget_url)+'"></'+'script>';box.append(area);
    const copy=document.createElement('button');copy.className='btn btn-ghost';copy.textContent='Copy Code';copy.onclick=async()=>{try{await navigator.clipboard.writeText(area.value);copy.textContent='Copied';}catch(e){area.select();copy.textContent='Select and copy the code';}};box.append(copy);
  }
}
