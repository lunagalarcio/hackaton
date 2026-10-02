# SAT Santander · Alerta temprana por movimiento en masa

Aplicativo web que, cada mes, dice **qué municipios de Santander deben estar
en alerta por movimiento en masa, con qué probabilidad y por qué**, usando solo
la información disponible el día 1 del mes.

No es un visor de datos: hay un modelo entrenado, validado fuera de muestra y
con sus límites escritos a la vista. El sitio web es estático y no calcula
nada — lee un diccionario que produce el modelo en Python.

- **87 municipios**, corte **1 de octubre de 2025**
- **16 en rojo · 25 en amarillo · 46 sin alerta**
- Umbral elegido por capacidad operativa: **0,18**

---

## Cómo abrirlo

Doble clic en `index.html`. **No necesita internet ni servidor**: las
librerías, las fuentes y los límites municipales están dentro del proyecto.

Para probarlo en el celular dentro de la misma red, con VS Code y la extensión
Live Server, se abre la dirección que muestra (por ejemplo
`http://192.168.x.x:5500`) desde el navegador del teléfono.

## Vistas

| Vista | Qué muestra |
|---|---|
| Mapa de alertas | Semáforo de los 87 municipios, detalle con las tres razones principales y ranking de probabilidad con búsqueda y filtros |
| Boletín | Un boletín por municipio con texto según su nivel, verificación de cifras, descarga individual y descarga por nivel (alerta roja, precaución, sin alerta o todos) en un solo PDF con índice |
| Modelo y métricas | Recall y PR-AUC frente a la línea base, importancia SHAP, esquema de validación y limitaciones |
| Umbral y semáforo | Reglas del semáforo y curva de recall y precisión según el umbral |

También tiene modo oscuro, menú lateral contraíble y diseño adaptable a
celular, tablet y escritorio.

---

## El modelo

### Qué predice

Para cada municipio y cada mes, la probabilidad de que se registre al menos un
movimiento en masa. Es una **probabilidad por municipio-mes**, no una decisión.

### Qué modelo se usó: regresión logística

`sklearn.linear_model.LogisticRegression` dentro de un `Pipeline` con
`StandardScaler`. Se probaron dos familias:

| Modelo | ROC-AUC | AP | Brier |
|---|---|---|---|
| **Regresión logística** | **0,706** | **0,188** | **0,083** |
| Gradient boosting | 0,687 | 0,180 | 0,084 |
| Línea base (histórico del mismo mes) | 0,611 | 0,141 | — |
| Lluvia acumulada 3 meses | 0,537 | 0,103 | — |
| Azar | 0,500 | 0,096 | 0,904 |

Se publica la logística por dos razones:

1. **Gana.** Mejor ROC-AUC y mejor AP que gradient boosting en este panel.
2. **Es coherente con las razones del boletín.** Obliga a que el efecto de cada
   variable sea monótono, así que el texto "más lluvia acumulada → más riesgo"
   no puede contradecir el signo del coeficiente. Un árbol puede afirmar que un
   municipio es más seguro que otro en casi todo lo medido y aun así ponerlo en
   rojo; eso no se puede explicar en una frase.

**Ojo con la diferencia entre las dos tablas de este README.** La de arriba son
métricas de **orden** (ROC-AUC, AP): miden solo si el modelo *ordena* bien los
municipios. Las de la sección siguiente son **operativas** (recall,
precisión): miden cuántos de los 10 municipios alertados realmente tuvieron un
movimiento en masa. Un modelo puede ordenar bien y aun así servir de poco si el
número de alertas no es el que el equipo puede revisar.

### Sin `class_weight="balanced"` — y por qué

Solo 9,5 % de los municipios-mes son positivos. Con pesos balanceados el
modelo mejora un poco el orden pero **destruye las probabilidades**: la mediana
sale en 0,42 cuando la tasa real es 0,095, y el Brier sube de 0,083 a 0,213.

Como el aplicativo muestra "probabilidad del 30,8 %" al usuario, unas
probabilidades infladas por un factor cuatro son directamente misinformation.
La regresión logística se publica **sin balancear** y por eso su recall@10 es
ligeramente menor que el de la versión balanceada: es un precio consciente por
poder mostrar un número honesto.

El mismo ajuste está en `src/evaluacion.py` y en `src/publicar.py`. Si cambia
en uno, cambia en el otro.

### Validación: ventana creciente, no partición aleatoria

El sistema se usa hacia adelante en el tiempo. Por eso, para predecir cada mes
se entrena **solo con meses anteriores** y nunca ve ese mes ni los siguientes.
Una partición aleatoria habría mezclado años y dado un resultado demasiado
optimista.

- 71 meses fuera de muestra, de enero de 2020 a septiembre de 2025
- 6.177 predicciones, 590 positivas
- Empieza en 2020 porque antes hay muy pocos positivos mensuales para que un
  modelo tabular tenga algo que aprender

**Febrero de 2020 está excluido** a propósito: no tuvo ningún positivo, y un
mes sin positivos no aporta nada a recall ni precisión (el denominador es
cero). Los meses con cero positivos se saltan y el esquema de validación del
aplicativo lo muestra tal cual, sin esconder el hueco.

### Importancia de variables (SHAP)

Se calcula SHAP local sobre los 87 municipios del corte, con la regresión
lineal como explicador (`shap.LinearExplainer`), y la importancia global es el
promedio de los valores absolutos. Las 27 variables se agrupan en **seis
razones** que el aplicativo sabe redactar, y cada municipio muestra **las tres
de mayor contribución**:

| Razón (`GRUPOS_RAZONES`) | Qué mira | Variables |
|---|---|---|
| `lluvia_rel_promedio` | lluvia frente a su climatología | 11: rezagos 1–6 meses, sumas 3 y 6, acumulada 12, anomalías y razón sobre el promedio histórico |
| `meses_mm_12m` | historial de movimientos en masa | `mm_3m`, `mm_6m`, `mm_12m`, `mm_24m`, días desde el último |
| `emergencias_12m` | otros eventos en 12 meses | inundación, incendio forestal, vendaval, creciente súbita |
| `tasa_historica` | qué tanto se mueve en ese municipio | `mm_tasa_historica` |
| `mes_sin` / `mes_cos` | estacionalidad | el mes del año como seno y coseno |
| `terreno` | dónde está | altitud, latitud, longitud |

Si se agrega una variable a `features.VARIABLES` y no se mapea a un grupo, la
exportación **falla con un mensaje explícito** en vez de dejar un boletín mudo.

### El umbral se elige por capacidad operativa, no por una métrica

Recorre los umbrales candidatos y se queda con el que deja en alerta **unos 10
municipios por mes**, que es lo que un equipo puede revisar. Salió **0,18**.
Consecuencia: se prioriza el recall, porque un falso negativo es un
deslizamiento sin preparación, pero el costo está en las visitas — solo el
22,4 % de las alertas resulta en positivo.

```
curva_umbral:
  0.14 -> recall 0.402 | precision 0.203
  0.16 -> recall 0.327 | precision 0.216
  0.18 -> recall 0.263 | precision 0.224   <- elegido
  0.20 -> recall 0.202 | precision 0.224
  0.22 -> recall 0.158 | precision 0.235
```

El semáforo sale de ese umbral: rojo si `prob >= 0,18`, amarillo si
`prob >= 0,11` (60 % del umbral), verde si no.

### Comparación operativa contra la línea base

| | Recall | Precisión | PR-AUC |
|---|---|---|---|
| **Regresión logística** | **0,263** | **0,224** | **0,188** |
| Línea base (histórico del mismo mes) | 0,168 | 0,139 | 0,141 |
| Piso de azar (elegir 10 al azar) | 0,115 | — | 0,096 |

La línea base es la tasa histórica de movimientos en masa de ese municipio en
ese mismo mes del calendario, promediada sobre años anteriores. El modelo la
supera, pero no por mucho: **este problema es difícil**, y un equipo que
presente estos números debería admitirlo antes de que lo descubra otro.

> La línea base se evalúa eligiendo **exactamente 10 municipios por mes por
> ranking**. La diferencia no es sutil: como es una tasa sobre unos pocos años,
> decenas de municipios empatan en el mismo valor, y si se usara
> `puntaje >= percentil` arrastraría a todos los empatados y alertaría 60
> municipios por mes — con un recall que parece mejor solo porque está viendo
> más.

### Qué NO puede hacer el modelo

Están escritos en la interfaz, no escondidos:

- Solo ve el **total mensual** de lluvia, no la intensidad hora a hora. Un
  aguacero de dos horas en una ladera es invisible para él.
- Un municipio con laderas muy distintas recibe **un solo valor** de lluvia para
  todo su territorio.
- **Subregistro**: un municipio que reporta poco puede parecer más seguro de lo
  que es, porque el modelo aprende del registro, no de lo que pasó.
- No hay datos de sismos, cortes de talud, deforestación ni obras.
- Al 26 % de los meses con movimiento en masa caen dentro de los 10 municipios
  alertados. **Sirve para priorizar vigilancia, no para declarar que un
  municipio está seguro.**

---

## Herramientas

### Python 3.12.9 — `.venv`

| Librería | Versión | Para qué |
|---|---|---|
| pandas | 3.0.6 | panel municipio-mes, groupby, joins |
| numpy | 2.5.3 | arreglos y cálculo numérico |
| scipy | 1.18.1 | delays rezagados y estadística |
| scikit-learn | 1.9.1 | regresión logística, gradient boosting, métricas |
| shap | 0.52.0 | importancia global y razones por municipio |
| folium | 0.20.0 | inspección visual del geojson |
| matplotlib | 3.11.2 | gráficas exploratorias del cuaderno |

### Navegador — todo local, sin CDN

| Librería | Para qué |
|---|---|
| Leaflet 1.x | mapa de los 87 municipios, sin capa de fondo (offline) |
| Chart.js | gráficas de métricas, SHAP y curva de umbral |
| jsPDF + AutoTable | boletines en PDF con portada e índice |
| Inter + IBM Plex Mono | tipografías, servidas desde `vendor/fonts/` |

### Verificación

No hay `pytest` ni carpeta `tests/`. El proyecto se comprobaba ejecutando el
pipeline completo y contrastando salidas:

```powershell
# sintaxis de los seis módulos y del generador de boletines
.venv\Scripts\python.exe -m py_compile src\config.py src\data_clean.py `
    src\features.py src\evaluacion.py src\publicar.py cuaderno\boletines.py

# pipeline completo: backtest + modelo + exportación
.venv\Scripts\python.exe -m src.publicar

# sintaxis de cada archivo JS
node --check js\app.js
```

Para correr solo la auditoría de fugas o la prueba de variables trampa hacen
falta el marco cargado, así que no son módulos ejecutables por su cuenta:

```python
from src import config as C, data_clean as dc, features as ft

datos = dc.cargar_todo()
marco = ft.marco_de_modelo(ft.construir_variables(datos), datos.panel)

print(ft.auditar_fugas(datos, C.periodo_de(C.ANIO_OBJETIVO, C.MES_OBJETIVO)))
print(ft.demostrar_variable_trampa(marco))
```

Lo que sí se comprueba de forma explícita:

- **Auditoría de fugas** (`features.auditar_fugas`): 11.223 filas × 27 variables
  contra la fecha de corte. Ninguna variable puede ver el mes que predice.
- **Variables trampa** (`features.demostrar_variable_trampa`): entrena cuatro
  modelos, tres con una variable que regala el mes objetivo. Sirve para ver que
  la auditoría serviría de algo: si una fuga pasara, saldría con ROC-AUC de
  1,000 en vez de 0,70.

  | Escenario | ROC-AUC | AP |
  |---|---|---|
  | Solo histórico legítimo | 0,696 | 0,156 |
  | + lluvia del mes objetivo | 0,760 | 0,228 |
  | + eventos del mes objetivo | 0,990 | 0,854 |
  | + movimientos en masa del mes objetivo | **1,000** | **1,000** |

  Ese 1,000 no es un logro: es la definición de la fuga. Por eso el modelo que
  se publica usa solo el primer escenario.
- **`boletines.verificar_cifras`**: exige que **toda** cifra impresa en un
  boletín exista en el diccionario `cifras` de ese municipio. Corre en Python
  al generar y **otra vez en el navegador** (`boletin.js`), más estricta: si un
  número del texto no está respaldado, el botón de descarga se bloquea.

---

## Estructura

```
sat-santander/
├── index.html
├── css/styles.css
├── js/
│   ├── util.js        regla del semáforo, formatos
│   ├── mapa.js        mapa con Leaflet sin capa de fondo
│   ├── graficos.js    gráficas con Chart.js
│   ├── boletin.js     verificación de cifras y PDF con jsPDF
│   ├── banderas.js    banderas de municipios
│   └── app.js         navegación, ranking, detalle, tema
├── datos/
│   ├── sat_datos.js        salidas del modelo (window.SAT_DATOS)
│   ├── sat_datos.json      las mismas salidas en JSON
│   ├── municipios.geo.js   límites de los 87 municipios
│   ├── panel_municipio_mes.csv      panel principal (crudo)
│   ├── emergencias_santander.csv   eventos (crudo)
│   ├── municipios_santander.csv     catálogo (crudo)
│   └── santander_municipios.geojson geometría (crudo)
├── src/
│   ├── config.py        rutas, fechas, decodificación de periodo
│   ├── data_clean.py    carga, validación, normalización
│   ├── features.py      27 variables causales + auditoría de fugas
│   ├── evaluacion.py    backtest de ventana creciente
│   └── publicar.py      modelo final, umbral, SHAP, boletines, export
├── cuaderno/
│   └── boletines.py     plantillas por nivel y verificar_cifras
├── outputs/             CSV del backtest (no se versiona)
└── vendor/              Leaflet, Chart.js, jsPDF y fuentes (con licencias)
```

**Los CSV de `datos/` son la entrada y no se tocan.** Todo lo que produce el
modelo va a `datos/sat_datos.js`, `datos/sat_datos.json` y `outputs/`.

---

## Generar los datos

`datos/sat_datos.js` y `datos/sat_datos.json` los genera el modelo, no se
escriben a mano:

```powershell
.venv\Scripts\python.exe -m src.publicar
```

Eso carga los cuatro CSV, arma las variables, corre el backtest, entrena el
modelo final con corte 1 de octubre de 2025 y exporta el diccionario que lee el
aplicativo, más los CSV de `outputs/`. El aviso de "Datos de ejemplo"
desaparece solo cuando `origen` es `"modelo"`.

## Cómo se conecta el modelo con el aplicativo

| Pieza de Python | Dónde lo usa el aplicativo |
|---|---|
| `data_clean.py` carga y valida los CSV | alimenta todo |
| `features.py` arma 27 variables causales | columnas del modelo |
| `evaluacion.py` backtest de ventana creciente | `metricas`, `curva_umbral`, `validacion` |
| `publicar.py` entrena el final y exporta | `municipios`, `boletines`, `importancia` |
| `boletines.py` redacta y verifica cifras | texto de cada boletín |
| `municipios.geo.js` límites municipales | mapa de Leaflet |

El contrato es un solo diccionario: **el HTML no trae ni un nombre ni una
cifra**. `index.html` es estructura vacía; todo sale de `window.SAT_DATOS`. Si
el umbral o el mes cambian, la interfaz cambia sola.

```
window.SAT_DATOS = {
  origen, datos_simulados,   # "modelo" / false cuando ya no es prototipo
  mes, corte, umbral, factor_amarillo,
  municipios[],              # codigo, municipio, prob, puesto, razones[]
  importancia[],             # SHAP global
  metricas{},                # modelo, linea_base, tasa_positivos, curva_umbral
  validacion{},              # esquema de la ventana creciente
  boletines{},               # por código: titulo, parrafos, cifras, nivel
  boletin_destacado,
  limitaciones[]
}
```

## Datos de entrada

- **Panel** `panel_municipio_mes.csv`: 9.396 filas municipio-mes, 87 municipios,
  868 meses con movimiento en masa. El marco usable va 2017–2025: la variable de
  lluvia acumulada a 24 meses necesita dos años de historia y el panel arranca en
  2015. En el backtest salen 6.177 filas (590 positivas, 9,55 %).
- **Emergencias** `emergencias_santander.csv`: 5 tipos de evento. La etiqueta es
  `Movimiento en masa`; los otros cuatro entran como variables de contexto.
- **Municipios** `municipios_santander.csv`: 87 municipios, área y altitud.
- **Geometría** `santander_municipios.geojson` → `municipios.geo.js`, con los
  límites simplificados para que el mapa pese poco.

## Detalles que importan

- **Decodificar `periodo`** (`anio*12 + mes`): dividir sin corregir lleva
  diciembre al año siguiente. `config.anio_de_periodo` resta 1 antes de
  dividir. Centralizado porque se usaba en cuatro sitios con el bug duplicado.
- **El marco empieza en 2017**, no en 2015, por el requisito de 24 meses.
- **`dias_desde_ultimo_mm`** va con un valor enorme como "nunca ocurrió", no
  con cero, para que el modelo no lo lea como "pasó ayer".
- **Un mes sin positivos se salta** en las métricas, y el esquema de validación
  lo enseña en vez de esconderlo.
- **Las limitaciones se generan con los números del modelo**, no están escritas a
  mano. El "26 % de los meses" sale de recalcular el recall al umbral publicado.
  Al principio ese texto decía 20 % y se quedó viejo en silencio.
- **La línea base se evalúa con top-10 exacto por ranking.** La tasa histórica
  empata a decenas de municipios, así que `puntaje >= percentil` arrastraba a
  todos los empatados, alertaba 60 municipios por mes y sacaba un recall que
  parecía mejor solo por mirar más. Con top-10 real la comparación es justa y
  el modelo gana por poco.
- **`outputs/` se escribe en la misma corrida** que el JSON. Antes eran CSV de
  una versión anterior del modelo y mostraban un Brier de 0,21 frente al 0,08
  que dice el aplicativo.

## Fuentes

- Límites municipales: `santiblanko/colombia.geojson`, basado en cartografía
  IGAC/DANE, simplificado con mapshaper.
- Eventos: dataset de emergencias del departamento.