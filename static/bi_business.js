(function () {
  'use strict';
  const palette = ['#2563eb', '#7c3aed', '#0d9488', '#ea580c', '#db2777', '#0891b2', '#b45309', '#4f46e5'];
  function bounds(chart) {
    const values = chart.series.flatMap(s => s.values);
    if (!chart.labels.length || !values.length || values.some(v => typeof v !== 'number' || !Number.isFinite(v))) return null;
    let min = Math.min(0, ...values), max = Math.max(0, ...values);
    if (min === max) max = 1; // Axis scale only; never adds a data point.
    const padding = (max - min) * .08;
    return {min: min < 0 ? min - padding : min, max: max > 0 ? max + padding : max};
  }
  function csv(chart) {
    const cell = value => {
      let s = String(value);
      if (typeof value !== 'number' && /^[\s]*[=+\-@]/.test(s)) s = "'" + s;
      return '"' + s.replace(/"/g, '""') + '"';
    };
    const rows = [['Category / period', ...chart.series.map(s => s.name + (chart.currency ? ' (' + chart.currency + ')' : ''))],
      ...chart.labels.map((label, i) => [label, ...chart.series.map(s => s.values[i])])];
    return rows.map(row => row.map(cell).join(',')).join('\r\n');
  }
  if (typeof module !== 'undefined' && module.exports) { module.exports = {bounds, csv}; return; }
  const source = document.getElementById('business-chart-data');
  if (!source) return;
  const modules = JSON.parse(source.textContent);
  const charts = new Map();
  modules.forEach(m => (m.charts || []).forEach((chart, i) => charts.set(m.key + '-' + i, chart)));
  const ns = 'http://www.w3.org/2000/svg';
  function element(tag, attrs, label) {
    const node = document.createElementNS(ns, tag);
    Object.entries(attrs || {}).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (label !== undefined) node.textContent = String(label);
    return node;
  }
  const format = (v, c) => (c.currency ? c.currency + ' ' : '') + v.toLocaleString(undefined, {maximumFractionDigits:c.unit === 'money' ? 2 : 0});
  function render(id, type) {
    const chart = charts.get(id), host = document.getElementById('chart-' + id);
    if (!chart || !host) return;
    const range = bounds(chart);
    if (!range) { host.textContent = 'No chart data. See source notes below.'; return; }
    // Categories get distinct colours; time series keep one colour across dates.
    const categorical = type === 'bar' && chart.series.length === 1 && chart.kind !== 'line';
    const legend = host.parentElement.querySelector('.business-chart-legend');
    if (legend) {
      legend.replaceChildren();
      (categorical ? chart.labels : chart.series.map(s => s.name)).forEach((label, i) => {
        const item = document.createElement('span'), swatch = document.createElement('i');
        swatch.style.background = palette[i % palette.length];
        item.append(swatch, document.createTextNode(label));
        legend.appendChild(item);
      });
    }
    const width = 800, height = 310, left = 76, right = 20, top = 16, bottom = 66;
    const plotW = width - left - right, plotH = height - top - bottom;
    const y = value => top + (range.max - value) / (range.max - range.min) * plotH;
    const step = plotW / chart.labels.length;
    const x = i => left + step * (i + .5);
    const svg = element('svg', {viewBox:`0 0 ${width} ${height}`, role:'img', 'aria-label':chart.title});
    svg.appendChild(element('title', {}, chart.title + '. ' + chart.scope + '. ' + chart.note));
    for (let tick = 0; tick <= 4; tick++) {
      const value = range.min + (range.max - range.min) * tick / 4;
      svg.appendChild(element('line', {x1:left,x2:width-right,y1:y(value),y2:y(value),class:'chart-grid'}));
      svg.appendChild(element('text', {x:left-8,y:y(value)+4,'text-anchor':'end'}, value.toLocaleString(undefined,{notation:'compact',maximumFractionDigits:1})));
    }
    svg.appendChild(element('line', {x1:left,x2:width-right,y1:y(0),y2:y(0),stroke:'currentColor','stroke-opacity':'.35'}));
    chart.labels.forEach((label, i) => {
      if (i % Math.ceil(chart.labels.length / 7) !== 0 && i !== chart.labels.length - 1) return;
      const short = label.length > 17 ? label.slice(0,15) + '…' : label;
      const text = element('text', {x:x(i),y:height-bottom+22,'text-anchor':'middle'},short);
      text.appendChild(element('title',{},label));
      svg.appendChild(text);
    });
    chart.series.forEach((series, si) => {
      const color = palette[si % palette.length];
      if (type === 'line') {
        const points = series.values.map((value,i) => `${x(i)},${y(value)}`).join(' ');
        svg.appendChild(element('polyline',{points,fill:'none',stroke:color,'stroke-width':2.5}));
      }
      series.values.forEach((value,i) => {
        const label = chart.labels[i] + ' · ' + series.name + ': ' + format(value, chart);
        let mark;
        if (type === 'line') {
          mark = element('circle',{cx:x(i),cy:y(value),r:4,fill:color,tabindex:0,'aria-label':label});
        } else {
          const barW = step * .72 / chart.series.length;
          mark = element('rect',{x:left+step*i+step*.14+barW*si,y:Math.min(y(0),y(value)),
            width:Math.max(.3,barW-2),height:Math.abs(y(value)-y(0)),rx:4,fill:categorical ? palette[i % palette.length] : color,tabindex:0,'aria-label':label});
        }
        mark.appendChild(element('title',{},label));
        svg.appendChild(mark);
      });
    });
    host.replaceChildren(svg);
  }
  document.querySelectorAll('.business-chart-plot').forEach(host => {
    const id = host.dataset.module + '-' + host.dataset.index;
    render(id, charts.get(id).kind);
  });
  document.querySelectorAll('.business-chart-type').forEach(select => select.addEventListener('change', () => render(select.dataset.chartId,select.value)));
  document.querySelectorAll('.business-export').forEach(button => button.addEventListener('click', () => {
    const chart = charts.get(button.dataset.chartId);
    if (!chart) return;
    const url = URL.createObjectURL(new Blob(['\uFEFF'+csv(chart)],{type:'text/csv;charset=utf-8'}));
    const a = document.createElement('a'); a.href = url; a.download = 'qiyadah-bi-' + button.dataset.chartId + '.csv';
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url),1000);
  }));
})();
