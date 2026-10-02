"""
Exporta las salidas del cuaderno al formato que lee el aplicativo web.

Pegue esta celda al final del cuaderno y ajuste los nombres marcados con
# AJUSTAR a los de su código. Genera datos/sat_datos.js, que reemplaza al
archivo de ejemplo.

Reglas:
- Ninguna cifra se escribe a mano: todo sale del modelo, del panel o del
  diccionario de cifras del boletín.
- Cada boletín se arma con cuaderno/boletines.py y pasa verificar_cifras antes
  de exportarse. Copie boletines.py junto al cuaderno.
"""
import json
import numpy as np

UMBRAL = 0.39            # AJUSTAR si cambia en validación
FACTOR_AMARILLO = 0.6

# ---------------------------------------------------------------------------
# 1. Probabilidades, razones y boletín de cada municipio
#    pred: DataFrame con codigo_dane (str de 5 dígitos), municipio, prob
#    valores[codigo]: dict con lo que pide boletines.generar_boletin, sacado del
#      panel al 1 de octubre (tasa_hist_pct, lluvia_mm, lluvia_ratio, mes_anterior,
#      mes, temporada, emergencias_12m, meses_mm_12m) y "orden": las variables de
#      ese municipio ordenadas por su valor SHAP local, de mayor a menor.
# ---------------------------------------------------------------------------
from boletines import generar_boletin

pred = pred.sort_values("prob", ascending=False).reset_index(drop=True)      # AJUSTAR
municipios, boletines = [], {}
for puesto, fila in enumerate(pred.itertuples(), start=1):
    codigo = str(fila.codigo_dane).zfill(5)                                   # AJUSTAR
    b = generar_boletin(fila.municipio, float(fila.prob), puesto, len(pred), UMBRAL,
                        valores[codigo], "1 de octubre de 2025", "octubre de 2025", 2025)
    municipios.append({"codigo": codigo, "municipio": fila.municipio,
                       "prob": round(float(fila.prob), 4), "razones": b.pop("razones")})
    boletines[codigo] = b   # si alguna cifra no tiene respaldo, generar_boletin lanza un error

# ---------------------------------------------------------------------------
# 2. Importancia global SHAP (media del valor absoluto)
#    shap_values: matriz (n, variables) de la clase positiva; X_test: DataFrame
#    ETIQUETAS: nombre legible de cada variable
# ---------------------------------------------------------------------------
ETIQUETAS = {                                                  # AJUSTAR
    "tasa_historica": "Tasa histórica del municipio",
    "lluvia_acum_2m": "Lluvia acumulada de 2 meses",
}
media_abs = np.abs(shap_values).mean(axis=0)
importancia = sorted(
    [{"etiqueta": ETIQUETAS.get(v, v), "valor": round(float(m), 4)} for v, m in zip(X_test.columns, media_abs)],
    key=lambda x: x["valor"], reverse=True,
)[:10]

# ---------------------------------------------------------------------------
# 3. Curva recall/precisión según umbral, calculada en VALIDACIÓN (no en prueba)
#    y_val, p_val: etiquetas y probabilidades de los pliegues de validación
# ---------------------------------------------------------------------------
from sklearn.metrics import precision_score, recall_score
curva = []
for t in np.round(np.arange(0.05, 0.81, 0.05).tolist() + [UMBRAL], 2):
    y_hat = (p_val >= t).astype(int)
    curva.append({
        "umbral": float(t),
        "recall": round(recall_score(y_val, y_hat), 3),
        "precision": round(precision_score(y_val, y_hat, zero_division=0), 3),
    })

# ---------------------------------------------------------------------------
# 4. Métricas en la prueba final (enero a septiembre de 2025)
# ---------------------------------------------------------------------------
metricas = {
    "periodo": "enero a septiembre de 2025",
    "modelo": {"nombre": "Bosque aleatorio", "recall": round(rec_modelo, 3),          # AJUSTAR
               "precision": round(prec_modelo, 3), "pr_auc": round(prauc_modelo, 3)},
    "linea_base": {"nombre": "Mismo mes del año anterior", "recall": round(rec_base, 3),
                   "precision": round(prec_base, 3), "pr_auc": round(prauc_base, 3)},
    "tasa_positivos": round(float(panel["hubo_mm"].mean()), 4),                       # AJUSTAR
}

datos = {
    "origen": "cuaderno",
    "datos_simulados": True,
    "mes": "octubre de 2025",
    "corte": "2025-10-01",
    "corte_texto": "1 de octubre de 2025",
    "umbral": UMBRAL,
    "factor_amarillo": FACTOR_AMARILLO,
    "municipios": municipios,
    "importancia": importancia,
    "metricas": metricas,
    "curva_umbral": curva,
    "boletines": boletines,
    "boletin_destacado": municipios[0]["codigo"],
    "limitaciones": [
        "Eventos detonados por lluvias intensas de pocas horas: la lluvia del modelo es mensual.",
        "Diferencias dentro del municipio: hay un solo valor de lluvia por municipio.",
        "Subregistro: un municipio que reporta poco puede parecer más seguro de lo que es.",
        "Causas que no están en los datos, como sismos, cortes de talud, deforestación u obras.",
    ],
}

with open("sat-santander/datos/sat_datos.js", "w", encoding="utf-8") as f:           # AJUSTAR ruta
    f.write("window.SAT_DATOS = ")
    json.dump(datos, f, ensure_ascii=False, indent=1)
    f.write(";\n")
print("Exportado:", len(municipios), "municipios")
