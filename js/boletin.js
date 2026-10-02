/* =========================================================
   SAT Santander · Boletines
   Hay un boletín por municipio, con plantilla según su nivel
   (alerta, precaución o sin alerta). Texto y cifras vienen del
   cuaderno (datos.boletines). El aplicativo NO escribe cifras:
   solo verifica que cada número del texto esté en el diccionario
   de cifras de ese municipio, igual que verificar_cifras.
   ========================================================= */

const Boletin = (() => {

  /* ---------- Verificación ---------- */
  function verificarCifras(textos, cifras) {
    const permitidas = Object.values(cifras).map(Number);
    const encontradas = textos.join(' ').match(/\d+(?:,\d+)?/g) || [];
    const faltantes = encontradas.filter(t => {
      const v = parseFloat(t.replace(',', '.'));
      return !permitidas.some(p => Math.abs(p - v) < 1e-9);
    });
    return { total: encontradas.length, faltantes: [...new Set(faltantes)], ok: faltantes.length === 0 };
  }

  function textosDe(b, m) {
    return [b.titulo, ...b.parrafos, ...(m ? m.razones.map(r => r.detalle) : [])];
  }

  function verificar(datos, m) {
    const b = datos.boletines[m.codigo];
    if (!b) return { total: 0, faltantes: [], ok: false, sinBoletin: true };
    return verificarCifras(textosDe(b, m), b.cifras);
  }

  /* ---------- Vista en pantalla ---------- */
  /* Lista con buscador: clic en el nombre = ver; casilla = marcar para descargar */
  function pintarLista(municipios, { seleccionado, filtro, busqueda, marcados }) {
    const norm = t => t.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    const q = norm(busqueda.trim());
    const filas = municipios.filter(m =>
      (filtro === 'todos' || m.nivel === filtro) && (!q || norm(m.municipio).includes(q)));

    // Resalta la parte del nombre que coincide con la búsqueda
    const resaltar = nombre => {
      if (!q) return esc(nombre);
      const i = norm(nombre).indexOf(q);
      if (i < 0) return esc(nombre);
      return esc(nombre.slice(0, i)) + '<mark>' + esc(nombre.slice(i, i + q.length)) + '</mark>' + esc(nombre.slice(i + q.length));
    };

    document.getElementById('bolLista').innerHTML = filas.map(m => `
      <li class="bol-item ${m.codigo === seleccionado ? 'is-active' : ''}">
        <label class="bol-item__chk" title="Marcar para descargar">
          <input type="checkbox" data-marcar="${esc(m.codigo)}" ${marcados.has(m.codigo) ? 'checked' : ''} aria-label="Marcar ${esc(m.municipio)} para descargar">
        </label>
        <button class="bol-item__btn" data-ver-boletin="${esc(m.codigo)}" ${m.codigo === seleccionado ? 'aria-current="true"' : ''}>
          <i class="mark mark--${m.nivel}" aria-hidden="true"></i>
          <span class="bol-item__name">${resaltar(m.municipio)}</span>
          <span class="bol-item__prob">${pct(m.prob)}</span>
          <span class="sr-only">${NIVELES[m.nivel].nombre}</span>
        </button>
      </li>`).join('');
    document.getElementById('bolVacio').hidden = filas.length > 0;
    document.getElementById('bolConteo').textContent = `${filas.length} de ${municipios.length}`;
    return filas;
  }

  function pintarDescargasPorNivel(datos, municipios) {
    const conteo = n => municipios.filter(m => m.nivel === n).length;
    const malos = municipios.filter(m => !verificar(datos, m).ok);
    document.getElementById('descargasNivel').innerHTML = `
      <button class="btn btn--nivel" data-pdf-nivel="rojo"><i class="mark mark--rojo" aria-hidden="true"></i>Alerta roja<span>${conteo('rojo')}</span></button>
      <button class="btn btn--nivel" data-pdf-nivel="amarillo"><i class="mark mark--amarillo" aria-hidden="true"></i>Precaución<span>${conteo('amarillo')}</span></button>
      <button class="btn btn--nivel" data-pdf-nivel="verde"><i class="mark mark--verde" aria-hidden="true"></i>Sin alerta<span>${conteo('verde')}</span></button>
      <button class="btn btn--nivel" data-pdf-nivel="todos">Todos los municipios<span>${municipios.length}</span></button>
      <p class="muted">${malos.length === 0
        ? `Los ${municipios.length} boletines tienen sus cifras verificadas. Cada descarga es un solo PDF con índice y un boletín por municipio.`
        : `${malos.length} boletín(es) tienen cifras sin respaldo y no se incluirán: ${malos.map(m => esc(m.municipio)).join(', ')}.`}</p>`;
  }

  function pintar(datos, municipios, codigo) {
    const m = municipios.find(x => x.codigo === codigo) || municipios[0];
    const b = datos.boletines[m.codigo];
    pintarDescargasPorNivel(datos, municipios);
    const vista = document.getElementById('boletinVista');
    const btn = document.getElementById('btnPdf');

    if (!b) {
      vista.innerHTML = `<p class="empty">No hay boletín exportado para ${esc(m.municipio)}.</p>`;
      document.getElementById('verificacion').innerHTML = '';
      btn.disabled = true;
      return;
    }
    const v = verificar(datos, m);

    vista.innerHTML = `
      <div class="bulletin__band">
        <div>
          <p>Gobernación de Santander · UDGRD</p>
          <h2>Boletín de movimiento en masa</h2>
        </div>
        <div class="when">
          <div class="bulletin__flags">
            <img class="flag" src="assets/bandera-santander.png" alt="Bandera de Santander">
            <img class="flag" src="assets/bandera-bucaramanga.png" alt="Bandera de Bucaramanga">
          </div>
          <p>Pronóstico de ${esc(datos.mes)}</p>
          <p>Corte: ${esc(datos.corte_texto)}</p>
        </div>
      </div>
      <div class="bulletin__body">
        <div style="display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center">
          <h3 class="bulletin__title">${esc(b.titulo)}</h3>
          ${badge(m.nivel)}
        </div>
        ${b.parrafos.map(p => `<p>${esc(p)}</p>`).join('')}
        <h4 class="detail__h3">Razones principales</h4>
        <ol class="reasons">
          ${m.razones.map((r, i) => `<li><span class="reasons__n">${i + 1}</span><div><p class="reasons__t">${esc(r.etiqueta)}</p><p class="reasons__d">${esc(r.detalle)}</p></div></li>`).join('')}
        </ol>
      </div>`;

    document.getElementById('verificacion').innerHTML = v.ok
      ? `<div class="verify"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6L9 17l-5-5"/></svg><div><strong>Cifras verificadas</strong><span>Los ${v.total} números del boletín están en el diccionario de ${esc(m.municipio)}.</span></div></div>`
      : `<div class="verify verify--mal"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 9v4M12 17h.01"/><circle cx="12" cy="12" r="10"/></svg><div><strong>Hay cifras sin respaldo</strong><span>No están en el diccionario: ${v.faltantes.map(esc).join(', ')}. Este boletín no se puede descargar.</span></div></div>`;
    btn.disabled = !v.ok;
    btn.dataset.codigo = m.codigo;
  }

  /* ---------- PDF ---------- */
  const VERDE = [0, 107, 63], ROJO = [200, 16, 46], AMARILLO = [255, 209, 0], PIZARRA = [30, 41, 59], GRIS = [71, 85, 105];
  const W = 210, M = 16, ANCHO = W - 2 * M, LIMITE = 276;
  const colorNivel = n => n === 'rojo' ? ROJO : n === 'amarillo' ? AMARILLO : VERDE;

  function nuevoDoc() {
    const { jsPDF } = window.jspdf;
    return new jsPDF({ unit: 'mm', format: 'a4' });
  }

  /* Encabezado verde con banderas, igual en todas las páginas */
  function encabezado(doc, datos, subtitulo) {
    doc.setFillColor(...VERDE); doc.rect(0, 0, W, 32, 'F');
    doc.setTextColor(255, 255, 255);
    doc.setFont('helvetica', 'normal'); doc.setFontSize(9);
    doc.text('GOBERNACIÓN DE SANTANDER · UDGRD', M, 11);

    const banderas = window.SAT_BANDERAS || {};
    let x = W - M;
    ['bucaramanga', 'santander'].forEach(k => {
      const ban = banderas[k];
      if (!ban) return;
      const alto = 10, ancho = alto * ban.ancho / ban.alto;
      x -= ancho;
      doc.setFillColor(255, 255, 255);
      doc.rect(x - 0.4, 5.6, ancho + 0.8, alto + 0.8, 'F');
      doc.addImage(ban.src, 'PNG', x, 6, ancho, alto, `bandera-${k}`);
      x -= 4;
    });

    doc.setTextColor(255, 255, 255);
    doc.setFont('helvetica', 'bold'); doc.setFontSize(15);
    doc.text(subtitulo, M, 20);
    doc.setFont('helvetica', 'normal'); doc.setFontSize(9.5);
    doc.text(`Pronóstico de ${datos.mes}`, M, 27);
    doc.text(`Corte: ${datos.corte_texto}`, W - M, 27, { align: 'right' });
  }

  /* Escritor con salto de página automático */
  function escritor(doc, datos, subtitulo, yInicial) {
    const w = { y: yInicial };
    w.espacio = alto => {
      if (w.y + alto > LIMITE) { doc.addPage(); encabezado(doc, datos, subtitulo); w.y = 42; }
    };
    w.parrafo = (texto, tam = 10.5, color = PIZARRA) => {
      doc.setFont('helvetica', 'normal'); doc.setFontSize(tam); doc.setTextColor(...color);
      const lineas = doc.splitTextToSize(texto, ANCHO);
      const alto = lineas.length * tam * 0.45;
      w.espacio(alto);
      doc.text(lineas, M, w.y + tam * 0.35);
      w.y += alto + 3;
    };
    w.subtitulo = texto => {
      w.espacio(14); w.y += 2;
      doc.setFont('helvetica', 'bold'); doc.setFontSize(12); doc.setTextColor(...PIZARRA);
      doc.text(texto, M, w.y + 4); w.y += 9;
    };
    return w;
  }

  /* Un boletín, empezando en página nueva. Devuelve las páginas que ocupó. */
  function escribirBoletin(doc, datos, m, primera) {
    const b = datos.boletines[m.codigo];
    if (!primera) doc.addPage();
    const desde = doc.getNumberOfPages();
    const subtitulo = 'Boletín de movimiento en masa';
    encabezado(doc, datos, subtitulo);
    const w = escritor(doc, datos, subtitulo, 42);

    doc.setFont('helvetica', 'bold'); doc.setFontSize(16); doc.setTextColor(...PIZARRA);
    const lineasTitulo = doc.splitTextToSize(b.titulo, ANCHO);
    doc.text(lineasTitulo, M, w.y); w.y += lineasTitulo.length * 7;

    // Caja de probabilidad
    doc.setDrawColor(226, 232, 240); doc.setLineWidth(0.2); doc.setFillColor(248, 249, 250);
    doc.roundedRect(M, w.y, ANCHO, 22, 2, 2, 'FD');
    doc.setFillColor(...colorNivel(m.nivel)); doc.rect(M + 4, w.y + 5, 3, 12, 'F');
    if (m.nivel === 'amarillo') { doc.setDrawColor(...PIZARRA); doc.rect(M + 4, w.y + 5, 3, 12, 'S'); }
    doc.setFont('helvetica', 'bold'); doc.setFontSize(24); doc.setTextColor(...(m.nivel === 'rojo' ? ROJO : PIZARRA));
    doc.text(pct(m.prob), M + 12, w.y + 14.5);
    doc.setFont('helvetica', 'normal'); doc.setFontSize(10); doc.setTextColor(...GRIS);
    doc.text(`Probabilidad de al menos un movimiento en masa en ${datos.mes}`, M + 42, w.y + 9.5);
    doc.text(`Nivel: ${NIVELES[m.nivel].nombre}`, M + 42, w.y + 15.5);
    w.y += 30;

    b.parrafos.forEach(p => w.parrafo(p));

    w.subtitulo('Razones principales');
    m.razones.forEach((r, i) => w.parrafo(`${i + 1}. ${r.etiqueta}: ${r.detalle}.`));

    w.subtitulo('Qué no puede anticipar este pronóstico');
    datos.limitaciones.forEach(l => w.parrafo(`- ${l}`, 9.5, GRIS));

    return { desde, hasta: doc.getNumberOfPages(), m };
  }

  /* Portada para descargas de varios municipios */
  function escribirPortada(doc, datos, lista, nivel, ordenados) {
    const titulo = TITULOS_NIVEL[nivel];
    encabezado(doc, datos, titulo);
    const w = escritor(doc, datos, titulo, 44);

    const descripcion = {
      rojo: `municipios con probabilidad igual o mayor al umbral de alerta (${num(datos.umbral)})`,
      amarillo: `municipios en precaución (entre ${num(datos.umbral * datos.factor_amarillo, 3)} y ${num(datos.umbral)})`,
      verde: `municipios sin alerta (por debajo de ${num(datos.umbral * datos.factor_amarillo, 3)})`,
      todos: 'municipios del departamento, de mayor a menor probabilidad',
      seleccion: 'municipios elegidos, de mayor a menor probabilidad'
    }[nivel];
    w.parrafo(`Este documento reúne los boletines de ${lista.length} ${descripcion}. Cada boletín empieza en una página nueva.`);

    if (nivel === 'rojo' || nivel === 'todos' || (nivel === 'seleccion' && lista.some(m => m.nivel === 'rojo'))) {
      const img = Graficos.imagenTop10(datos, ordenados);
      const alto = ANCHO * 500 / 1000;
      w.espacio(alto + 16);
      w.subtitulo('Municipios con mayor probabilidad en el departamento');
      doc.addImage(img, 'PNG', M, w.y, ANCHO, alto);
      w.y += alto + 6;
    }
    w.subtitulo('Índice');
    return w;
  }

  function tablaIndice(doc, w, lista, paginas) {
    doc.autoTable({
      startY: w.y,
      margin: { left: M, right: M, top: 42, bottom: 22 },
      head: [['#', 'Municipio', 'Probabilidad', 'Nivel', 'Página']],
      body: lista.map(m => [m.puesto, m.municipio, pct(m.prob), NIVELES[m.nivel].nombre, paginas[m.codigo] || '']),
      styles: { font: 'helvetica', fontSize: 9.5, textColor: PIZARRA, cellPadding: 2, lineColor: [226, 232, 240], lineWidth: 0.2 },
      headStyles: { fillColor: [241, 244, 247], textColor: GRIS, fontStyle: 'bold' },
      columnStyles: { 0: { cellWidth: 12, halign: 'right' }, 2: { halign: 'right', cellWidth: 28 }, 3: { cellWidth: 30 }, 4: { halign: 'right', cellWidth: 18 } },
      didParseCell: c => {
        if (c.section === 'body' && c.column.index === 3) {
          const n = lista[c.row.index].nivel;
          c.cell.styles.fontStyle = 'bold';
          if (n === 'rojo') { c.cell.styles.fillColor = ROJO; c.cell.styles.textColor = [255, 255, 255]; }
          if (n === 'amarillo') c.cell.styles.fillColor = AMARILLO;
        }
      },
      // Si el índice pasa a otra página, esa página también lleva el encabezado verde
      didDrawPage: d => { if (d.pageNumber > 1) encabezado(doc, w.datos, w.titulo); }
    });
  }

  function pies(doc, datos, rangos, verifs) {
    const total = doc.getNumberOfPages();
    for (let i = 1; i <= total; i++) {
      doc.setPage(i);
      const r = rangos.find(x => i >= x.desde && i <= x.hasta);
      let izq = 'SAT Santander';
      if (r) {
        const v = verifs[r.m.codigo];
        izq += ` · ${r.m.municipio} · Cifras verificadas: ${v.total} de ${v.total}`;
      }
      if (datos.datos_simulados) izq += ' · Datos simulados';
      doc.setDrawColor(226, 232, 240); doc.setLineWidth(0.2); doc.line(M, 284, W - M, 284);
      doc.setFont('helvetica', 'normal'); doc.setFontSize(8); doc.setTextColor(...GRIS);
      doc.text(izq, M, 289);
      doc.text(`Página ${i} de ${total}`, W - M, 289, { align: 'right' });
    }
  }

  const TITULOS_NIVEL = {
    rojo: 'Boletines de alerta roja',
    amarillo: 'Boletines de precaución',
    verde: 'Boletines sin alerta',
    todos: 'Boletines de todos los municipios',
    seleccion: 'Boletines seleccionados'
  };

  const sinTildes = t => t.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/\s+/g, '');

  /* Un solo municipio */
  function descargarUno(datos, municipios, codigo) {
    const m = municipios.find(x => x.codigo === codigo);
    const v = verificar(datos, m);
    if (!v.ok) throw new Error(`El boletín de ${m.municipio} tiene cifras sin respaldo.`);
    const doc = nuevoDoc();
    const r = escribirBoletin(doc, datos, m, true);
    pies(doc, datos, [r], { [m.codigo]: v });
    doc.save(`Boletin_SAT_${sinTildes(m.municipio)}_${datos.corte.slice(0, 7)}.pdf`);
  }

  /* Varios municipios en un solo PDF: portada con índice y un boletín por página */
  function descargarVarios(datos, municipios, candidatos, clave) {
    const verifs = {};
    const lista = candidatos.filter(m => (verifs[m.codigo] = verificar(datos, m)).ok);
    if (lista.length === 0) throw new Error('No hay boletines verificados para descargar.');

    const armar = paginas => {
      const doc = nuevoDoc();
      const w = escribirPortada(doc, datos, lista, clave, municipios);
      w.datos = datos;
      w.titulo = TITULOS_NIVEL[clave];
      tablaIndice(doc, w, lista, paginas);
      const rangos = lista.map(m => escribirBoletin(doc, datos, m, false));
      return { doc, rangos };
    };

    // Primera pasada para saber en qué página queda cada boletín; la segunda ya lleva el índice numerado
    const paginas = {};
    armar({}).rangos.forEach(r => { paginas[r.m.codigo] = r.desde; });
    const { doc, rangos } = armar(paginas);
    pies(doc, datos, rangos, verifs);

    const nombre = { rojo: 'AlertaRoja', amarillo: 'Precaucion', verde: 'SinAlerta', todos: 'Todos', seleccion: `Seleccion_${lista.length}` }[clave];
    doc.save(`Boletines_SAT_${nombre}_${datos.corte.slice(0, 7)}.pdf`);
    return lista.length;
  }

  function descargarNivel(datos, municipios, nivel) {
    return descargarVarios(datos, municipios, municipios.filter(m => nivel === 'todos' || m.nivel === nivel), nivel);
  }

  /* Los municipios que el usuario marcó; si es uno solo, sale como boletín individual */
  function descargarMarcados(datos, municipios, codigos) {
    const lista = municipios.filter(m => codigos.has(m.codigo));
    if (lista.length === 1) { descargarUno(datos, municipios, lista[0].codigo); return 1; }
    return descargarVarios(datos, municipios, lista, 'seleccion');
  }

  return { pintar, pintarLista, descargarUno, descargarNivel, descargarMarcados, verificar };
})();
