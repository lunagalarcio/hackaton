/* =========================================================
   SAT Santander · Utilidades compartidas
   ========================================================= */

const NIVELES = {
  rojo:     { nombre: 'Alerta',     corto: 'Rojo' },
  amarillo: { nombre: 'Precaución', corto: 'Amarillo' },
  verde:    { nombre: 'Sin alerta', corto: 'Verde' }
};

/* Escapa texto antes de insertarlo como HTML */
function esc(texto) {
  return String(texto)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* Número con coma decimal: 0.39 -> "0,39" */
function num(valor, decimales = 2) {
  return Number(valor).toLocaleString('es-CO', { minimumFractionDigits: decimales, maximumFractionDigits: decimales });
}

/* Probabilidad como porcentaje: 0.72 -> "72 %" */
function pct(valor) {
  return `${Math.round(valor * 100)} %`;
}

/* Regla del semáforo, la misma del cuaderno */
function nivelDe(prob, datos) {
  if (prob >= datos.umbral) return 'rojo';
  if (prob >= datos.umbral * datos.factor_amarillo) return 'amarillo';
  return 'verde';
}

function badge(nivel) {
  return `<span class="badge badge--${nivel}">${NIVELES[nivel].nombre.toUpperCase()}</span>`;
}

function guardar(clave, valor) {
  try { localStorage.setItem(clave, valor); } catch (e) { /* sin almacenamiento */ }
}

/* Lee una variable CSS del tema actual */
function cssVar(nombre) {
  return getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();
}

function anunciar(texto) {
  const el = document.getElementById('anuncio');
  el.textContent = '';
  setTimeout(() => { el.textContent = texto; }, 50);
}
