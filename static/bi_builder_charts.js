/* Shared SVG renderer for selectable measures with enhanced chart varieties and responsive layout. */

window.BICharts = {

  axisLines(name, mode='wrap', capacity=14) {
    const text=String(name), limit=Math.max(3,Math.floor(capacity));
    const shorten=value=>value.length>limit?value.slice(0,limit-1)+'…':value;
    if(mode==='abbreviate')return [text.length<=limit?text:shorten(text.split(/\s+/).filter(Boolean).map(word=>word[0]).join('').toUpperCase())];
    if(mode==='truncate')return [shorten(text)];
    if(text.length<=limit)return [text];
    let split=text.lastIndexOf(' ',limit);if(split<1)split=limit;
    return [text.slice(0,split),shorten(text.slice(split).trim())];
  },

  color(w, row, index, colors, series=false) {

    const key=String(row.key ?? row.name), overrides=series?w.series_colors:w.category_colors;

    const candidate=overrides?.[key] || w.chart_color;

    return /^#[0-9a-f]{6}$/i.test(candidate||'') ? candidate : colors[index % colors.length];

  },

  contrast(color) {

    const rgb=(color.match(/[0-9a-f]{2}/gi)||[]).map(x=>parseInt(x,16));

    return rgb.length===3 && rgb[0]*.299+rgb[1]*.587+rgb[2]*.114>155?'#163a34':'#ffffff';

  },

  legendScale(w, itemCount = 1) {
    const wCols = Number(w.w) || 10;
    const hRows = Number(w.h) || 6;
    const plotH = Math.max(76, Number(w._plot_height) || (hRows * 52 - 64));
    const chartScale = Math.min(150, Math.max(50, Number(w.chart_scale) || 100)) / 100;
    const dimScale = Math.max(0.62, Math.min(1.85, (Math.min(wCols / 10, hRows / 6) * 0.65 + Math.sqrt((wCols * hRows) / 60) * 0.35))) * chartScale;
    const baseFont = Number(w.legend_font_size) || 11;
    const maxFitFont = Math.max(7.5, Math.floor((plotH - 8) / (Math.max(1, itemCount) * 1.42)));
    const fontSize = Math.max(7.5, Math.min(24, Math.min(+(baseFont * dimScale).toFixed(1), maxFitFont)));
    const swatchSize = Math.max(6, Math.round(fontSize * 0.82));
    const gap = Math.max(2, Math.round(fontSize * 0.32));
    return { fontSize, swatchSize, gap, dimScale };
  },

  renderVerticalLegend(w, items, {esc, colors, series = false}) {
    if (w.show_legend === false || !items || !items.length) return '';
    const { fontSize, swatchSize, gap } = this.legendScale(w, items.length);
    const legendColor = esc(w.legend_color || w.text_color || '#163a34');
    return `<div class="pb-chart-legend pb-chart-legend-vertical" style="font-size:${fontSize}px;color:${legendColor};gap:${gap}px;--pb-swatch-size:${swatchSize}px;">${items.map((item, i) => {
      const color = this.color(w, item, i, colors, series);
      const label = item.label ?? item.name ?? item.key ?? '';
      const extra = item.extra ? ` <strong style="opacity:.85;font-weight:700;">${esc(item.extra)}</strong>` : '';
      const groupAttr = item.groupKey != null ? ` tabindex="0" role="button" data-bi-group="${esc(item.groupKey)}"` : '';
      return `<span${groupAttr} title="${esc(label)}${item.extra ? ' · ' + esc(item.extra) : ''}"><i style="background:${color};width:${swatchSize}px;height:${swatchSize}px;"></i><b class="pb-legend-text">${esc(label)}</b>${extra}</span>`;
    }).join('')}</div>`;
  },

  renderRing(w, rows, {esc, format, colors}) {
    if(rows.some(r=>Number(r.value)<0))return '<p>Pie and donut need nonnegative values. Choose a bar or line chart.</p>';
    const total=rows.reduce((n,r)=>n+Math.max(0,Number(r.value)||0),0);
    if(!total)return '<p>No positive values for this chart.</p>';

    const position=w.label_position||'auto';
    const outside=w.show_values&&(position==='outside'||position==='auto'&&(rows.some(r=>Number(r.value)>0&&Number(r.value)/total<.10)||['category','category_value','category_percent'].includes(w.label_mode)));

    const totalW = Math.max(140, Number(w._plot_width) || ((Number(w.w) || 10) * 42 - 32));
    const totalH = Math.max(80, Number(w._plot_height) || ((Number(w.h) || 6) * 52 - 62 - (w.subtitle ? 20 : 0)));
    const hasLegend = w.show_legend !== false;
    const legendReserve = hasLegend ? Math.min(175, Math.max(68, totalW * 0.34)) : 0;

    const W = Math.max(90, Math.round(totalW - legendReserve));
    const H = Math.max(80, Math.round(totalH));
    const scalePct = Math.min(150, Math.max(50, Number(w.chart_scale) || 100)) / 100;
    const { dimScale } = this.legendScale(w, rows.length);
    const font = Math.max(8, Math.round((Number(w.data_label_font_size) || 12) * Math.min(1.25, Math.max(0.7, dimScale))));

    const cx = W / 2, cy = H / 2;
    const gutter = outside ? Math.min(64, W * 0.24) : 8;
    const maxRadius = Math.max(16, Math.min((W - 2 * gutter) / 2, (H - 12) / 2));
    const r = Math.max(14, maxRadius * 0.90 * scalePct);
    const hole = w.style === 'pie' ? 0 : r * (Number(w.donut_hole) || 60) / 100;

    let angle=-Math.PI/2,shapes='',labels='';const anchors=[];

    rows.forEach((row,i)=>{
      const v=Math.max(0,Number(row.value)||0);if(!v)return;
      const span=v/total*Math.PI*2,end=angle+span,mid=angle+span/2;
      const point=(radius,a)=>[cx+radius*Math.cos(a),cy+radius*Math.sin(a)];
      const a=point(r,angle),b=point(r,end),ia=point(hole,angle),ib=point(hole,end);
      const color=this.color(w,row,i,colors),attrs=`tabindex="0" role="button" data-bi-group="${esc(row.key??row.name)}"`;
      const title=`<title>${esc(row.name)}: ${esc(format(v))} (${(v/total*100).toFixed(1)}%)</title>`;

      if(span>=Math.PI*2-1e-8){shapes+=`<circle ${attrs} cx="${cx}" cy="${cy}" r="${hole?(r+hole)/2:r}" fill="${hole?'none':color}" stroke="${color}" stroke-width="${hole?r-hole:0}">${title}</circle>`;}
      else {const path=hole?`M${a} A${r},${r} 0 ${span>Math.PI?1:0} 1 ${b} L${ib} A${hole},${hole} 0 ${span>Math.PI?1:0} 0 ${ia} Z`:`M${cx},${cy} L${a} A${r},${r} 0 ${span>Math.PI?1:0} 1 ${b} Z`;shapes+=`<path ${attrs} d="${path}" fill="${color}" stroke="${esc(w.card_color||'#ffffff')}" stroke-width="1">${title}</path>`;}

      const pct=(v/total*100).toFixed(1)+'%',mode=w.label_mode||'percent';
      const text=mode==='value'?format(v):mode==='both'?pct+' · '+format(v):mode==='category'?row.name:mode==='category_value'?row.name+' · '+format(v):mode==='category_percent'?row.name+' · '+pct:pct;

      if(w.show_values){
        if(outside)anchors.push({mid,text,title,color,side:Math.cos(mid)>=0?1:-1,y:cy+Math.sin(mid)*(r+14)});
        else {const radius=w.label_position==='center'?(hole+r)/2:hole+(r-hole)*.65,pt=point(radius,mid);labels+=`<text x="${pt[0]}" y="${pt[1]}" dominant-baseline="middle" text-anchor="middle" font-size="${font}" fill="${esc(w.data_label_color||this.contrast(color))}">${title}${esc(text)}</text>`;}
      }
      angle=end;
    });

    for(const side of [-1,1]){
      const list=anchors.filter(a=>a.side===side).sort((a,b)=>a.y-b.y),gap=font+5;
      list.forEach((a,i)=>a.y=Math.max(a.y,i?list[i-1].y+gap:font+6));
      if(list.length){const shift=Math.max(0,list.at(-1).y-(H-font-6));list.forEach(a=>a.y-=shift);}
      list.forEach(a=>{const x=cx+side*(r+16),sx=cx+Math.cos(a.mid)*r,sy=cy+Math.sin(a.mid)*r;
        const maxChars=Math.max(6,Math.floor((W/2-r-20)/(font*.55))),full=String(a.text),short=full.length>maxChars?full.slice(0,maxChars-1)+'…':full;
        labels+=`<path d="M${sx},${sy} L${cx+side*(r+8)},${a.y} L${x},${a.y}" fill="none" stroke="${a.color}"/><text x="${x+side*3}" y="${a.y}" dominant-baseline="middle" text-anchor="${side>0?'start':'end'}" font-size="${font}" fill="${esc(w.data_label_color||w.text_color||'#163a34')}"><title>${esc(full)}</title>${esc(short)}</text>`;
      });
    }

    const subtitleFontSize = Number(w.subtitle_font_size) || 11;
    const subtitleColor = esc(w.subtitle_color || '#527467');
    const subtitleHtml = w.subtitle ? `<p class="pb-chart-subtitle" style="font-size:${subtitleFontSize}px;color:${subtitleColor};margin:0 0 4px;flex:none;">${esc(w.subtitle)}</p>` : '';

    const legendItems = rows.map(row => {
      const v = Math.max(0, Number(row.value) || 0);
      const pct = (v / total * 100).toFixed(1) + '%';
      return {
        key: row.key ?? row.name,
        name: row.name,
        label: row.name,
        extra: w.label_mode === 'value' ? format(v) : pct,
        groupKey: row.key ?? row.name
      };
    });
    const legend = this.renderVerticalLegend(w, legendItems, {esc, colors, series: false});

    return `${subtitleHtml}<div class="pb-chart-body-flex"><svg class="pb-chart-svg pb-ring-svg" preserveAspectRatio="xMidYMid meet" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(w.title||w.style)}">${shapes}${labels}</svg>${legend}</div>`;
  },

  render(w, rows, series, {esc, format, colors}) {
    if (!rows || !rows.length) return '<p>No records for these fields and dates.</p>';
    
    // Dynamic height scaling based on widget height grid units (w.h)
    const cardH = Math.max(150, (w.h || 6) * 52 - 62);
    const chartHeight = Math.max(120, (Number(w._plot_height)||cardH) - (w.subtitle ? 22 : 0));
    
    const axisFontSize = Number(w.axis_font_size) || 10;
    const axisColor = esc(w.axis_color || 'currentColor');
    const dataLabelFontSize = Number(w.data_label_font_size) || 14;
    const dataLabelColor = esc(w.data_label_color || w.text_color || 'currentColor');
    const subtitleFontSize = Number(w.subtitle_font_size) || 11;
    const subtitleColor = esc(w.subtitle_color || '#527467');

    // Check Radar / Polar Area
    if (w.style === 'radar') return this.renderRadar(w, rows, series, {esc, format, colors, height: chartHeight});
    if (w.style === 'polar_area') return this.renderPolarArea(w, rows, series, {esc, format, colors, height: chartHeight});



    const horizontal = ['bar', 'stacked_bar', 'lollipop', 'grouped_bar'].includes(w.style);

    const stacked = ['stacked_bar', 'stacked_column'].includes(w.style);

    const isLine = ['line', 'area', 'step_line', 'spline_line', 'curved_area'].includes(w.style);

    const isCurved = ['spline_line', 'curved_area'].includes(w.style);

    

    // Match the SVG coordinate space to the resized card, including its legend.
    const availableWidth = Math.max(180, Number(w._plot_width) || 620);
    const legendWidth = w.show_legend === false ? 0 : Math.min(150, Math.max(70, availableWidth * .28));
    const plotWidth = Math.max(120, availableWidth - legendWidth - (legendWidth ? 8 : 0));
    const availableHeight = Math.max(120, (Number(w._plot_height) || chartHeight) - (w.subtitle ? 22 : 0));
    const left = horizontal ? Math.min(110, plotWidth * .3) : Math.min(55, plotWidth * .2);
    const right = plotWidth - 14, top = 18;

    const bottom = availableHeight - 55;

    const width = right - left, height = bottom - top;

    

    const val = (r, s) => Number(r.values?.[s.key] ?? r.value) || 0;

    const extents = rows.flatMap(r => stacked

      ? [series.reduce((n, s) => n + Math.min(0, val(r, s)), 0), series.reduce((n, s) => n + Math.max(0, val(r, s)), 0)]

      : series.map(s => val(r, s)));

    const lo = Math.min(0, ...extents), hi = Math.max(0, ...extents);

    const range = hi - lo || 1;

    const pos = v => horizontal ? left + (v - lo) / range * width : bottom - (v - lo) / range * height;

    const step = (horizontal ? height : width) / rows.length;

    const center = i => (horizontal ? top : left) + (i + .5) * step;

    const band = Math.min(horizontal ? 28 : 52, step * .72);

    const axes = w.show_axes !== false;

    

    let marks = '', grid = '', labels = '';

    if (axes) {

      for (let i = 0; i <= 4; i++) {

        const v = lo + range * i / 4, p = pos(v), label = esc(format(v, series[0]));

        grid += horizontal

          ? `${w.show_grid !== false ? `<line x1="${p}" y1="${top}" x2="${p}" y2="${bottom}" stroke="${esc(w.grid_color||'currentColor')}" opacity="${w.grid_color?1:.12}"/>` : ''}<text x="${p}" y="${bottom + 18}" text-anchor="middle" font-size="${axisFontSize}" fill="${axisColor}">${label}</text>`

          : `${w.show_grid !== false ? `<line x1="${left}" y1="${p}" x2="${right}" y2="${p}" stroke="${esc(w.grid_color||'currentColor')}" opacity="${w.grid_color?1:.12}"/>` : ''}<text x="${left - 8}" y="${p + 3}" text-anchor="end" font-size="${axisFontSize}" fill="${axisColor}">${label}</text>`;

      }

      rows.forEach((r, i) => {

        if (!horizontal && i % Math.ceil(rows.length / 7) !== 0 && i !== rows.length - 1) return;

        const x=horizontal?left-10:center(i), y=horizontal?center(i):bottom+16;
        const capacity=horizontal?(left-20)/(axisFontSize*.56):Math.max(3,(width/Math.min(rows.length,7)-6)/(axisFontSize*.56));
        const lines=this.axisLines(r.name,w.axis_label_mode||'wrap',capacity);
        labels+=`<text x="${x}" y="${y}" text-anchor="${horizontal?'end':'middle'}" font-size="${axisFontSize}" fill="${axisColor}"><title>${esc(r.name)}</title>${lines.map((line,n)=>`<tspan x="${x}" dy="${n?axisFontSize+2:0}">${esc(line)}</tspan>`).join('')}</text>`;

      });

    }



    const positive = rows.map(() => 0), negative = rows.map(() => 0);



    // Helper for smooth cubic bezier paths

    const makeBezier = (pts) => {

      if (pts.length < 2) return '';

      let path = `M ${pts[0][0]},${pts[0][1]}`;

      for (let i = 0; i < pts.length - 1; i++) {

        const [x0, y0] = pts[i];

        const [x1, y1] = pts[i + 1];

        const dx = (x1 - x0) * 0.35;

        path += ` C ${x0 + dx},${y0} ${x1 - dx},${y1} ${x1},${y1}`;

      }

      return path;

    };



    series.forEach((s, j) => {

      const color = this.color(w,s,j,colors,true);

      const seriesLine = isLine || (w.style === 'combo' && j > 0);

      const points = rows.map((r, i) => [center(i), pos(val(r, s))]);



      if (seriesLine) {

        let path = '';

        if (isCurved) {

          path = makeBezier(points);

        } else {

          path = points.map(([x, y], i) => i === 0 ? `M${x},${y}` : w.style === 'step_line' ? `H${x}V${y}` : `L${x},${y}`).join(' ');

        }

        if (w.style === 'area' || w.style === 'curved_area') {

          marks += `<path d="${path} L${points.at(-1)[0]},${pos(0)} L${points[0][0]},${pos(0)} Z" fill="${color}" opacity=".15"/>`;

        }

        marks += `<path d="${path}" fill="none" stroke="${color}" stroke-width="2.8"/>`;

      }



      rows.forEach((r, i) => {

        const v = val(r, s), p = pos(v), c = center(i);

        const color=seriesLine || series.length>1?this.color(w,s,j,colors,true):this.color(w,r,i,colors);

        const attrs = `tabindex="0" role="button" data-bi-group="${esc(r.key ?? r.name)}" ${s.drillSeries ? `data-bi-series="${esc(s.key)}"` : `data-bi-measure="${esc(s.key)}"`}`;

        const title = `<title>${esc(r.name)} · ${esc(s.label)}: ${esc(format(v, s))}</title>`;

        let labelX = c, labelY = p - 7, labelAnchor='middle', insideLabel=false;



        if (seriesLine) {

          marks += `<circle ${attrs} cx="${c}" cy="${p}" r="${w.show_markers === false ? 7 : 4}" fill="${w.show_markers === false ? 'transparent' : color}">${title}</circle>`;

        } else if (w.style === 'lollipop') {

          const cy = c - band / 2 + (j + .5) * band / series.length;

          marks += `<line x1="${pos(0)}" y1="${cy}" x2="${p}" y2="${cy}" stroke="${color}" stroke-width="2"/><circle ${attrs} cx="${p}" cy="${cy}" r="4" fill="${color}">${title}</circle>`;

          labelX = p + 8; labelY = cy - 6;

        } else {

          const isGroupedH = w.style === 'grouped_bar';

          const offset = stacked ? (v >= 0 ? positive[i] : negative[i]) : 0;

          const a = pos(offset), b = pos(offset + v);

          const thickness = stacked || w.style === 'combo' ? band : band / series.length;

          const start = c - band / 2 + (stacked || w.style === 'combo' ? 0 : j * thickness);

          if (stacked) { if (v >= 0) positive[i] += v; else negative[i] += v; }

          

          if (horizontal || isGroupedH) {

            marks += `<rect ${attrs} x="${Math.min(a, b)}" y="${start}" width="${Math.max(1, Math.abs(b - a))}" height="${Math.max(1, thickness - 1)}" rx="2" fill="${color}">${title}</rect>`;

            insideLabel=['inside','center'].includes(w.label_position)||(w.label_position==='auto'&&stacked);

            labelX=insideLabel?(w.label_position==='inside'?b+(b>a?-6:6):(a+b)/2):b+(b>a?8:-8);

            labelAnchor=insideLabel?(w.label_position==='inside'?(b>a?'end':'start'):'middle'):(b>a?'start':'end');

            labelY = start + thickness / 2 + 3;

          } else {

            marks += `<rect ${attrs} x="${start}" y="${Math.min(a, b)}" width="${Math.max(1, thickness - 1)}" height="${Math.max(1, Math.abs(b - a))}" rx="2" fill="${color}">${title}</rect>`;

            insideLabel=['inside','center'].includes(w.label_position)||(w.label_position==='auto'&&stacked);

            labelX = start + thickness / 2;

            labelY=insideLabel?(w.label_position==='inside'?b+(b<a?14:-6):(a+b)/2+3):b+(b<a?-6:14);

          }

        }

        if (w.show_values) {

          if(seriesLine && ['inside','center'].includes(w.label_position))labelY=p+16;

          marks += `<text x="${labelX}" y="${Math.max(12, labelY)}" text-anchor="${labelAnchor}" font-size="${dataLabelFontSize}" fill="${insideLabel&&!w.data_label_color?this.contrast(color):dataLabelColor}">${esc(format(v, s))}</text>`;

        }

      });

    });



    const totalHeight = availableHeight;

    const subtitleHtml = w.subtitle ? `<p class="pb-chart-subtitle" style="font-size:${subtitleFontSize}px;color:${subtitleColor};margin:2px 0 6px;">${esc(w.subtitle)}</p>` : '';

    const categoryLegend=series.length===1&&!isLine&&w.style!=='combo';
    const legendEntries=categoryLegend?rows:series;
    const legendHtml = this.renderVerticalLegend(w, legendEntries, {esc, colors, series: !categoryLegend}).replace('style="', `style="flex:0 0 ${legendWidth}px;max-width:${legendWidth}px;`);

    return `${subtitleHtml}<div class="pb-chart-body-flex"><svg class="pb-chart-svg" viewBox="0 0 ${plotWidth} ${totalHeight}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(w.title || 'Chart')}">${grid}${marks}${labels}${axes ? `<text x="${(left + right) / 2}" y="${bottom + 46}" text-anchor="middle" font-size="${axisFontSize + 1}" fill="${axisColor}">${esc(w.x_title || (horizontal ? 'Value' : w.axis_label || 'Group'))}</text><text transform="translate(13 ${(top + bottom) / 2}) rotate(-90)" text-anchor="middle" font-size="${axisFontSize + 1}" fill="${axisColor}">${esc(w.y_title || (horizontal ? w.axis_label || 'Group' : 'Value'))}</text>` : ''}</svg>${legendHtml}</div>`;

  },



  renderRadar(w, rows, series, {esc, format, colors, height}) {

    const plotWidth=Math.max(140,(Number(w._plot_width)||620)*(w.show_legend===false?1:.7));
    const cx = plotWidth/2, cy = height / 2, r = Math.max(25,Math.min(plotWidth/2-45, height / 2 - 35));

    const n = rows.length;

    if (n < 3) return '<p>Radar chart requires at least 3 categories.</p>';



    const axisFontSize = Number(w.axis_font_size) || 10;

    const axisColor = esc(w.axis_color || 'currentColor');

    const subtitleFontSize = Number(w.subtitle_font_size) || 11;

    const subtitleColor = esc(w.subtitle_color || '#527467');



    const val = (r, s) => Number(r.values?.[s.key] ?? r.value) || 0;

    const maxV = Math.max(1, ...rows.flatMap(row => series.map(s => val(row, s))));

    const angleStep = (Math.PI * 2) / n;



    let grid = '', labels = '', polygons = '';



    // Radar Concentric Web

    [0.25, 0.5, 0.75, 1.0].forEach(k => {

      const ringPts = rows.map((_, i) => {

        const a = i * angleStep - Math.PI / 2;

        return `${cx + r * k * Math.cos(a)},${cy + r * k * Math.sin(a)}`;

      }).join(' ');

      grid += `<polygon points="${ringPts}" fill="none" stroke="${esc(w.grid_color||'currentColor')}" opacity="${w.grid_color?1:k === 1.0 ? '.25' : '.1'}"/>`;

      if (w.show_axes !== false) {

        grid += `<text x="${cx + 4}" y="${cy - r * k + 10}" font-size="${axisFontSize}" fill="${axisColor}" opacity=".75">${esc(format(maxV * k, series[0]))}</text>`;

      }

    });



    // Radial Spoke Lines & Category Labels

    rows.forEach((row, i) => {

      const a = i * angleStep - Math.PI / 2;

      const x2 = cx + r * Math.cos(a), y2 = cy + r * Math.sin(a);

      grid += `<line x1="${cx}" y1="${cy}" x2="${x2}" y2="${y2}" stroke="${esc(w.grid_color||'currentColor')}" opacity="${w.grid_color?1:.18}"/>`;

      

      const lx = cx + (r + 18) * Math.cos(a), ly = cy + (r + 14) * Math.sin(a);

      const align = Math.abs(Math.cos(a)) < 0.2 ? 'middle' : Math.cos(a) > 0 ? 'start' : 'end';

      labels += `<text x="${lx}" y="${ly}" text-anchor="${align}" font-size="${axisFontSize}" fill="${axisColor}"><title>${esc(row.name)}</title>${esc(String(row.name).slice(0, 14))}</text>`;

    });



    // Series Polygons

    series.forEach((s, j) => {

      const color = this.color(w,s,j,colors,true);

      const pts = rows.map((row, i) => {

        const v = Math.max(0, val(row, s));

        const a = i * angleStep - Math.PI / 2;

        const dist = (v / maxV) * r;

        return [cx + dist * Math.cos(a), cy + dist * Math.sin(a)];

      });



      const polyStr = pts.map(p => p.join(',')).join(' ');

      polygons += `<polygon points="${polyStr}" fill="${color}" fill-opacity=".2" stroke="${color}" stroke-width="2.5"/>`;

      

      pts.forEach(([px, py], i) => {

        const v = val(rows[i], s);

        const attrs = `tabindex="0" role="button" data-bi-group="${esc(rows[i].key ?? rows[i].name)}" ${s.drillSeries ? `data-bi-series="${esc(s.key)}"` : `data-bi-measure="${esc(s.key)}"`}`;

        polygons += `<circle ${attrs} cx="${px}" cy="${py}" r="4" fill="${color}"><title>${esc(rows[i].name)} · ${esc(s.label)}: ${esc(format(v, s))}</title></circle>`;
        if(w.show_values)polygons+=`<text x="${px}" y="${py+(['inside','center'].includes(w.label_position)?16:-9)}" text-anchor="middle" font-size="${w.data_label_font_size||14}" fill="${esc(w.data_label_color||w.text_color||'#163a34')}">${esc(format(v,s))}</text>`;

      });

    });



    const subtitleHtml = w.subtitle ? `<p class="pb-chart-subtitle" style="font-size:${subtitleFontSize}px;color:${subtitleColor};margin:2px 0 6px;">${esc(w.subtitle)}</p>` : '';

    const legendHtml = this.renderVerticalLegend(w, series, {esc, colors, series: true});

    return `${subtitleHtml}<div class="pb-chart-body-flex"><svg class="pb-chart-svg" viewBox="0 0 ${plotWidth} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(w.title || 'Radar Chart')}">${grid}${polygons}${labels}</svg>${legendHtml}</div>`;

  },



  renderPolarArea(w, rows, series, {esc, format, colors, height}) {

    const plotWidth=Math.max(140,(Number(w._plot_width)||620)*(w.show_legend===false?1:.7));
    const cx = plotWidth/2, cy = height / 2, r = Math.max(25,Math.min(plotWidth/2-30, height / 2 - 30));

    const n = rows.length;

    if (!n) return '<p>No data for polar area chart.</p>';



    const subtitleFontSize = Number(w.subtitle_font_size) || 11;

    const subtitleColor = esc(w.subtitle_color || '#527467');



    const s = series[0];

    const val = row => Math.max(0, Number(row.values?.[s.key] ?? row.value) || 0);

    const maxV = Math.max(1, ...rows.map(val));

    const angleStep = (Math.PI * 2) / n;



    let slices = '', grid = '';

    

    // Concentric grid rings

    [0.33, 0.66, 1.0].forEach(k => {

      grid += `<circle cx="${cx}" cy="${cy}" r="${r * k}" fill="none" stroke="${esc(w.grid_color||'currentColor')}" opacity="${w.grid_color?1:.12}"/>`;

    });



    rows.forEach((row, i) => {

      const v = val(row);

      const radius = Math.max(6, (v / maxV) * r);

      const a1 = i * angleStep - Math.PI / 2;

      const a2 = (i + 1) * angleStep - Math.PI / 2;

      const color = this.color(w,row,i,colors);



      const x1 = cx + radius * Math.cos(a1), y1 = cy + radius * Math.sin(a1);

      const x2 = cx + radius * Math.cos(a2), y2 = cy + radius * Math.sin(a2);

      const largeArc = angleStep > Math.PI ? 1 : 0;

      

      const path = `M ${cx},${cy} L ${x1},${y1} A ${radius},${radius} 0 ${largeArc} 1 ${x2},${y2} Z`;

      const attrs = `tabindex="0" role="button" data-bi-group="${esc(row.key ?? row.name)}" data-bi-measure="${esc(s.key)}"`;

      

      slices += `<path ${attrs} d="${path}" fill="${color}" opacity=".75" stroke="#fff" stroke-width="1.5"><title>${esc(row.name)}: ${esc(format(v, s))}</title></path>`;
      if(w.show_values){const mid=(a1+a2)/2,inside=['inside','center'].includes(w.label_position),dist=inside?radius*.65:radius+16;
        slices+=`<text x="${cx+dist*Math.cos(mid)}" y="${cy+dist*Math.sin(mid)}" text-anchor="middle" dominant-baseline="middle" font-size="${w.data_label_font_size||14}" fill="${esc(w.data_label_color||(inside?this.contrast(color):(w.text_color||'#163a34')))}">${esc(format(v,s))}</text>`;}


    });



    const subtitleHtml = w.subtitle ? `<p class="pb-chart-subtitle" style="font-size:${subtitleFontSize}px;color:${subtitleColor};margin:2px 0 6px;">${esc(w.subtitle)}</p>` : '';

    const legendHtml = this.renderVerticalLegend(w, rows, {esc, colors, series: false});

    return `${subtitleHtml}<div class="pb-chart-body-flex"><svg class="pb-chart-svg" viewBox="0 0 ${plotWidth} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(w.title || 'Polar Area Chart')}">${grid}${slices}</svg>${legendHtml}</div>`;

  }

};



