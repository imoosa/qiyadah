/* Plain-language planning from the existing warehouse indicators. */
(function(root){
'use strict';
const esc=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>v==null?'—':Number(v).toLocaleString(undefined,{maximumFractionDigits:1});
const month=v=>new Date(v+'-01T12:00:00').toLocaleDateString(undefined,{month:'long',year:'numeric'});
const ready=p=>p?.status==='ready'&&p.forecast?.length>0;
function actions(d){
  const result=[];
  if(d.warehouse_warning)result.push({rank:0,label:'Check data first',title:'Refresh before making a decision',why:d.warehouse_warning,next:'Refresh the source data, then update this outlook.',link:'warehouse',button:'Open data refresh'});
  const cash=d.cash_flow_forecast;
  if(ready(cash)&&cash.forecast[0].value<0)result.push({rank:1,label:'Finance · review first',title:'Plan for more cash going out than coming in',why:'The recent pattern points to negative monthly net cash movement. This does not tell us your bank balance.',next:'Compare upcoming collections and payment due dates with your available cash.',link:'cash',button:'Review cash records'});
  const stock=(d.inventory_demand||[]).filter(r=>r.status==='ready'&&r.purchase_requirement_units>0);
  if(stock.length)result.push({rank:2,label:'Stock · purchasing',title:`Review ${stock.length} product${stock.length===1?'':'s'} for replenishment`,why:'Estimated demand during supplier delivery time, plus your reorder buffer, is greater than recorded stock.',next:'Check physical stock and orders already on the way before deciding what to purchase.',link:'#stock-details',button:'See suggested quantities'});
  const quiet=(d.customer_risk||[]).filter(r=>r.indicator==='at_risk');
  if(quiet.length)result.push({rank:3,label:'Sales · follow up',title:`Reconnect with ${quiet.length} quiet customer${quiet.length===1?'':'s'}`,why:'These customers have at least two invoices and 180 days of history, but no invoice in over 90 days.',next:'Ask whether they need help or have an upcoming order. A quiet period does not mean a customer is lost.',link:'#customer-details',button:'See customers to contact'});
  const rev=d.revenue_forecast;
  if(ready(rev)&&rev.history?.length){const last=rev.history.at(-1).actual;if(last>0&&rev.forecast[0].value<last*.9)result.push({rank:4,label:'Sales · review pipeline',title:'Prepare for a softer sales month',why:'The monthly estimate is more than 10% below the last completed month.',next:'Review open opportunities and check whether last month included a one-off large sale.',link:'crm',button:'Review CRM'});}
  if(d.anomalies?.status==='ready'&&d.anomalies.flags.length)result.push({rank:5,label:'Records · review',title:'Check unusual sales months',why:`${d.anomalies.flags.length} month(s) stand out from the historical pattern.`,next:'Check for one-off sales, missing records or duplicated invoices before changing plans.',link:'#unusual-months',button:'Review flagged months'});
  const missing=[d.revenue_forecast,d.sales_forecast,d.cash_flow_forecast].filter(p=>!ready(p)).length;
  const unknown=(d.inventory_demand||[]).filter(r=>r.status!=='ready').length;
  if(missing||unknown)result.push({rank:6,label:'Data · improve coverage',title:'Fill the gaps in your records',why:[missing?`${missing} forecast(s) need more completed months.`:'',unknown?`${unknown} product(s) lack enough stock-movement history.`:''].filter(Boolean).join(' '),next:'Record missing invoices, cash/bank transactions and stock movements, then refresh the data snapshot.',link:'warehouse',button:'Review data coverage'});
  if(!result.length)result.push({rank:7,label:'Routine review',title:'Keep a regular check on your plan',why:'No priority trigger was found in the available indicators. This is not a full business health check.',next:'Review open sales, upcoming payments and stock each week. Update this outlook when records change.',link:'sales',button:'Review sales invoices'});
  return result.sort((a,b)=>a.rank-b.rank);
}
function inventoryAdvice(r){
  if(r.status!=='ready')return 'Record at least 30 days of stock movements before estimating demand.';
  if(r.purchase_requirement_units>0)return `Review an order of ${num(r.purchase_requirement_units)} units; deduct any stock already on order.`;
  if(!r.daily_demand)return 'No outgoing stock recorded in the recent window. Confirm movements are complete.';
  return 'No extra order suggested by this estimate. Keep checking demand.';
}
function customerAdvice(r){
  if(r.indicator==='at_risk')return 'Contact the customer and ask about their next requirement.';
  if(r.indicator==='insufficient_history')return 'Build history: needs two invoices and at least 180 days since the first sale.';
  return 'Continue normal follow-up; no inactivity trigger in the last 90 days.';
}
if(typeof module!=='undefined'&&module.exports)module.exports={actions,inventoryAdvice,customerAdvice,esc};
if(typeof document==='undefined')return;
const $=id=>document.getElementById(id),app=$('outlookApp');if(!app)return;
let currency='INR';
const money=v=>v==null?'—':new Intl.NumberFormat(undefined,{style:'currency',currency,maximumFractionDigits:0}).format(v);
const link=k=>k.startsWith('#')?k:app.dataset[k];
function table(headers,rows,empty){return rows.length?'<div class="bi-scroll" tabindex="0" role="region" aria-label="Scrollable details"><table class="bi-table"><thead><tr>'+headers.map(x=>'<th scope="col">'+esc(x)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(x=>'<td>'+esc(x)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>':'<p class="bi-empty">'+esc(empty)+'</p>';}
function chart(p,fmt){
 const actual=p.history.slice(-12),future=p.forecast;if(!actual.length)return '';
 const all=[...actual.map(r=>r.actual),...future.map(r=>r.value)],lo=Math.min(0,...all),hi=Math.max(1,...all),x=i=>60+i*410/Math.max(1,all.length-1),y=v=>125-(v-lo)*100/(hi-lo||1);
 const points=(values,start)=>values.map((v,i)=>x(start+i)+','+y(v)).join(' ');
 return `<svg class="bi-chart" viewBox="0 0 500 155" role="img" aria-label="Historical monthly values followed by a flat estimate based on the recent three-month average. The exact figures are in the table below."><text x="2" y="25" font-size="9" fill="currentColor">${esc(fmt(hi))}</text><text x="2" y="125" font-size="9" fill="currentColor">${esc(fmt(lo))}</text><line x1="60" x2="470" y1="${y(0)}" y2="${y(0)}" stroke="#a9bcb5"/><polyline points="${points(actual.map(r=>r.actual),0)}" fill="none" stroke="#14826a" stroke-width="3"/><polyline points="${points([actual.at(-1).actual,...future.map(r=>r.value)],actual.length-1)}" fill="none" stroke="#a77700" stroke-width="3" stroke-dasharray="6 4"/><text x="60" y="148" font-size="10" fill="currentColor">${esc(actual[0].month)}</text><text x="470" y="148" text-anchor="end" font-size="10" fill="currentColor">${esc(future.at(-1).month)}</text></svg><div class="outlook-chart-legend"><span>Recorded history</span><span>Monthly estimate</span></div>`;
}
function forecastCard(title,p,kind,d){
 const fmt=kind==='count'?(v=>v==null?'�':Math.round(v).toLocaleString()):money;
 const meaning=kind==='cash'?'Cash and bank money in minus money out. This is not profit or your closing balance.':kind==='count'?'Number of invoices, not products or customers. Includes sales and repair invoices.':'Total invoiced value, including tax and repair bills. This is not cash collected or profit.';
 if(!ready(p))return `<article class="bi-panel outlook-card"><h3>${esc(title)}</h3><p class="outlook-tag neutral">More history needed</p><p>${esc(p?.months_available??0)} of ${esc(p?.months_required??6)} completed months available.</p><p>${meaning}</p><p>Record earlier ${kind==='cash'?'cash and bank transactions':'invoices'} and refresh source data. We will show an estimate once enough history exists.</p></article>`;
 const first=p.forecast[0],last=p.history.at(-1),delta=last?.actual>0?(first.value-last.actual)/last.actual*100:null;
 const comparison=delta==null?'A percentage comparison is not meaningful against a zero or negative previous month.':`${num(Math.abs(delta))}% ${delta>=0?'above':'below'} ${month(last.month)}.`;
 const uncertainty=p.backtest_mae===0?'Recent tests had no error. Future results can still change.':`In recent tests, the estimate missed actual results by ${fmt(p.backtest_mae)} per month on average.`;
 return `<article class="bi-panel outlook-card"><h3>${esc(title)}</h3><div class="bi-number">${kind==='count'?'About ':''}${esc(fmt(first.value))}</div><p><strong>${esc(month(first.month))}</strong>${first.month===d.as_of?.slice(0,7)?' · current month estimate':''}</p><p>${esc(comparison)}</p><p>${meaning}</p><p class="outlook-note"><strong>Allow for variation</strong><br>Planning range: ${esc(fmt(first.low))} to ${esc(fmt(first.high))}.<br>${esc(uncertainty)} This is not a guaranteed range or a confidence percentage.</p><details><summary>View trend, monthly estimates & calculation</summary>${chart(p,fmt)}${table(['Month','Estimate','Planning range'],p.forecast.map(r=>[month(r.month),fmt(r.value),fmt(r.low)+' to '+fmt(r.high)]))}<p>Each estimate uses the average of the last three completed months. It stays flat because this method does not predict growth or seasonality. The current partial month is excluded.</p><p>The range adds and subtracts twice the average test error from the last three completed months. Longer horizons carry more uncertainty, even though this simple range stays the same.</p>${table(['Recorded month','Actual'],p.history.slice(-12).map(r=>[month(r.month),fmt(r.actual)]))}</details></article>`;
}
function render(d){
 const tasks=actions(d),demand=[...(d.inventory_demand||[])].sort((a,b)=>(b.purchase_requirement_units||0)-(a.purchase_requirement_units||0));
 const customers=[...(d.customer_risk||[])].sort((a,b)=>(b.indicator==='at_risk')-(a.indicator==='at_risk'));
 const riskLabels={at_risk:'Follow up',active:'Recent activity',insufficient_history:'Not enough history'};
 $('results').innerHTML=`<section id="priorities" class="outlook-section"><h2>What to work on next</h2><p>Start with the first item. Suggestions are based on the records available, not confirmed outcomes.</p><div class="outlook-priorities">${tasks.map((a,i)=>`<article class="outlook-action"><span class="outlook-tag ${a.rank>=6?'neutral':''}">${i+1} · ${esc(a.label)}</span><h3>${esc(a.title)}</h3><p>${esc(a.why)}</p><p><strong>Next step:</strong> ${esc(a.next)}</p><a class="outlook-link" href="${esc(link(a.link))}">${esc(a.button)} →</a></article>`).join('')}</div></section>
 <section id="forecast-section" class="outlook-section"><h2>What the next months may look like</h2><p>Use these as starting points for planning. Open a card for the figures and calculation.</p><div class="outlook-cards">${forecastCard('Monthly invoiced sales',d.revenue_forecast,'revenue',d)}${forecastCard('Invoices per month',d.sales_forecast,'count',d)}${forecastCard('Monthly net cash movement',d.cash_flow_forecast,'cash',d)}</div></section>
 <section id="planning-details" class="outlook-section"><h2>Where to take action</h2><p>Review the specific products and customers behind the suggestions.</p>
 <div class="bi-panel outlook-section" id="stock-details"><h3>Stock to review</h3><p>Uses outgoing stock movements over up to 90 days. Suggested orders include demand during supplier delivery time and your reorder buffer; open purchase orders are not deducted.</p>${table(['Product','Stock now','Estimated days left','Suggested order','What to do'],demand.map(r=>[r.name,num(r.current_units),r.status!=='ready'?'Not estimated':r.stockout_in_days==null?'No recent usage':num(r.stockout_in_days)+' days',r.status==='ready'?num(r.purchase_requirement_units)+' units':'Not estimated',inventoryAdvice(r)]),'No products in the snapshot. Add stock items and refresh source data.')}<p><a class="outlook-link" href="${esc(link('stock'))}">Open inventory →</a></p></div>
 <div class="bi-panel outlook-section" id="customer-details"><h3>Customers to follow up with</h3><p>The inactivity rule flags established customers with no invoice in over 90 days. It cannot tell whether someone will leave.</p>${table(['Customer','Recorded invoices','Last invoice','Review status','What to do'],customers.map(r=>[r.name,num(r.invoices),r.days_since_last_sale==null?'No invoices recorded':num(r.days_since_last_sale)+' days ago',riskLabels[r.indicator]||'Review history',customerAdvice(r)]),'No customers in the snapshot. Add customer records and refresh source data.')}<p><a class="outlook-link" href="${esc(link('crm'))}">Open CRM →</a></p></div></section>
 <section class="bi-panel outlook-section" id="unusual-months"><h2>Months worth checking</h2><p>A large change may be a one-off sale or incomplete records. It is not evidence of an error or fraud.</p>${d.anomalies?.status==='ready'?table(['Month','Invoiced sales','Difference from typical month'],d.anomalies.flags.map(r=>[month(r.month),money(r.value),money(r.deviation)]),'No unusual months were flagged by this rule.'): `<p>Needs ${esc(d.anomalies?.months_required??8)} completed months; ${esc(d.anomalies?.months_available??0)} available.</p>`}</section>
 <section class="bi-panel outlook-section"><h2>How to use this page</h2><div class="outlook-explainer"><div><h3>1. Check the data date</h3><p>The outlook uses a saved snapshot. New invoices and other changes appear after you refresh source data, then update this outlook.</p></div><div><h3>2. Review the suggestions</h3><p>Confirm quantities, due dates and customer context in the relevant module before acting. A forecast is an estimate, not a promise.</p></div><div><h3>3. Compare with what happens</h3><p>Review monthly results against the estimate. Better records improve the usefulness of the outlook.</p></div></div><details><summary>Data and calculation notes</summary><ul>${(d.assumptions||[]).map(s=>'<li class="bi-muted">'+esc(s)+'</li>').join('')}</ul></details></section>`;
}
async function load(e){
 e?.preventDefault();if(!$('outlookControls').reportValidity())return;
 $('update').disabled=true;$('results').setAttribute('aria-busy','true');$('results').replaceChildren();$('predictionStatus').textContent='Preparing your business outlook…';
 try{
  const response=await fetch('/api/bi/v1/predictive?'+new URLSearchParams({lead_days:$('lead').value,horizon:$('horizon').value}));
  const d=await response.json();if(!response.ok)throw Error(d.error||'The outlook could not be loaded.');
  currency=d.currency||'INR';render(d);
  const snapshot=d.warehouse_last_success?new Date(d.warehouse_last_success).toLocaleString():'Not available';
  $('predictionStatus').textContent='Data snapshot: '+snapshot+' · Outlook as of '+d.as_of+(d.warehouse_warning?' · Data needs attention':'');
 }catch(error){$('predictionStatus').textContent='Outlook unavailable';$('results').innerHTML=`<section class="outlook-error"><h2>We could not prepare the outlook</h2><p>${esc(error.message)}</p><p>Check your connection or open source data to review the latest refresh. Then try Update outlook again.</p><a class="outlook-link" href="${esc(link('warehouse'))}">Open data refresh →</a></section>`;}
 finally{$('update').disabled=false;$('results').setAttribute('aria-busy','false');}
}
$('outlookControls').addEventListener('submit',load);load();
})(typeof globalThis!=='undefined'?globalThis:this);
