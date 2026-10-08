const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const context=vm.createContext({window:{}});
vm.runInContext(fs.readFileSync('static/bi_builder_charts.js','utf8'),context);
const charts=context.window.BICharts;
const esc=v=>String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const opts={esc,format:v=>String(v),colors:['#117965','#e9bd18']};
const rows=[{key:'a',name:'Alpha',value:80},{key:'b',name:'Beta',value:20}];
test('pie and donut are scalable SVGs with actual slice labels and drill targets',()=>{
 for(const style of ['pie','donut'])for(const label_position of ['auto','outside','inside','center']){
  const html=charts.renderRing({style,label_position,show_values:true,label_mode:'category_value'},rows,opts);
  assert.match(html,/viewBox=/);assert.match(html,/Alpha/);assert.match(html,/data-bi-group="a"/);
  assert.doesNotMatch(html,/NaN|undefined|conic-gradient/);
 }
});
test('single slice draws a full ring and zero or negative totals are handled',()=>{
 assert.match(charts.renderRing({style:'donut'},[rows[0]],opts),/<circle/);
 assert.match(charts.renderRing({},[{value:0}],opts),/No positive/);
 assert.match(charts.renderRing({},[{value:-1}],opts),/nonnegative/);
});
test('category color follows its key when data order changes',()=>{
 const w={category_colors:{b:'#ff0033'}};
 assert.equal(charts.color(w,rows[1],0,opts.colors),'#ff0033');
 assert.match(charts.renderRing({...w,style:'pie'},[rows[1],rows[0]],opts),/fill="#ff0033"/);
});
test('all shared chart styles render with saved category and series colors',()=>{
 for(const style of ['bar','column','line','area','grouped_bar','grouped_column','stacked_column','stacked_bar','combo','step_line','spline_line','curved_area','lollipop','radar','polar_area']){
  const html=charts.render({style,h:7,show_values:true,label_position:'center',series_colors:{value:'#cc00ff'},category_colors:{a:'#ff0033'}},[...rows,{key:'c',name:'Gamma',value:40}],[{key:'value',label:'Sales'}],opts);
  assert.doesNotMatch(html,/NaN|undefined/);assert.match(html,/#cc00ff|#ff0033/);
 }
});
test('inside labels use contrast and donut hole size changes geometry',()=>{
 assert.equal(charts.contrast('#000000'),'#ffffff');assert.equal(charts.contrast('#ffffff'),'#163a34');
 assert.notEqual(charts.renderRing({style:'donut',donut_hole:20},rows,opts),charts.renderRing({style:'donut',donut_hole:80},rows,opts));
});

test('resized columns use card dimensions instead of a fixed wide viewBox',()=>{
 for(const width of [300,480,800])for(const height of [180,350]){
  const html=charts.render({style:'column',_plot_width:width,_plot_height:height},rows,[{key:'value',label:'Value'}],opts);
  const box=html.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/);
  const legend=Math.min(150,Math.max(70,width*.28));
  assert.equal(Number(box[1]),width-legend-8);assert.equal(Number(box[2]),height);
  assert.doesNotMatch(html,/NaN|undefined/);
 }
 const html=charts.render({style:'column',_plot_width:480,_plot_height:250,show_legend:false},rows,[{key:'value',label:'Value'}],opts);
 assert.match(html,/viewBox="0 0 480 250"/);
});

test('long category labels wrap or abbreviate while full names remain available',()=>{
 assert.equal(charts.axisLines('Reliance Corporate Fleet','wrap',12).length,2);
 assert.equal(charts.axisLines('Reliance Corporate Fleet','abbreviate',12)[0],'RCF');
 for(const mode of ['wrap','abbreviate','truncate']){
  const html=charts.render({style:'column',axis_label_mode:mode,_plot_width:480,_plot_height:250},[{key:'r',name:'Reliance Corporate Fleet',value:10}],[{key:'value',label:'Value'}],opts);
  assert.match(html,/<tspan/);assert.match(html,/<title>Reliance Corporate Fleet<\/title>/);assert.match(html,/pb-legend-text">Reliance Corporate Fleet/);
 }
});
test('all shared chart styles render finite geometry at resized dimensions',()=>{
 for(const style of ['bar','column','line','area','step_line','spline_line','curved_area','stacked_bar','stacked_column','grouped_column','grouped_bar','combo','lollipop','radar','polar_area']){
  for(const width of [300,700])for(const height of [180,360]){
   const html=charts.render({style,_plot_width:width,_plot_height:height},[...rows,{key:'c',name:'Gamma',value:30}],[{key:'value',label:'Value'}],opts);
   assert.doesNotMatch(html,/NaN|undefined|Infinity/);
   const box=html.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/);
   assert.ok(Number(box[1])<=width,style);assert.equal(Number(box[2]),height,style);
  }
 }
});

test('grid colour applies to rectangular and radial chart grids',()=>{
 for(const style of ['column','bar','line','radar','polar_area']){
  const html=charts.render({style,grid_color:'#ab1234'},[...rows,{key:'c',name:'Gamma',value:30}],[{key:'value',label:'Value'}],opts);
  assert.match(html,/stroke="#ab1234" opacity="1"/);
 }
});
