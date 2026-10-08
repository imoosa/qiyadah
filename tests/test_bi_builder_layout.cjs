const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync('templates/bi_builder.html', 'utf8');
function setup(widgets=[]) {
  const c=vm.createContext({state:{widgets}, $:()=>({clientWidth:1200,clientLeft:1,clientTop:1,getBoundingClientRect:()=>({left:20,top:40})})});
  vm.runInContext(source.slice(source.indexOf('const inside='),source.indexOf('function styles(')),c);
  vm.runInContext(source.slice(source.indexOf('function gridMetrics('),source.indexOf('function removePreview(')),c);
  return c;
}
test('manual placement preserves positions between grid lines',()=>{
  const c=setup(),w={id:'a',w:6,h:3};
  assert.equal(c.place(w,2.37,4.61,false),true);
  assert.equal(w.x,2.37);assert.equal(w.y,4.61);
});
test('collision does not relocate the visual upward',()=>{
  const c=setup([{id:'b',x:0,y:4,w:6,h:4}]),w={id:'a',x:10,y:10,w:6,h:3};
  assert.equal(c.place(w,0,5,false),false);
  assert.equal(w.x,10);assert.equal(w.y,10);
});
test('pointer coordinates preserve sub-grid movement including canvas border',()=>{
  const c=setup(),m=c.gridMetrics(),p=c.pointAt(35+2.37*m.stepX,55+4.61*m.stepY);
  assert.ok(Math.abs(p[0]-2.37)<1e-10);assert.ok(Math.abs(p[1]-4.61)<1e-10);
});
test('builder script parses',()=>{
  for(const match of source.matchAll(/<script>([\s\S]*?)<\/script>/g))
    new vm.Script(match[1].replace(/\{\{[\s\S]*?\}\}/g,'null'));
});


test('Design and its tools remain inside the right sidebar',()=>{
  const html=source.slice(source.indexOf('{% block content %}'),source.indexOf('{% block extra_script %}'));
  const stack=[],parents={};
  for(const match of html.matchAll(/<(\/?)([a-z][a-z0-9]*)\b([^>]*)>/gi)){
    const [,closing,tag,attrs]=match;
    if(closing){assert.equal(stack.pop()?.tag,tag,`Unbalanced closing ${tag}`);continue;}
    const id=attrs.match(/\bid="([^"]+)"/)?.[1];
    if(id)parents[id]=stack.map(node=>node.className||node.id);
    if(!['input','img','br','hr','meta','link'].includes(tag))stack.push({tag,id,className:attrs.match(/\bclass="([^"]+)"/)?.[1]});
  }
  assert.equal(stack.length,0);
  for(const id of ['pbDatabasePanel','pbDesignPanel','pbDockPanelVisuals','pbDockPanelTheme'])assert.ok(parents[id].includes('pb-studio-dock'),id);
  assert.ok(parents.pbDockPanelVisuals.includes('pbDesignPanel'));
});

test('sidebar tabs reveal Design and all three tool tabs switch correctly',()=>{
  const elements={};
  const $=id=>elements[id]||={hidden:false,classList:{toggle(){}},setAttribute(){},addEventListener(){}};
  const c=vm.createContext({$,document:{querySelectorAll:()=>[]}});
  vm.runInContext(source.slice(source.indexOf('let fieldsExpanded=false;'),source.indexOf('function renderDataExplorer()')),c);
  c.switchSidebarPanel('design');assert.equal($('pbDesignPanel').hidden,false);assert.equal($('pbDatabasePanel').hidden,true);
  for(const tab of ['dropzones','visuals','theme']){
    c.switchDockTab(tab);
    for(const [name,id] of [['dropzones','pbDockPanelDropzones'],['visuals','pbDockPanelVisuals'],['theme','pbDockPanelTheme']])assert.equal($(id).hidden,name!==tab);
  }
  c.setFieldsExpanded(true);
  assert.equal($('pbDesignPanel').hidden,false);assert.equal($('pbDatabasePanel').hidden,false);
  c.switchDockTab('dropzones');assert.equal($('pbDatabasePanel').hidden,false);
  c.setFieldsExpanded(false);assert.equal($('pbDatabasePanel').hidden,true);assert.equal($('pbDesignPanel').hidden,false);
  c.switchSidebarPanel('database');assert.equal($('pbDesignPanel').hidden,true);assert.equal($('pbDatabasePanel').hidden,false);
});
