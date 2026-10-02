/* =========================================================
   SAT Santander · Datos de prueba
   Cuando exista el backend (Firebase, API, etc.), este archivo
   se reemplaza por una consulta. La estructura puede quedarse igual.
   Niveles válidos: "vigilancia" | "aviso" | "roja"
   Coordenadas aproximadas (WGS84).
   ========================================================= */

const SAT_DATA = {
  kpis: [
    {
      label: 'Monitoreo hidrológico',
      valor: 'Estable',
      numerico: false,
      nivel: 'vigilancia',
      descripcion: 'Cuencas Suárez y Chicamocha bajo umbral.'
    },
    {
      label: 'Municipios en aviso',
      valor: '05',
      numerico: true,
      nivel: 'aviso',
      descripcion: 'Soto Norte y García Rovira con lluvias moderadas.'
    },
    {
      label: 'Alertas de evacuación',
      valor: '02',
      numerico: true,
      nivel: 'roja',
      descripcion: 'Nivel crítico en Puerto Wilches y Barrancabermeja.'
    }
  ],

  puntos: [
    {
      municipio: 'Puerto Wilches',
      provincia: 'Yariguíes',
      punto: 'Río Magdalena · sector Murallas',
      valor: null,              // pendiente: dato real del sensor
      unidad: 'm',
      nivel: 'roja',
      lat: 7.3475, lng: -73.8983
    },
    {
      municipio: 'Barrancabermeja',
      provincia: 'Yariguíes',
      punto: 'Río Magdalena',
      valor: null,
      unidad: 'm',
      nivel: 'roja',
      lat: 7.0653, lng: -73.8547
    },
    {
      municipio: 'Girón',
      provincia: 'Soto',
      punto: 'Sensor Río de Oro',
      valor: 4.80,
      unidad: 'm',
      nivel: 'roja',
      lat: 7.0703, lng: -73.1686
    },
    {
      municipio: 'Pescadero',
      provincia: 'Soto',
      punto: 'Talud vía Bucaramanga–San Gil',
      valor: null,
      unidad: 'mm/h',
      nivel: 'aviso',
      lat: 6.8350, lng: -73.0650
    },
    {
      municipio: 'Guadalupe',
      provincia: 'Comunera',
      punto: 'Quebrada Las Gachas',
      valor: 1.20,
      unidad: 'm',
      nivel: 'vigilancia',
      lat: 6.2456, lng: -73.4189
    }
  ],

  reportes: [
    {
      lugar: 'Puerto Wilches',
      hace: 'hace 12 min',
      texto: 'Desbordamiento inminente en el sector Murallas.',
      nivel: 'roja'
    },
    {
      lugar: 'Pescadero · vía Bucaramanga–San Gil',
      hace: 'hace 45 min',
      texto: 'Caída leve de rocas y lodo sobre la calzada.',
      nivel: 'aviso'
    },
    {
      lugar: 'Girón · Río de Oro',
      hace: '[hora del reporte]',
      texto: 'El sensor supera el umbral crítico (4,80 m).',
      nivel: 'roja'
    }
  ]
};
