const assert=require('node:assert/strict');
const test=require('node:test');
const {actions,inventoryAdvice,customerAdvice,esc}=require('../static/bi_predictive.js');
const forecast=value=>({status:'ready',forecast:[{value}],history:[{actual:100}]});
const healthy=()=>({revenue_forecast:forecast(100),sales_forecast:forecast(10),cash_flow_forecast:forecast(50),inventory_demand:[],customer_risk:[],anomalies:{status:'ready',flags:[]}});
test('stale data comes before business actions',()=>{
 const d=healthy();d.warehouse_warning='Snapshot is stale';d.cash_flow_forecast=forecast(-100);
 const a=actions(d);assert.equal(a[0].link,'warehouse');assert.equal(a[1].link,'cash');
 assert.match(a[1].why,/does not tell us your bank balance/);
});
test('missing history is actionable and never means all clear',()=>{
 const d=healthy();d.revenue_forecast={status:'insufficient_history'};d.inventory_demand=[{status:'insufficient_history'}];
 assert.equal(actions(d)[0].label,'Data · improve coverage');
 assert.match(inventoryAdvice(d.inventory_demand[0]),/30 days/);
});
test('stock recommendations account for orders in transit',()=>{
 assert.match(inventoryAdvice({status:'ready',purchase_requirement_units:8}),/8 units; deduct any stock already on order/);
 assert.match(inventoryAdvice({status:'ready',purchase_requirement_units:0,daily_demand:0}),/Confirm movements are complete/);
});
test('customer history gaps do not label someone at risk',()=>{
 const d=healthy();d.customer_risk=[{indicator:'insufficient_history'}];
 assert.equal(actions(d).some(a=>a.link==='#customer-details'),false);
 assert.match(customerAdvice(d.customer_risk[0]),/180 days/);
});
test('decline threshold avoids alarming on small changes or zero baseline',()=>{
 const d=healthy();d.revenue_forecast=forecast(95);assert.equal(actions(d).some(a=>a.link==='crm'),false);
 d.revenue_forecast=forecast(80);assert.equal(actions(d).some(a=>a.link==='crm'),true);
 d.revenue_forecast.history=[{actual:0}];assert.equal(actions(d).some(a=>a.link==='crm'),false);
});
test('names and server messages cannot insert HTML',()=>{
 assert.equal(esc('<img src=x onerror="alert(1)">'),'&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
});

const vm=require('node:vm');
const fs=require('node:fs');
async function renderResponse(data,ok=true){
 const elements={};
 for(const id of ['outlookApp','outlookControls','horizon','lead','update','results','predictionStatus'])elements[id]={dataset:{warehouse:'/warehouse',sales:'/sales',stock:'/stock',crm:'/crm',cash:'/cash'},value:id==='lead'?'14':'3',setAttribute(){},replaceChildren(){this.innerHTML=''},reportValidity:()=>true,addEventListener(){}};
 const context=vm.createContext({document:{getElementById:id=>elements[id]},URLSearchParams,Intl,Date,fetch:async()=>({ok,json:async()=>data})});
 vm.runInContext(fs.readFileSync('static/bi_predictive.js','utf8'),context);
 await new Promise(resolve=>setImmediate(resolve));
 return elements;
}
test('empty data renders useful next steps without invented figures',async()=>{
 const missing={status:'insufficient_history',months_available:0,months_required:6};
 const elements=await renderResponse({currency:'INR',as_of:'2026-09-27',revenue_forecast:missing,sales_forecast:missing,cash_flow_forecast:missing,inventory_demand:[],customer_risk:[],anomalies:{status:'insufficient_history',months_available:0,months_required:8}});
 assert.match(elements.results.innerHTML,/No products in the snapshot/);
 assert.match(elements.results.innerHTML,/More history needed/);
 assert.equal(elements.update.disabled,false);
});
test('API errors offer recovery and release the update control',async()=>{
 const elements=await renderResponse({error:'Refresh required <script>'},false);
 assert.match(elements.results.innerHTML,/Refresh required &lt;script&gt;/);
 assert.match(elements.results.innerHTML,/Open data refresh/);
 assert.equal(elements.update.disabled,false);
});
