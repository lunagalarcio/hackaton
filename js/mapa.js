/* =========================================================
   SAT Santander · Mapa (Leaflet, sin capa de fondo)
   Funciona sin internet: solo dibuja los límites municipales.
   ========================================================= */

const Mapa = (() => {
  let mapa = null;
  let capa = null;
  let seleccionado = null;
  const porCodigo = {};
  let infoPorCodigo = {};

  function colorNivel(nivel) {
    return { rojo: cssVar('--rojo'), amarillo: cssVar('--amarillo'), verde: cssVar('--verde') }[nivel];
  }

  function estilo(codigo) {
    const info = infoPorCodigo[codigo];
    const activo = codigo === seleccionado;
    return {
      fillColor: info ? colorNivel(info.nivel) : cssVar('--superficie-2'),
      fillOpacity: activo ? 0.95 : 0.78,
      color: activo ? cssVar('--texto') : cssVar('--mapa-borde'),
      weight: activo ? 3 : 1
    };
  }

  function iniciar(geo, municipios, alSeleccionar) {
    infoPorCodigo = Object.fromEntries(municipios.map(m => [m.codigo, m]));

    mapa = L.map('map', {
      zoomSnap: 0.25,
      scrollWheelZoom: false,
      attributionControl: true,
      tap: true
    });
    mapa.attributionControl.setPrefix('');
    mapa.attributionControl.addAttribution('Límites municipales: IGAC/DANE');

    capa = L.geoJSON(geo, {
      style: f => estilo(f.properties.codigo),
      onEachFeature: (f, layer) => {
        const codigo = f.properties.codigo;
        porCodigo[codigo] = layer;
        const info = infoPorCodigo[codigo];
        const texto = info
          ? `<strong>${esc(info.municipio)}</strong><br>${pct(info.prob)} · ${NIVELES[info.nivel].nombre}`
          : esc(f.properties.nombre);
        layer.bindTooltip(texto, { sticky: true, className: 'map-tip', direction: 'top' });
        layer.on('click', () => alSeleccionar(codigo, { origen: 'mapa' }));
        layer.on('mouseover', () => { if (codigo !== seleccionado) layer.setStyle({ fillOpacity: 0.95 }); });
        layer.on('mouseout', () => layer.setStyle(estilo(codigo)));
      }
    }).addTo(mapa);

    ajustar();
    // Al cambiar el tamaño de la ventana se reencuadra el departamento
    let t;
    window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(invalidar, 150); });
  }

  const visible = () => mapa && mapa.getContainer().offsetWidth > 0;

  function ajustar() {
    if (!mapa || !capa || !visible()) return;
    mapa.invalidateSize();
    mapa.fitBounds(capa.getBounds(), { padding: [12, 12] });
  }

  function resaltar(codigo, centrar) {
    const anterior = seleccionado;
    seleccionado = codigo;
    if (anterior && porCodigo[anterior]) porCodigo[anterior].setStyle(estilo(anterior));
    const capaMun = porCodigo[codigo];
    if (!capaMun) return;
    capaMun.setStyle(estilo(codigo));
    capaMun.bringToFront();
    if (centrar && visible()) {
      const limites = capaMun.getBounds();
      if (!mapa.getBounds().contains(limites)) mapa.fitBounds(limites, { maxZoom: 10, padding: [40, 40] });
    }
  }

  function refrescarTema() {
    if (!capa) return;
    capa.eachLayer(l => l.setStyle(estilo(l.feature.properties.codigo)));
  }

  function invalidar() { if (visible()) mapa.invalidateSize(); }

  return { iniciar, resaltar, refrescarTema, invalidar, ajustar };
})();
