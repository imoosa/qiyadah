const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync('templates/bi_builder.html', 'utf8');
const line = prefix => {
  const start=source.indexOf(prefix);
  if(prefix.startsWith('async function')) return source.slice(start,source.indexOf('\n}',start)+2);
  return source.slice(start,source.indexOf('\n});',start)+4);
};
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => {resolve=a;reject=b}); return {promise,resolve,reject}; };
function setup() {
  const elements = {};
  const context = vm.createContext({JSON, Object, URLSearchParams, console,
    state: {id: 1, revision: 1, widgets: [], background: 'canvas_light', dirty: true, data: {old: true}},
    dataRequest: 0, visualRequest: 0, dashboardRequest: 0,
    $: id => elements[id] ||= {value: '', addEventListener(type, handler) {this[type] = handler}},
    status() {}, render() {}, saved: async () => {}, loadVisuals: async () => {},
    filterQuery: () => new URLSearchParams(),
  });
  context.$('pbSaved').value = '1'; context.$('pbTitle').value = 'Original'; context.$('pbVisibility').value = 'private';
  context.$('pbFrom').value = '2026-01-01'; context.$('pbTo').value = '2026-09-25';
  vm.runInContext(line("$('pbSave').addEventListener"), context);
  vm.runInContext(line('async function loadData()'), context);
  return context;
}
test('editing while a save is pending retains unsaved changes', async () => {
  const c=setup(), request=deferred(); c.api=()=>request.promise;
  const save=c.$('pbSave').click(); c.$('pbTitle').value='Newer title';
  request.resolve({id:1,revision:2,title:'Original'}); await save;
  assert.equal(c.state.dirty,true); assert.equal(c.state.revision,2);
});
test('save completion cannot replace a newly selected dashboard', async () => {
  const c=setup(), request=deferred(); c.api=()=>request.promise;
  const save=c.$('pbSave').click(); c.dashboardRequest++; c.state.id=8;
  request.resolve({id:1,revision:2,title:'Original'}); await save;
  assert.equal(c.state.id,8);
});
test('failed refresh clears previous figures and exposes the error', async () => {
  const c=setup(); c.api=async()=>{throw Error('Unavailable')}; await c.loadData();
  assert.equal(c.state.data,null); assert.equal(c.state.dataError,'Unavailable');
});
test('older data response cannot overwrite a newer filter selection', async () => {
  const c=setup(), first=deferred(), second=deferred(); let count=0;
  c.api=()=> (++count===1 ? first.promise : second.promise);
  const a=c.loadData(), b=c.loadData(); second.resolve({version:2}); await b;
  first.resolve({version:1}); await a; assert.equal(c.state.data.version,2);
});
test('invalid dates clear old data without querying', async () => {
  const c=setup(); c.$('pbFrom').value='2027-01-01'; c.api=()=>assert.fail('unexpected query');
  await c.loadData(); assert.equal(c.state.data,null); assert.match(c.state.dataError,/From date/);
});
test('all three BI page scripts parse', () => {
  for(const name of ['bi_builder','bi_warehouse','bi_predictive']) {
    const html=fs.readFileSync(`templates/${name}.html`,'utf8');
    for(const match of html.matchAll(/<script>([\s\S]*?)<\/script>/g))
      new vm.Script(match[1].replace(/\{\{[\s\S]*?\}\}/g,'null'));
  }
});

test('changing source uses a valid amount measure instead of alphabetically first count', () => {
  const c=setup(), widget={id:'chart',type:'chart',key:'custom',semantic_measure:'subtotal'};
  c.state.visuals={}; c.active=()=>widget; c.mark=()=>{};
  c.semanticCatalog={sources:{purchase:{measures:{count:'Count',subtotal:'Purchase cost'},dimensions:{period:'Date'}}}};
  vm.runInContext(line("$('pbSettings').addEventListener('change'"),c);
  c.$('pbSettings').change({target:{id:'pbSemanticSource',value:'purchase',dataset:{}}});
  assert.equal(widget.semantic_measure,'subtotal'); assert.equal(widget.semantic_aggregation,'sum');
  assert.equal(widget.title,'Purchase cost');
});

test('choosing a new primary measure replaces the previous primary', () => {
  const c=setup(), widget={id:'chart',type:'chart',key:'custom',semantic_source:'sales',semantic_measure:'subtotal',semantic_measures:['subtotal','count']};
  c.state.visuals={}; c.active=()=>widget; c.mark=()=>{};
  c.semanticCatalog={sources:{sales:{measures:{subtotal:'Net sales',tax_amount:'Sales tax',count:'Invoice count'}}}};
  vm.runInContext(line("$('pbSettings').addEventListener('change'"),c);
  c.$('pbSettings').change({target:{id:'pbSemanticMeasure',value:'tax_amount',dataset:{}}});
  assert.deepEqual(Array.from(widget.semantic_measures),['tax_amount','count']);
  assert.equal(widget.title,'Sales tax / Invoice count');
});

function chartRenderer() {
  const c=vm.createContext({window:{}});
  vm.runInContext(fs.readFileSync('static/bi_builder_charts.js','utf8'),c);
  return (style,rows,series)=>c.window.BICharts.render({style},rows,series,{esc:String,format:String,colors:['teal','gold','blue']});
}
test('stacked bars are horizontal and retain clicked measure identity', () => {
  const html=chartRenderer()('stacked_bar',[{key:'Jan',name:'Jan',values:{sales:100,tax:20}}],
    [{key:'sales',label:'Sales'},{key:'tax',label:'Tax'}]);
  assert.match(html,/data-bi-measure="tax"/);
  const bars=[...html.matchAll(/<rect[^>]*width="([\d.]+)" height="([\d.]+)"/g)];
  assert.equal(bars.length,2); assert.ok(Number(bars[0][1])>Number(bars[0][2]));
});
test('combo draws every additional measure and negative values remain visible', () => {
  const html=chartRenderer()('combo',[{key:'Jan',name:'Jan',values:{sales:100,cost:60,profit:-5}}],
    [{key:'sales',label:'Sales'},{key:'cost',label:'Cost'},{key:'profit',label:'Profit'}]);
  assert.match(html,/Profit: -5/); assert.equal((html.match(/<path /g)||[]).length,2);
  assert.match(html,/data-bi-measure="profit"/);
});

test('save targets only the selected dashboard',async()=>{
  const c=setup();let path,method;
  c.api=async(p,m)=>{path=p;method=m;return {id:1,revision:2,title:'Original'}};
  await c.$('pbSave').click();assert.equal(path,'/api/bi/v1/builder/dashboards/1');assert.equal(method,'PUT');
});
test('save is blocked while another dashboard is loading',async()=>{
  const c=setup();c.$('pbSaved').value='2';c.api=()=>assert.fail('must not save the old dashboard');
  await c.$('pbSave').click();assert.equal(c.state.id,1);
});
test('KPI rejects dates and customer names without changing the card',()=>{
  const c=vm.createContext({status(){},mark(){assert.fail('incompatible field changed KPI')},render(){}});
  vm.runInContext(source.slice(source.indexOf('function assignFieldToWidget'),source.indexOf('/* ── Dropzones')),c);
  for(const field of ['period','customer']){
    const widget={type:'metric',key:'expenses',title:'Expenses'};
    c.assignFieldToWidget(widget,'sales',field,'dimension',field);
    assert.equal(widget.key,'expenses');assert.equal(widget.title,'Expenses');
  }
});

test('customer filter renders names, selected value and escaped labels',()=>{
  const c=setup();c.esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;');
  c.filterOptions={clients:[{id:7,name:'A & B <Customer>'}]};c.$('pbFocus').value='client_id';c.$('pbFocusValue').value='7';
  vm.runInContext(source.slice(source.indexOf('function filterLabel'),source.indexOf('function preview(w)')),c);
  const html=c.filterPreview({key:'client_id'});
  assert.match(html,/value="7" selected/);assert.match(html,/A &amp; B &lt;Customer>/);
});
test('canvas business and date filters update the shared query and refresh',()=>{
  const c=setup();let refreshes=0;c.mark=()=>{};c.loadData=()=>refreshes++;c.chooseFilter=()=>{c.$('pbFocusValue').value=''};
  vm.runInContext(line("$('pbCanvas').addEventListener('change'"),c);
  c.$('pbCanvas').change({target:{dataset:{businessFilter:'employee_id'},value:'42'}});
  assert.equal(c.$('pbFocus').value,'employee_id');assert.equal(c.$('pbFocusValue').value,'42');
  c.$('pbCanvas').change({target:{dataset:{filter:'from'},value:'2026-02-01'}});
  assert.equal(c.$('pbFrom').value,'2026-02-01');assert.equal(refreshes,2);
  c.$('pbCanvas').change({target:{dataset:{businessFilter:'employee_id'},value:''}});
  assert.equal(c.$('pbFocus').value,'');
});

test('successful save confirms the saved dashboard name',async()=>{
  const c=setup();c.api=async()=>({id:1,revision:2,title:'Sales Overview'});
  await c.$('pbSave').click();
  assert.equal(c.$('pbSaveFlash').hidden,false);
  assert.match(c.$('pbSaveFlash').textContent,/Saved your changes to/);
  assert.match(c.$('pbSaveFlash').textContent,/Sales Overview/);
});
test('failed save does not show a success confirmation',async()=>{
  const c=setup();c.api=async()=>{throw Error('Save failed')};
  await c.$('pbSave').click();assert.equal(c.$('pbSaveFlash').hidden,true);
});
