/* =========================================================
   SAT Santander · Aplicativo
   ========================================================= */

const TITULOS = {
  mapa: 'Mapa de alertas',
  boletin: 'Boletín',
  modelo: 'Modelo y métricas',
  umbral: 'Umbral y semáforo'
};

const estado = {
  datos: null,
  municipios: [],       // ordenados de mayor a menor probabilidad
  conteo: { rojo: 0, amarillo: 0, verde: 0 },
  filtro: 'todos',
  busqueda: '',
  seleccionado: null,
  vista: 'mapa',
  verTodos: false,
  boletinSel: null,
  bol: { filtro: 'todos', busqueda: '', marcados: new Set() }
};

const FILAS_INICIALES = 15;

const esMovil = () => window.matchMedia('(max-width: 720px)').matches;
const normalizar = t => t.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

/* ---------- Preparar datos ---------- */
function prepararDatos() {
  const datos = window.SAT_DATOS;
  estado.datos = datos;
  estado.municipios = datos.municipios
    .map(m => ({ ...m, nivel: nivelDe(m.prob, datos) }))
    .sort((a, b) => b.prob - a.prob)
    .map((m, i) => ({ ...m, puesto: i + 1 }));
  estado.municipios.forEach(m => { estado.conteo[m.nivel]++; });
}

/* ---------- Barra superior ---------- */
function pintarTopbar() {
  const d = estado.datos;
  document.getElementById('topbarSub').textContent = `Pronóstico de ${d.mes} · corte ${d.corte_texto}`;
  const rojos = estado.conteo.rojo;
  const pill = document.getElementById('alertPill');
  pill.classList.toggle('is-calm', rojos === 0);
  document.getElementById('alertPillText').innerHTML = rojos === 0
    ? 'Sin alertas'
    : `${rojos}<span class="pill-long"> ${rojos === 1 ? 'municipio' : 'municipios'}</span> en alerta`;
  document.getElementById('chipSimulados').hidden = !d.datos_simulados;
  document.getElementById('avisoEjemplo').hidden = d.origen !== 'ejemplo';
  document.getElementById('mapaMes').textContent = d.mes.charAt(0).toUpperCase() + d.mes.slice(1);
}

/* ---------- Tarjetas del semáforo ---------- */
function pintarKpis() {
  const d = estado.datos, c = estado.conteo, total = estado.municipios.length;
  const tarjetas = [
    { nivel: 'rojo', etiqueta: 'En alerta', regla: `Probabilidad ≥ ${num(d.umbral)}` },
    { nivel: 'amarillo', etiqueta: 'En precaución', regla: `Entre ${num(d.umbral * d.factor_amarillo, 3)} y ${num(d.umbral)}` },
    { nivel: 'verde', etiqueta: 'Sin alerta', regla: `Por debajo de ${num(d.umbral * d.factor_amarillo, 3)}` }
  ];
  document.getElementById('kpis').innerHTML = tarjetas.map(t => `
    <article class="card kpi kpi--${t.nivel}">
      <div class="kpi__top"><span class="kpi__label">${t.etiqueta}</span>${badge(t.nivel)}</div>
      <span class="kpi__value">${c[t.nivel]}<small>de ${total}</small></span>
      <span class="kpi__desc">${t.regla}</span>
    </article>`).join('');

  document.getElementById('leyenda').innerHTML = ['rojo', 'amarillo', 'verde']
    .map(n => `<span><i class="mark mark--${n}"></i>${NIVELES[n].nombre} (${c[n]})</span>`).join('') +
    '<span class="muted">Toque un municipio para ver por qué</span>';
}

/* ---------- Detalle del municipio ---------- */
function pintarDetalle() {
  const m = estado.municipios.find(x => x.codigo === estado.seleccionado);
  const el = document.getElementById('detalle');
  if (!m) { el.innerHTML = '<p class="empty">Seleccione un municipio en el mapa o en el ranking.</p>'; return; }
  const d = estado.datos;
  const pAm = d.umbral * d.factor_amarillo;
  const tieneBoletin = Boolean(d.boletines && d.boletines[m.codigo]);

  el.innerHTML = `
    <div class="detail detail--${m.nivel}">
      <div class="detail__head">
        <div>
          <h2 class="detail__name">${esc(m.municipio)}</h2>
          <p class="detail__code">Código DANE ${esc(m.codigo)} · puesto ${m.puesto} de ${estado.municipios.length}</p>
        </div>
        ${badge(m.nivel)}
      </div>
      <div>
        <div class="detail__prob"><strong>${pct(m.prob)}</strong><span>de probabilidad en ${esc(d.mes)}</span></div>
        <div style="margin-top:12px">
          <div class="gauge" role="img" aria-label="Probabilidad ${pct(m.prob)}; umbral de alerta ${num(d.umbral)}">
            <div class="gauge__fill fill--${m.nivel}" style="width:${Math.min(100, m.prob * 100)}%"></div>
            <div class="gauge__mark" style="left:${pAm * 100}%;opacity:.45"></div>
            <div class="gauge__mark" style="left:${d.umbral * 100}%"></div>
          </div>
          <div class="gauge__labels"><span>0 %</span><span>Umbral ${num(d.umbral)}</span><span>100 %</span></div>
        </div>
      </div>
      <div class="stack">
        <h3 class="detail__h3">Por qué</h3>
        <ol class="reasons">
          ${m.razones.map((r, i) => `<li><span class="reasons__n">${i + 1}</span><div><p class="reasons__t">${esc(r.etiqueta)}</p><p class="reasons__d">${esc(r.detalle)}</p></div></li>`).join('')}
        </ol>
      </div>
      ${tieneBoletin ? `<div class="detail__actions">
        <button class="btn btn--primary" data-boletin="${esc(m.codigo)}">Ver boletín</button>
        <button class="btn" data-pdf="${esc(m.codigo)}">Descargar PDF</button>
      </div>` : ''}
    </div>`;
}

/* ---------- Filtros y ranking ---------- */
function pintarFiltros() {
  const c = estado.conteo;
  const opciones = [
    { id: 'todos', texto: `Todos (${estado.municipios.length})` },
    { id: 'rojo', texto: `Rojo (${c.rojo})`, mark: 'rojo' },
    { id: 'amarillo', texto: `Amarillo (${c.amarillo})`, mark: 'amarillo' },
    { id: 'verde', texto: `Verde (${c.verde})`, mark: 'verde' }
  ];
  const cont = document.getElementById('filtros');
  cont.innerHTML = opciones.map(o => `
    <button type="button" data-filtro="${o.id}" aria-pressed="${estado.filtro === o.id}">
      ${o.mark ? `<i class="mark mark--${o.mark}" aria-hidden="true"></i>` : ''}${o.texto}
    </button>`).join('');
  cont.onclick = e => {
    const b = e.target.closest('[data-filtro]');
    if (!b) return;
    estado.filtro = b.dataset.filtro;
    pintarFiltros();
    pintarRanking();
  };
}

function pintarRanking() {
  const d = estado.datos;
  const q = normalizar(estado.busqueda.trim());
  const filas = estado.municipios.filter(m =>
    (estado.filtro === 'todos' || m.nivel === estado.filtro) &&
    (!q || normalizar(m.municipio).includes(q)));

  const visibles = estado.verTodos ? filas : filas.slice(0, FILAS_INICIALES);
  const cont = document.getElementById('verMasCont');
  cont.hidden = filas.length <= FILAS_INICIALES;
  document.getElementById('verMas').textContent = estado.verTodos
    ? 'Mostrar menos'
    : `Mostrar los ${filas.length} municipios`;

  document.getElementById('tablaRanking').innerHTML = visibles.map(m => `
    <tr class="${m.codigo === estado.seleccionado ? 'is-selected' : ''}">
      <td class="num">${m.puesto}</td>
      <td class="c-mun"><strong>${esc(m.municipio)}</strong></td>
      <td class="c-prob">
        <div class="prob">
          <span class="prob__val">${pct(m.prob)}</span>
          <span class="prob__bar" aria-hidden="true">
            <span class="prob__fill fill--${m.nivel}" style="width:${m.prob * 100}%"></span>
            <span class="prob__mark" style="left:${d.umbral * 100}%"></span>
          </span>
        </div>
      </td>
      <td class="c-niv">${badge(m.nivel)}</td>
      <td class="c-raz"><span class="razon">${esc(m.razones[0].detalle)}</span></td>
      <td class="c-acc"><button class="btn btn-ver" data-ver="${esc(m.codigo)}" aria-label="Ver detalle de ${esc(m.municipio)}">Ver detalle</button></td>
    </tr>`).join('');

  document.getElementById('sinResultados').hidden = filas.length > 0;
}

/* ---------- Selección ---------- */
function seleccionar(codigo, { origen } = {}) {
  estado.seleccionado = codigo;
  estado.boletinSel = codigo;
  pintarDetalle();
  pintarRanking();
  Mapa.resaltar(codigo, origen === 'tabla');
  const m = estado.municipios.find(x => x.codigo === codigo);
  if (m) anunciar(`${m.municipio}: ${pct(m.prob)}, ${NIVELES[m.nivel].nombre}`);

  // En celular, o al venir de la tabla, se lleva la vista al detalle
  if (origen === 'tabla' || (origen === 'mapa' && esMovil())) {
    document.getElementById(origen === 'tabla' && !esMovil() ? 'map' : 'detalle')
      .scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

/* ---------- Vista del modelo ---------- */
function pintarModelo() {
  const d = estado.datos, met = d.metricas;
  const exactitudTrivial = Math.round((1 - met.tasa_positivos) * 100);
  document.getElementById('periodoPrueba').textContent = `Prueba: ${met.periodo}`;
  document.getElementById('notaShap').textContent = d.origen === 'ejemplo' ? 'Valores de ejemplo' : '';
  document.getElementById('kpisModelo').innerHTML = `
    <article class="card kpi"><span class="kpi__label">Recall</span>
      <span class="kpi__value">${num(met.modelo.recall)}<small>base ${num(met.linea_base.recall)}</small></span>
      <span class="kpi__desc">De cada 100 meses con movimiento en masa, el modelo avisó en ${Math.round(met.modelo.recall * 100)}.</span></article>
    <article class="card kpi"><span class="kpi__label">PR-AUC</span>
      <span class="kpi__value">${num(met.modelo.pr_auc)}<small>base ${num(met.linea_base.pr_auc)}</small></span>
      <span class="kpi__desc">Resume precisión y recall en todos los umbrales.</span></article>
    <article class="card kpi"><span class="kpi__label">Meses con evento</span>
      <span class="kpi__value">${num(met.tasa_positivos * 100, 1)}<small>%</small></span>
      <span class="kpi__desc">Por eso no se usa la exactitud: decir siempre "no" acertaría el ${exactitudTrivial} %.</span></article>`;

  // Esquema de validación: sale de los datos, no de un dibujo fijo.
  // Un timeline pintado a mano sobrevive a que el modelo cambie y termina
  // contando una validación que nunca se corrió.
  pintarTimeline(d);
  document.getElementById('limitaciones').innerHTML = d.limitaciones.map(l => `<li>${esc(l)}</li>`).join('');
}

/* La línea de tiempo del backtest real: una fila por año, con los años que
   aportaron meses de prueba marcados como validación. Un timeline pintado a mano
   sobrevive a que el modelo cambie y termina contando una validación que nunca
   se corrió, así que las dos filas salen de los datos. */
function pintarTimeline(d) {
  const v = d.validacion;
  const el = document.getElementById('timeline');
  if (!v || !el) return;

  const anios = [];
  for (let a = v.anio_inicio; a <= v.anio_fin; a++) anios.push(a);
  const conPrueba = new Set((v.anios_con_prueba || []).map(a => a.anio));

  el.innerHTML =
    '<span></span>' +
    anios.map(a => `<span class="timeline__year">${a}</span>`).join('') +
    `<span class="timeline__lab">Mes a mes<span class="sr-only">: ${esc(v.descripcion)}</span></span>` +
    anios.map(a => `<span class="tl ${conPrueba.has(a) ? 'tl--val' : 'tl--train'}" aria-hidden="true"></span>`).join('');

  document.getElementById('notaTimeline').textContent = `${v.meses} meses fuera de muestra`;
  document.getElementById('leyendaTimeline').innerHTML =
    '<span><i class="tl tl--train"></i>Sirve para entrenar</span>' +
    '<span><i class="tl tl--val"></i>Se predice sin haberlo visto</span>' +
    `<span class="muted">${esc(v.descripcion)}</span>`;
}

function pintarUmbral() {
  const d = estado.datos, pAm = d.umbral * d.factor_amarillo, c = estado.conteo;
  document.getElementById('reglas').innerHTML = `
    <div class="rule"><i class="mark mark--rojo"></i><div><p class="rule__t">Rojo · ${c.rojo} municipios</p><p class="rule__d">Probabilidad mayor o igual al umbral (${num(d.umbral)}).</p></div></div>
    <div class="rule"><i class="mark mark--amarillo"></i><div><p class="rule__t">Amarillo · ${c.amarillo} municipios</p><p class="rule__d">Al menos el ${Math.round(d.factor_amarillo * 100)} % del umbral (${num(pAm, 3)}).</p></div></div>
    <div class="rule"><i class="mark mark--verde"></i><div><p class="rule__t">Verde · ${c.verde} municipios</p><p class="rule__d">Por debajo de ${num(pAm, 3)}.</p></div></div>`;
  document.getElementById('notaCurva').textContent = d.origen === 'ejemplo' ? 'Curva de ejemplo' : 'Datos de validación';

  // Por qué este umbral. El texto lo arma el modelo, no la maqueta: si el
  // umbral se recalcula, la explicación tiene que cambiar con el.
  const met = d.metricas;
  document.getElementById('tituloUmbral').textContent = `Por qué ${num(d.umbral)}`;
  document.getElementById('textoUmbral').innerHTML = `
    <p>El umbral no se copia de ningún sitio: se eligió en el backtest como el que deja en
       alerta unos ${num(met.alertas_por_mes, 1)} municipios por mes, que es lo que un equipo
       puede revisar. Con ese valor el modelo alcanza un recall de ${num(met.modelo.recall)}
       frente a ${num(met.linea_base.recall)} de la línea base.</p>
    <p>Se prioriza el recall porque un falso negativo es un deslizamiento sin preparación,
       pero el costo está en las visitas: solo el ${pct(met.modelo.precision)} de las alertas
       resulta en positivo, así que la mayor parte del esfuerzo se va en confirmar que no pasa nada.</p>
    <p>Con un umbral más bajo se detectan más eventos y aumentan las falsas alarmas;
       con uno más alto pasa lo contrario. La curva de abajo muestra el canje.</p>`;
}

/* ---------- Boletines ---------- */
function pintarBoletin() {
  Boletin.pintar(estado.datos, estado.municipios, estado.boletinSel || estado.datos.boletin_destacado);
  pintarListaBoletines();
}

function pintarListaBoletines() {
  const c = estado.conteo, f = estado.bol.filtro;
  document.getElementById('bolFiltros').innerHTML = [
    { id: 'todos', texto: 'Todos' },
    { id: 'rojo', texto: `Rojo ${c.rojo}` },
    { id: 'amarillo', texto: `Amar. ${c.amarillo}` },
    { id: 'verde', texto: `Verde ${c.verde}` }
  ].map(o => `<button type="button" data-bol-filtro="${o.id}" aria-pressed="${f === o.id}">${
    o.id !== 'todos' ? `<i class="mark mark--${o.id}" aria-hidden="true"></i>` : ''}${o.texto}</button>`).join('');

  estado.bol.visibles = Boletin.pintarLista(estado.municipios, {
    seleccionado: estado.boletinSel || estado.datos.boletin_destacado,
    filtro: f, busqueda: estado.bol.busqueda, marcados: estado.bol.marcados
  });
  pintarMarcados();
}

/* Lleva el municipio activo a la vista dentro de la lista (sin mover la página) */
function centrarEnLista() {
  const lista = document.getElementById('bolLista');
  const activo = lista.querySelector('.is-active');
  if (activo) lista.scrollTop = activo.offsetTop - lista.clientHeight / 2 + activo.clientHeight / 2;
}

function pintarMarcados() {
  const n = estado.bol.marcados.size;
  document.getElementById('bolMarcadosTxt').textContent =
    n === 0 ? 'Ninguno marcado' : `${n} ${n === 1 ? 'municipio marcado' : 'municipios marcados'}`;
  document.getElementById('bolLimpiar').hidden = n === 0;
  const btn = document.getElementById('btnSeleccion');
  btn.disabled = n === 0;
  btn.querySelector('span').textContent = n === 0 ? 'Descargar marcados' : `Descargar marcados (${n})`;
}

/* Genera el PDF dejando que el botón muestre que está trabajando */
function conEspera(boton, tarea) {
  const textoOriginal = boton.innerHTML;
  boton.disabled = true;
  boton.setAttribute('aria-busy', 'true');
  if (boton.dataset.pdfNivel) boton.querySelector('span').textContent = '…';
  setTimeout(() => {
    try { tarea(); }
    catch (err) { console.error(err); alert(err.message || 'No se pudo generar el PDF.'); }
    finally {
      boton.innerHTML = textoOriginal; boton.removeAttribute('aria-busy');
      boton.disabled = boton.id === 'btnSeleccion' ? estado.bol.marcados.size === 0 : false;
    }
  }, 30);
}

function iniciarBoletines() {
  pintarBoletin();

  document.getElementById('bolBuscar').addEventListener('input', e => {
    estado.bol.busqueda = e.target.value;
    pintarListaBoletines();
  });
  // Enter en el buscador abre el primer resultado
  document.getElementById('bolBuscar').addEventListener('keydown', e => {
    if (e.key !== 'Enter' || !estado.bol.visibles || !estado.bol.visibles.length) return;
    e.preventDefault();
    estado.boletinSel = estado.bol.visibles[0].codigo;
    pintarBoletin();
  });
  document.getElementById('bolFiltros').addEventListener('click', e => {
    const b = e.target.closest('[data-bol-filtro]');
    if (!b) return;
    estado.bol.filtro = b.dataset.bolFiltro;
    pintarListaBoletines();
  });
  document.getElementById('bolLista').addEventListener('click', e => {
    const ver = e.target.closest('[data-ver-boletin]');
    if (ver) {
      estado.boletinSel = ver.dataset.verBoletin;
      Boletin.pintar(estado.datos, estado.municipios, estado.boletinSel);
      pintarListaBoletines();
      if (window.matchMedia('(max-width: 1024px)').matches) {
        document.getElementById('boletinVista').scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  });
  document.getElementById('bolLista').addEventListener('change', e => {
    const chk = e.target.closest('[data-marcar]');
    if (!chk) return;
    if (chk.checked) estado.bol.marcados.add(chk.dataset.marcar); else estado.bol.marcados.delete(chk.dataset.marcar);
    pintarMarcados();
  });
  document.getElementById('bolMarcarVisibles').addEventListener('click', () => {
    (estado.bol.visibles || []).forEach(m => estado.bol.marcados.add(m.codigo));
    pintarListaBoletines();
  });
  document.getElementById('bolLimpiar').addEventListener('click', () => {
    estado.bol.marcados.clear();
    pintarListaBoletines();
  });
  document.getElementById('btnSeleccion').addEventListener('click', e => {
    conEspera(e.currentTarget, () => {
      const n = Boletin.descargarMarcados(estado.datos, estado.municipios, estado.bol.marcados);
      anunciar(`PDF generado con ${n} ${n === 1 ? 'boletín' : 'boletines'}`);
    });
  });

  document.getElementById('btnPdf').addEventListener('click', e => {
    const b = e.currentTarget;
    conEspera(b, () => Boletin.descargarUno(estado.datos, estado.municipios, b.dataset.codigo));
  });
  document.getElementById('descargasNivel').addEventListener('click', e => {
    const b = e.target.closest('[data-pdf-nivel]');
    if (!b) return;
    conEspera(b, () => {
      const n = Boletin.descargarNivel(estado.datos, estado.municipios, b.dataset.pdfNivel);
      anunciar(`PDF generado con ${n} boletines`);
    });
  });
}

/* ---------- Gráficas según la vista visible ---------- */
function dibujarGraficas() {
  if (estado.vista === 'modelo') { Graficos.metricas(estado.datos); Graficos.shap(estado.datos); }
  if (estado.vista === 'umbral') Graficos.umbral(estado.datos);
}

/* ---------- Navegación ---------- */
function irA(vista) {
  estado.vista = vista;
  document.querySelectorAll('.nav__item').forEach(i => {
    const activo = i.dataset.view === vista;
    i.classList.toggle('is-active', activo);
    if (activo) i.setAttribute('aria-current', 'page'); else i.removeAttribute('aria-current');
  });
  document.querySelectorAll('[data-view-panel]').forEach(p => p.classList.toggle('is-visible', p.dataset.viewPanel === vista));
  document.getElementById('viewTitle').textContent = TITULOS[vista];
  document.title = `${TITULOS[vista]} · SAT Santander`;
  if (vista === 'mapa') setTimeout(() => { Mapa.invalidar(); Mapa.ajustar(); }, 60);
  dibujarGraficas();
  cerrarMenu();
  window.scrollTo({ top: 0 });
}

function cerrarMenu() {
  document.getElementById('sidebar').classList.remove('is-open');
  document.getElementById('scrim').hidden = true;
  document.getElementById('menuBtn').setAttribute('aria-expanded', 'false');
}

function iniciarNavegacion() {
  document.querySelectorAll('.nav__item').forEach(i => i.addEventListener('click', () => irA(i.dataset.view)));

  const sidebar = document.getElementById('sidebar');
  const scrim = document.getElementById('scrim');
  const menuBtn = document.getElementById('menuBtn');
  menuBtn.addEventListener('click', () => {
    const abierto = sidebar.classList.toggle('is-open');
    scrim.hidden = !abierto;
    menuBtn.setAttribute('aria-expanded', String(abierto));
    if (abierto) sidebar.querySelector('.nav__item').focus();
  });
  scrim.addEventListener('click', cerrarMenu);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') cerrarMenu(); });

  // Botones dentro del contenido
  document.addEventListener('click', e => {
    const ir = e.target.closest('[data-ir]');
    if (ir) irA(ir.dataset.ir);
    const ver = e.target.closest('[data-ver]');
    if (ver) seleccionar(ver.dataset.ver, { origen: 'tabla' });
    const bol = e.target.closest('[data-boletin]');
    if (bol) { estado.boletinSel = bol.dataset.boletin; irA('boletin'); pintarBoletin(); centrarEnLista(); }
    const pdf = e.target.closest('[data-pdf]');
    if (pdf) conEspera(pdf, () => Boletin.descargarUno(estado.datos, estado.municipios, pdf.dataset.pdf));
  });

  document.getElementById('verMas').addEventListener('click', () => {
    const plegar = estado.verTodos;
    estado.verTodos = !estado.verTodos;
    pintarRanking();
    if (plegar) document.getElementById('ranking').scrollIntoView({ block: 'start' });
  });

  document.getElementById('buscar').addEventListener('input', e => {
    estado.busqueda = e.target.value;
    pintarRanking();
  });
}

/* ---------- Tema ---------- */
function iniciarTema() {
  const raiz = document.documentElement;
  const boton = document.getElementById('themeBtn');
  const meta = document.querySelector('meta[name="theme-color"]');
  function aplicar(tema) {
    raiz.setAttribute('data-theme', tema);
    const oscuro = tema === 'dark';
    boton.setAttribute('aria-label', oscuro ? 'Activar modo claro' : 'Activar modo oscuro');
    boton.setAttribute('aria-pressed', String(oscuro));
    meta.setAttribute('content', oscuro ? '#162033' : '#006B3F');
  }
  aplicar(raiz.getAttribute('data-theme') || 'light');
  boton.addEventListener('click', () => {
    const tema = raiz.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    aplicar(tema);
    guardar('sat-tema', tema);
    Mapa.refrescarTema();
    dibujarGraficas();
  });
}

/* ---------- Menú contraído (escritorio) ---------- */
function iniciarContraerMenu() {
  const raiz = document.documentElement;
  const boton = document.getElementById('collapseBtn');
  function aplicar(contraido) {
    if (contraido) raiz.setAttribute('data-sidebar', 'collapsed'); else raiz.removeAttribute('data-sidebar');
    const texto = contraido ? 'Expandir menú' : 'Contraer menú';
    boton.setAttribute('aria-label', texto);
    boton.setAttribute('title', texto);
    boton.setAttribute('aria-expanded', String(!contraido));
    boton.querySelector('.label').textContent = texto;
  }
  aplicar(raiz.getAttribute('data-sidebar') === 'collapsed');
  boton.addEventListener('click', () => {
    const contraido = raiz.getAttribute('data-sidebar') !== 'collapsed';
    aplicar(contraido);
    guardar('sat-menu', contraido ? 'collapsed' : 'expanded');
  });
  document.getElementById('sidebar').addEventListener('transitionend', e => {
    if (e.propertyName === 'width') { Mapa.ajustar(); dibujarGraficas(); }
  });
}

/* ---------- Arranque ---------- */
document.addEventListener('DOMContentLoaded', () => {
  if (!window.SAT_DATOS || !window.SAT_GEO) {
    document.getElementById('contenido').innerHTML =
      '<div class="card empty"><p>No se encontraron los datos. Verifique que existan <code>datos/sat_datos.js</code> y <code>datos/municipios.geo.js</code>.</p></div>';
    return;
  }
  prepararDatos();
  pintarTopbar();
  pintarKpis();
  pintarFiltros();
  Mapa.iniciar(window.SAT_GEO, estado.municipios, seleccionar);
  seleccionar(estado.municipios[0].codigo);
  pintarModelo();
  pintarUmbral();
  iniciarBoletines();

  iniciarNavegacion();
  iniciarTema();
  iniciarContraerMenu();
});
