/* =========================================================
   SAT Santander · Gráficos (Chart.js)
   Los colores se leen del tema activo, por eso al cambiar de tema
   las gráficas se vuelven a dibujar.
   ========================================================= */

const Graficos = (() => {
  const activos = {};

  function paleta() {
    return {
      texto: cssVar('--texto'),
      texto2: cssVar('--texto-2'),
      texto3: cssVar('--texto-3'),
      borde: cssVar('--borde'),
      acento: cssVar('--acento'),
      verde: cssVar('--verde'),
      rojo: cssVar('--rojo'),
      amarillo: cssVar('--amarillo'),
      amarilloLinea: cssVar('--amarillo-linea')
    };
  }

  /* Plugin propio: líneas de referencia (umbral, meta) con etiqueta */
  const lineasReferencia = {
    id: 'lineasReferencia',
    afterDatasetsDraw(chart, _args, opciones) {
      const lineas = (opciones && opciones.lineas) || [];
      const { ctx, chartArea: a, scales } = chart;
      lineas.forEach(l => {
        const escala = l.eje === 'x' ? scales.x : scales.y;
        if (!escala) return;
        const p = escala.getPixelForValue(l.valor);
        ctx.save();
        ctx.strokeStyle = l.color;
        ctx.lineWidth = 2;
        ctx.setLineDash(l.punteada ? [6, 4] : []);
        ctx.beginPath();
        if (l.eje === 'x') { ctx.moveTo(p, a.top); ctx.lineTo(p, a.bottom); }
        else { ctx.moveTo(a.left, p); ctx.lineTo(a.right, p); }
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = l.color;
        ctx.font = `600 ${l.tamano || 12}px Inter, system-ui, sans-serif`;
        if (l.eje === 'x') { ctx.textAlign = 'left'; ctx.fillText(l.texto, p + 6, l.arriba ? a.top - 8 : a.top + 14); }
        else { ctx.textAlign = 'right'; ctx.fillText(l.texto, a.right - 4, p - 6); }
        ctx.restore();
      });
    }
  };

  /* Plugin propio: escribe el valor sobre cada barra */
  const valoresEnBarras = {
    id: 'valoresEnBarras',
    afterDatasetsDraw(chart, _args, opciones) {
      if (!opciones || !opciones.activo) return;
      const { ctx } = chart;
      const horizontal = chart.options.indexAxis === 'y';
      chart.data.datasets.forEach((ds, i) => {
        chart.getDatasetMeta(i).data.forEach((barra, j) => {
          const v = ds.data[j];
          if (v === null || v === undefined) return;
          ctx.save();
          ctx.fillStyle = opciones.color;
          ctx.font = `600 ${opciones.tamano || 12}px "IBM Plex Mono", ui-monospace, monospace`;
          const texto = opciones.formato ? opciones.formato(v) : num(v);
          if (horizontal) { ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillText(texto, barra.x + 6, barra.y); }
          else { ctx.textAlign = 'center'; ctx.fillText(texto, barra.x, barra.y - 6); }
          ctx.restore();
        });
      });
    }
  };

  Chart.register(lineasReferencia, valoresEnBarras);

  function base(c) {
    Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
    Chart.defaults.color = c.texto3;
    Chart.defaults.borderColor = c.borde;
  }

  function crear(id, config) {
    if (activos[id]) activos[id].destroy();
    const canvas = document.getElementById(id);
    if (!canvas) return;
    activos[id] = new Chart(canvas, config);
  }

  /* ---------- Modelo vs línea base ---------- */
  function metricas(datos) {
    const c = paleta(); base(c);
    const m = datos.metricas;
    crear('chartMetricas', {
      type: 'bar',
      data: {
        labels: ['Recall', 'PR-AUC'],
        datasets: [
          { label: m.modelo.nombre, data: [m.modelo.recall, m.modelo.pr_auc], backgroundColor: c.verde, borderRadius: 4, maxBarThickness: 64 },
          { label: `Línea base: ${m.linea_base.nombre.toLowerCase()}`, data: [m.linea_base.recall, m.linea_base.pr_auc], backgroundColor: c.texto3, borderRadius: 4, maxBarThickness: 64 }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        layout: { padding: { top: 18 } },
        scales: { y: { min: 0, max: 1, ticks: { callback: v => num(v, 1) } }, x: { grid: { display: false } } },
        plugins: {
          legend: { position: 'bottom', labels: { color: c.texto2, boxWidth: 12 } },
          tooltip: { callbacks: { label: t => `${t.dataset.label}: ${num(t.raw)}` } },
          valoresEnBarras: { activo: true, color: c.texto }
        }
      }
    });
  }

  /* ---------- Importancia SHAP ---------- */
  function shap(datos) {
    const c = paleta(); base(c);
    const items = [...datos.importancia].sort((a, b) => b.valor - a.valor);
    crear('chartShap', {
      type: 'bar',
      data: {
        labels: items.map(i => i.etiqueta),
        datasets: [{ label: 'Importancia media |SHAP|', data: items.map(i => i.valor), backgroundColor: c.acento, borderRadius: 3, maxBarThickness: 22 }]
      },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        layout: { padding: { right: 48 } },
        scales: {
          x: { beginAtZero: true, ticks: { callback: v => num(v, 2) } },
          y: { grid: { display: false }, ticks: { color: c.texto2, autoSkip: false, callback(v) { const t = this.getLabelForValue(v); const max = this.chart.width < 520 ? 20 : 34; return t.length > max ? t.slice(0, max - 1) + '…' : t; } } }
        },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { title: t => items[t[0].dataIndex].etiqueta, label: t => num(t.raw, 3) } },
          valoresEnBarras: { activo: true, color: c.texto2, tamano: 11, formato: v => num(v, 3) }
        }
      }
    });
  }

  /* ---------- Curva del umbral ---------- */
  function umbral(datos) {
    const c = paleta(); base(c);
    const curva = [...datos.curva_umbral].sort((a, b) => a.umbral - b.umbral);
    crear('chartUmbral', {
      type: 'line',
      data: {
        datasets: [
          { label: 'Recall', data: curva.map(p => ({ x: p.umbral, y: p.recall })), borderColor: c.verde, backgroundColor: c.verde, borderWidth: 3, pointRadius: 0, tension: .3 },
          { label: 'Precisión', data: curva.map(p => ({ x: p.umbral, y: p.precision })), borderColor: c.texto3, backgroundColor: c.texto3, borderWidth: 2, borderDash: [6, 4], pointRadius: 0, tension: .3 }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: { type: 'linear', min: 0, max: Math.max(...curva.map(p => p.umbral)), title: { display: true, text: 'Umbral de probabilidad', color: c.texto3 }, ticks: { callback: v => num(v, 1) } },
          y: { min: 0, max: 1, ticks: { callback: v => num(v, 1) } }
        },
        plugins: {
          legend: { position: 'bottom', labels: { color: c.texto2, boxWidth: 12 } },
          tooltip: { callbacks: { title: t => `Umbral ${num(t[0].parsed.x)}`, label: t => `${t.dataset.label}: ${num(t.parsed.y)}` } },
          lineasReferencia: {
            lineas: [
              { eje: 'x', valor: datos.umbral, texto: `Umbral elegido ${num(datos.umbral)}`, color: c.rojo },
              { eje: 'y', valor: 0.70, texto: 'Meta de recall 0,70', color: c.texto2, punteada: true, tamano: 11 }
            ]
          }
        }
      }
    });
  }

  /* ---------- Imagen para el PDF: 10 municipios con mayor probabilidad ----------
     Se dibuja fuera de pantalla, siempre con colores del tema claro. */
  function imagenTop10(datos, municipios) {
    const top = municipios.slice(0, 10);
    const cont = document.createElement('div');
    cont.style.cssText = 'position:fixed;left:-10000px;top:0;width:1000px;height:500px;';
    const canvas = document.createElement('canvas');
    canvas.width = 1000; canvas.height = 500;
    cont.appendChild(canvas);
    document.body.appendChild(cont);

    const colores = { rojo: '#C8102E', amarillo: '#FFD100', verde: '#006B3F' };
    const fondoBlanco = { id: 'fondoBlanco', beforeDraw(ch) { ch.ctx.save(); ch.ctx.fillStyle = '#FFFFFF'; ch.ctx.fillRect(0, 0, ch.width, ch.height); ch.ctx.restore(); } };

    const chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: top.map(m => m.municipio),
        datasets: [{ data: top.map(m => m.prob), backgroundColor: top.map(m => colores[m.nivel]), borderColor: '#1E293B', borderWidth: top.map(m => m.nivel === 'amarillo' ? 1 : 0), borderRadius: 3, maxBarThickness: 30 }]
      },
      options: {
        indexAxis: 'y', responsive: false, animation: false, devicePixelRatio: 2,
        layout: { padding: { right: 60, top: 28 } },
        scales: {
          x: { min: 0, max: 1, ticks: { color: '#475569', font: { size: 14 }, callback: v => `${Math.round(v * 100)} %` }, grid: { color: '#E2E8F0' } },
          y: { ticks: { color: '#1E293B', font: { size: 15, weight: '600' } }, grid: { display: false } }
        },
        plugins: {
          legend: { display: false }, tooltip: { enabled: false },
          lineasReferencia: { lineas: [{ eje: 'x', valor: datos.umbral, texto: `Umbral ${num(datos.umbral)}`, color: '#1E293B', punteada: true, tamano: 14, arriba: true }] },
          valoresEnBarras: { activo: true, color: '#1E293B', tamano: 14, formato: v => pct(v) }
        }
      },
      plugins: [fondoBlanco]
    });

    const imagen = chart.toBase64Image('image/png', 1);
    chart.destroy();
    cont.remove();
    return imagen;
  }

  return { metricas, shap, umbral, imagenTop10 };
})();
