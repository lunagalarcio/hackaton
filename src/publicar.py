from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import data_clean as dc
from . import evaluacion as ev
from . import features as ft

# Ruta de salida que lee el aplicativo web. El sitio es estatico y se abre con
# doble clic en index.html, asi que no hay servidor: los datos viajan en un
# archivo .js que asigna una variable global. Se escribe tambien el .json por si
# alguien lo quiere consumir desde otro lado.
JS_SALIDA = C.RAIZ / "datos" / "sat_datos.js"
JSON_SALIDA = C.RAIZ / "datos" / "sat_datos.json"

FACTOR_AMARILLO = 0.6

# Presupuesto de visita mensual. El umbral no se copia de ningun lado: se elige
# como el que produce este numero de alertas, que es lo que un equipo puede
# atender. Con el corte 0.18 salen 9.7 alertas por mes en el backtest.
ALERTAS_POR_MES = 10

# El modelo que se publica es la regresion logistica, no el gradient boosting.
# En el backtest las dos casi empatan (AP 0.189 contra 0.180) y la logistica gana
# en average precision, pero sobre todo: sin class_weight="balanced" sus
# probabilidades quedan calibradas (Brier 0.083 contra 0.213) y eso es
# indispensable, porque el aplicativo le dice al municipio "probabilidad del
# 18 %". Con pesos balanceados la mediana de las probabilidades sale 0.42 cuando
# la tasa real es 9.5 %, y ese numero no le sirve de nada a nadie.
def _modelo():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=5000, C=1.0),
    )


# Las dos temporadas de mayor riesgo, tomadas de la tasa real de movimientos en
# masa por mes del ano y no de un supuesto. En el marco: octubre 18.4 %, abril
# 17.9 %, noviembre 17.6 % y mayo 15.5 %, contra 2.3 % en febrero.
TEMPORADAS_RIESGO = frozenset({4, 5, 10, 11})

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


# --------------------------------------------------------------------------- #
# SHAP
# --------------------------------------------------------------------------- #


# Valores SHAP de la regresion logistica sobre las variables estandarizadas.
#
# Para un modelo lineal el valor de Shapley es exacto y no necesita estimacion:
# contribucion_i = coeficiente_i * (x_i - media_i). Se pide a shap la misma
# cantidad para no depender de esa formula, y se devuelve la matriz (n, variables)
# con los valores en la escala de probabilidad, que es la que se muestra.
def valores_shap(modelo, x_entrenamiento: pd.DataFrame, x_explicar: pd.DataFrame) -> np.ndarray:
    import shap

    escalador = modelo.named_steps["standardscaler"]
    regresion = modelo.named_steps["logisticregression"]

    fondo = escalador.transform(x_entrenamiento)
    explicados = escalador.transform(x_explicar)

    explicador = shap.LinearExplainer(
        regresion, shap.maskers.Independent(fondo, max_samples=len(fondo))
    )
    valores = explicador.shap_values(explicados)
    return np.asarray(valores)


# Importancia global: promedio del valor absoluto, de mayor a menor.
def importancia_global(shap: np.ndarray, variables: list[str], top: int = 10) -> list[dict]:
    media = np.abs(shap).mean(axis=0)
    orden = np.argsort(media)[::-1][:top]
    return [
        {"etiqueta": ETIQUETAS.get(variables[i], variables[i]), "valor": round(float(media[i]), 4)}
        for i in orden
    ]


ETIQUETAS = {
    "mm_tasa_historica": "Tasa histórica del municipio",
    "lluvia_lag1": "Lluvia del mes anterior",
    "lluvia_lag1_ratio_clima": "Lluvia frente a su promedio",
    "lluvia_lag1_anomalia": "Anomalía de lluvia del mes anterior",
    "lluvia_suma_3m": "Lluvia acumulada de 3 meses",
    "lluvia_suma_6m": "Lluvia acumulada de 6 meses",
    "lluvia_acumulada_12m": "Lluvia acumulada de 12 meses",
    "clima_lag1": "Promedio histórico de lluvia",
    "lluvia_lag2": "Lluvia de hace 2 meses",
    "lluvia_lag3": "Lluvia de hace 3 meses",
    "lluvia_lag6": "Lluvia de hace 6 meses",
    "lluvia_suma_3m_anomalia": "Anomalía de lluvia de 3 meses",
    "mm_12m": "Meses con movimiento en masa (último año)",
    "mm_24m": "Meses con movimiento en masa (2 años)",
    "mm_3m": "Movimientos en masa del trimestre",
    "mm_6m": "Movimientos en masa del semestre",
    "eventos_12m": "Emergencias en los últimos 12 meses",
    "dias_desde_ultimo_mm": "Días desde el último movimiento en masa",
    "inundacion_12m": "Inundaciones en los últimos 12 meses",
    "incendio_forestal_12m": "Incendios forestales en los últimos 12 meses",
    "vendaval_12m": "Vendavales en los últimos 12 meses",
    "creciente_subita_12m": "Crecientes súbitas en los últimos 12 meses",
    "altitud_estatica": "Altitud del municipio",
    "latitud": "Latitud",
    "longitud": "Longitud",
    "mes_sin": "Época del año",
    "mes_cos": "Época del año",
}


# Las 27 variables se agrupan en las seis razones que el aplicativo sabe redactar.
# Cada razón es una plantilla de texto, asi que varias variables competes por un
# solo espacio: se suman las contribuciones SHAP del grupo y el municipio muestra
# las tres razones con mayor valor absoluto.
GRUPOS_RAZONES = {
    "tasa_historica": ["mm_tasa_historica"],
    "lluvia_rel_promedio": [
        "lluvia_lag1", "lluvia_lag2", "lluvia_lag3", "lluvia_lag6",
        "lluvia_suma_3m", "lluvia_suma_6m", "lluvia_acumulada_12m",
        "clima_lag1", "lluvia_lag1_anomalia", "lluvia_lag1_ratio_clima",
        "lluvia_suma_3m_anomalia",
    ],
    "emergencias_12m": [
        "eventos_12m", "inundacion_12m", "incendio_forestal_12m",
        "vendaval_12m", "creciente_subita_12m",
    ],
    "meses_mm_12m": ["mm_12m", "mm_24m", "mm_3m", "mm_6m", "dias_desde_ultimo_mm"],
    "mes_sin": ["mes_sin", "mes_cos"],
    "terreno": ["altitud_estatica", "latitud", "longitud"],
}

# Las 27 variables tienen que quedar metidas en un grupo. Si se agrega una
# variable a features.VARIABLES y no se mapea aqui, esta comprobacion lo dice al
# momento de exportar y no semanas despues en el texto de un boletin.
def _verificar_grupos() -> None:
    variables = set(ft.VARIABLES)
    mapeadas = {v for grupo in GRUPOS_RAZONES.values() for v in grupo}
    if variables != mapeadas:
        raise AssertionError(
            f"variables sin grupo o grupo con variable inexistente: "
            f"{sorted(variables ^ mapeadas)}"
        )


# Orden de las razones de un municipio: de mayor a menor contribucion SHAP
# agrupada. Las que no aportan nada en ese municipio se dejan al final para que
# el texto no diga "el municipio no registro emergencia" como si fuera una
# weakness en vez de una buena noticia.
def orden_razones(shap_fila: np.ndarray, variables: list[str]) -> list[str]:
    totales = {}
    for razon, grupo in GRUPOS_RAZONES.items():
        indices = [variables.index(v) for v in grupo]
        totales[razon] = float(abs(shap_fila[indices]).sum())
    return sorted(totales, key=lambda r: totales[r], reverse=True)


# --------------------------------------------------------------------------- #
# Umbral
# --------------------------------------------------------------------------- #


# Elige el umbral por capacidad, no por una cifra puesta de antemano.
#
# Se recorren los umbrales y se toma el que deja cerca de ALERTAS_POR_MES
# municipios en alerta por mes en el backtest. Asi la regla del semaforo
# responde a "cuanto puede atender el equipo", que es una pregunta operativa
# real, y no a "que recallPIB quiero mostrar".
def elegir_umbral(pred: pd.DataFrame, alertas: int = ALERTAS_POR_MES) -> tuple[float, dict]:
    from sklearn.metrics import precision_score, recall_score

    candidatos = np.round(np.arange(0.04, 0.61, 0.01), 2)
    y = pred[ft.OBJETIVO].to_numpy()
    s = pred["score_logistica"].to_numpy()

    mejor = None
    for umbral in candidatos:
        por_mes = pred.assign(alerta=s >= umbral).groupby("periodo")["alerta"].sum()
        diferencia = abs(por_mes.mean() - alertas)
        if mejor is None or diferencia < mejor[0]:
            mejor = (diferencia, float(umbral))

    umbral = mejor[1]
    predicho = (s >= umbral).astype(int)
    detalle = {
        "umbral": umbral,
        "alertas_por_mes": float(
            pred.assign(a=s >= umbral).groupby("periodo")["a"].sum().mean()
        ),
        "recall": float(recall_score(y, predicho)),
        "precision": float(precision_score(y, predicho, zero_division=0)),
    }
    return umbral, detalle


# Curva recall/precision segun umbral, sobre las predicciones fuera de muestra
# del backtest. Sean "validacion" o "prueba" es lo mismo aqui: ningun mes fue
# usado para entrenar al predecirlo.
def curva_umbral(pred: pd.DataFrame, nombre_columna: str, umbral: float) -> list[dict]:
    from sklearn.metrics import precision_score, recall_score

    y = pred[ft.OBJETIVO].to_numpy()
    s = pred[nombre_columna].to_numpy()
    valores = sorted({*np.round(np.arange(0.02, 0.81, 0.02), 2), round(umbral, 2)})

    curva = []
    for t in valores:
        predicho = (s >= t).astype(int)
        curva.append({
            "umbral": float(t),
            "recall": round(float(recall_score(y, predicho, zero_division=0)), 3),
            "precision": round(float(precision_score(y, predicho, zero_division=0)), 3),
        })
    return curva


# Metricas de la linea base en el mismo presupuesto de alertas.
#
# Comparar la linea base con su propio umbral OPTIMO seria tramposo. Se le da
# el mismo numero de alertas que al modelo y se mide que tanto recall compra cada
# uno con el mismo esfuerzo.
def metricas_linea_base(pred: pd.DataFrame, columna: str, alertas: int = ALERTAS_POR_MES) -> dict:
    from sklearn.metrics import precision_score, recall_score

    y = pred[ft.OBJETIVO].to_numpy()
    # La linea base se evalua con EXACTAMENTE `alertas` municipios por mes, y se
    # eligen por ranking y no con "puntaje >= percentil".
    #
    # La diferencia no es sutil: base_frecuencia_del_mes es una tasa sobre unos
    # pocos años, asi que decenas de municipios empatan en el mismo valor (0 de 6,
    # 1 de 6...). Con ">=" el percentil 88.5 arrastra a todos los empatados y la
    # linea base termina alertando 60 municipios, con un recall que parece mejor
    # solo porque esta viendo mas.
    bloques = []
    for _, grupo in pred.groupby("periodo"):
        puntajes = grupo[columna].to_numpy()
        elegidos = np.argsort(-puntajes, kind="stable")[:alertas]
        marcador = np.zeros(len(grupo), dtype=int)
        marcador[elegidos] = 1
        bloques.append(marcador)
    predicho = np.concatenate(bloques)

    return {
        "recall": float(recall_score(y, predicho, zero_division=0)),
        "precision": float(precision_score(y, predicho, zero_division=0)),
    }


# Formato de porcentaje para los textos que se muestran al usuario.
def pct(valor: float) -> str:
    return f"{valor * 100:.0f} %"


# Recall del modelo sobre el backtest al umbral que se acaba de elegir.
#
# Se calcula aqui y no se copia de la curva de umbral porque son cosas distintas:
# la curva viene del resumen de evaluacion y este es el mismo corte con el punto
# exacto que se publico. Si divergen, es que el umbral se movio.
def _recall_a_umbral(pred: pd.DataFrame, umbral: float) -> float:
    from sklearn.metrics import recall_score

    # La columna se llama score_logistica: es el prefijo que usa evaluacion.py
    # para los puntajes de modelo. "prob_logistica" no existe.
    y = pred[ft.OBJETIVO].to_numpy()
    predicho = (pred["score_logistica"].to_numpy() >= umbral).astype(int)
    return float(recall_score(y, predicho, zero_division=0))


# --------------------------------------------------------------------------- #
# Valores de boletin
# --------------------------------------------------------------------------- #


# Arma el diccionario que consume cuaderno/boletines.py con las cifras del
# municipio, todas conocidas al dia del corte.
#
# rainfall_ratio se redondea a un decimal a proposito: el boletin lo imprime con
# fmt(valor, 1), y verificar_cifras exige que el numero del texto exista tal cual
# en el diccionario. Con el valor entero a mas decimales, "1,2" no encontraria
# respaldo en 1.234 y la exportacion abortaria.
def valores_boletin(fila: pd.Series, orden: list[str], mes_objetivo: int) -> dict:
    return {
        "tasa_hist_pct": round(float(fila["mm_tasa_historica"]) * 100, 1),
        "lluvia_mm": float(fila["lluvia_lag1"]),
        "lluvia_ratio": round(float(fila["lluvia_lag1_ratio_clima"]), 1),
        "mes_anterior": MESES[mes_objetivo - 2],
        "mes": MESES[mes_objetivo - 1],
        "temporada": mes_objetivo in TEMPORADAS_RIESGO,
        "emergencias_12m": int(fila["eventos_12m"]),
        "meses_mm_12m": int(fila["mm_12m"]),
        "altitud_m": int(fila["altitud_estatica"]),
        "orden": orden,
    }


# --------------------------------------------------------------------------- #
# Exportacion
# --------------------------------------------------------------------------- #


# Une el modelo, el corte y los boletines en el diccionario que lee el aplicativo.
def construir_datos(marco: pd.DataFrame, pred_backtest: pd.DataFrame) -> dict:
    import sys

    sys.path.insert(0, str(C.RAIZ / "cuaderno"))
    from boletines import generar_boletin, nivel_de

    _verificar_grupos()

    corte = C.periodo_de(C.ANIO_OBJETIVO, C.MES_OBJETIVO)
    mes_objetivo = C.MES_OBJETIVO
    mes_texto = f"{MESES[mes_objetivo - 1]} de {C.ANIO_OBJETIVO}"
    corte_texto = f"1 de {MESES[mes_objetivo - 1]} de {C.ANIO_OBJETIVO}"

    # El corte solo se usa para partir el entrenamiento. Las variables del mes
    # objetivo se calculan con datos anteriores (auditar_fugas lo comprueba) y
    # la etiqueta de octubre no se mira en ningun momento.
    variables = ft.VARIABLES
    entrenamiento = marco[marco["periodo"] < corte]
    objetivo = marco[marco["periodo"] == corte].reset_index(drop=True)

    if len(objetivo) != marco["codigo_dane"].nunique():
        raise AssertionError(
            f"el corte {corte} deja {len(objetivo)} municipios, se esperaban "
            f"{marco['codigo_dane'].nunique()}"
        )

    modelo = _modelo()
    modelo.fit(entrenamiento[variables], entrenamiento[ft.OBJETIVO])
    prob = modelo.predict_proba(objetivo[variables])[:, 1]

    shap_filas = valores_shap(modelo, entrenamiento[variables], objetivo[variables])

    umbral, detalle_umbral = elegir_umbral(pred_backtest)
    resumen = ev.evaluar(pred_backtest).set_index("metodo")
    base_nombre = "base_frecuencia_del_mes"
    base = metricas_linea_base(pred_backtest, base_nombre)
    # El recall al umbral elegido sale de la curva, no de un numero escrito a
    # mano: el texto de limitaciones debe décrire el modelo que se publica.
    detalle_umbral = dict(detalle_umbral)
    detalle_umbral["recall"] = _recall_a_umbral(pred_backtest, float(umbral))

    municipios = []
    boletines = {}
    # El indice de objetivo se reinicio arriba, asi que fila.name da la posicion
    # exacta dentro de shap_filas sin buscar el codigo otra vez.
    ordenados = objetivo.assign(prob=prob).sort_values("prob", ascending=False)

    for puesto, (_, fila) in enumerate(ordenados.iterrows(), start=1):
        codigo = str(fila["codigo_dane"]).zfill(5)
        valores = valores_boletin(fila, orden_razones(shap_filas[fila.name], variables), mes_objetivo)
        boletin = generar_boletin(
            fila["municipio"], float(fila["prob"]), puesto, len(ordenados),
            umbral, valores, corte_texto, mes_texto, C.ANIO_OBJETIVO,
            FACTOR_AMARILLO,
        )
        municipios.append({
            "codigo": codigo,
            "municipio": fila["municipio"],
            "prob": round(float(fila["prob"]), 4),
            # El puesto tambien va en el diccionario: el aplicativo lo muestra en
            # la columna "#", en el detalle y en el indice del PDF. Si falta, el
            # HTML queda con "puesto undefined" sin avisar.
            "puesto": puesto,
            "razones": boletin.pop("razones"),
        })
        boletines[codigo] = boletin

    return {
        "origen": "modelo",
        "datos_simulados": False,
        "mes": mes_texto,
        "corte": f"{C.ANIO_OBJETIVO}-{C.MES_OBJETIVO:02d}-01",
        "corte_texto": corte_texto,
        "umbral": round(umbral, 2),
        "factor_amarillo": FACTOR_AMARILLO,
        "municipios": municipios,
        "importancia": importancia_global(shap_filas, variables),
        "metricas": {
            "periodo": _texto_periodo(pred_backtest),
            "modelo": {
                "nombre": "Regresión logística",
                "recall": round(detalle_umbral["recall"], 3),
                "precision": round(detalle_umbral["precision"], 3),
                "pr_auc": round(float(resumen.loc["score_logistica", "agregado_average_precision"]), 3),
                "roc_auc": round(float(resumen.loc["score_logistica", "agregado_roc_auc"]), 3),
                "brier": round(float(resumen.loc["score_logistica", "agregado_brier"]), 4),
            },
            "linea_base": {
                # El nombre tiene que decir lo que hace la linea base. Esta no
                # mira el mes anterior: promedia cuantos meses con MM teve ese
                # municipio en ese mismo mes del calendario, en anos previos.
                "nombre": "Histórico del mismo mes",
                "recall": round(base["recall"], 3),
                "precision": round(base["precision"], 3),
                "pr_auc": round(float(resumen.loc[base_nombre, "agregado_average_precision"]), 3),
            },
            "tasa_positivos": round(float(pred_backtest[ft.OBJETIVO].mean()), 4),
            "alertas_por_mes": round(detalle_umbral["alertas_por_mes"], 1),
            "recall_at_10": round(float(resumen.loc["score_logistica", f"mensual_recall_at_{ev.K_ALERTA}"]), 3),
            "piso_azar_recall_at_10": round(ev.recall_azar(), 3),
        },
        "curva_umbral": curva_umbral(pred_backtest, "score_logistica", umbral),
        "validacion": _esquema_validacion(pred_backtest),
        "boletines": boletines,
        "boletin_destacado": municipios[0]["codigo"],
        "limitaciones": _limitaciones(
            detalle_umbral["recall"], ALERTAS_POR_MES
        ),
    }


def _texto_periodo(pred: pd.DataFrame) -> str:
    anios = sorted({C.anio_de_periodo(p) for p in pred["periodo"].unique()})
    meses = pred["periodo"].nunique()
    return f"{anios[0]} a {anios[-1]}, {meses} meses fuera de muestra"


def _esquema_validacion(pred: pd.DataFrame) -> dict:
    anios = sorted({C.anio_de_periodo(p) for p in pred["periodo"].unique()})
    # Se cuentan periodos distintos, no filas: 1044 filas son los 87 municipios de
    # 12 meses, y el navegador necesita saber cuantos meses hay, no cuantos registros.
    por_anio = (
        pred.assign(anio=[C.anio_de_periodo(p) for p in pred["periodo"]])
        .groupby("anio")["periodo"]
        .nunique()
        .sort_index()
    )
    return {
        "anio_inicio": anios[0],
        "anio_fin": anios[-1],
        "meses": int(pred["periodo"].nunique()),
        # El navegador pinta una fila por año y necesita saber cuáles tuvieron meses
        # de prueba. Se le manda el conteo para que no tenga que deducirlo.
        "anios_con_prueba": [
            {"anio": int(anio), "meses": int(meses)} for anio, meses in por_anio.items()
        ],
        "descripcion": (
            "Ventana creciente: para cada mes se entrena con todos los meses "
            "anteriores y se predice ese mes. Ninguna predicción vio su propio "
            "resultado ni el de un mes futuro."
        ),
    }


# Las limitaciones que el aplicativo muestra. Son las del modelo que se publica,
# no un texto generico: la ultima linea es la que mas pesa, porque el problema
# es que un solo valor de lluvia por municipio no puede ver un aguacero de dos
# horas en una ladera.
def _limitaciones(recall_umbral: float, alertas_por_mes: float) -> list[str]:
    # Los numeros van con el modelo, no escritos a mano. Con el umbral de hoy el
    # recall es 26 %; si alguien lo recalcula, este texto queda viejo y miente.
    return [
        "Eventos detonados por lluvias intensas de pocas horas: el modelo solo "
        "ve el total mensual de lluvia, no la intensidad hora a hora.",
        "Dentro de un municipio hay laderas muy distintas y el modelo usa un solo "
        "valor de lluvia para todo el territorio.",
        "Subregistro: un municipio que reporta poco puede parecer más seguro de lo "
        "que es, porque el modelo aprende del registro, no de lo que pasó.",
        "Causas que no están en los datos: sismos, cortes de talud, deforestación, "
        "obras y construcción vial.",
        f"Al {pct(recall_umbral)} de los meses con movimiento en masa caen dentro "
        f"de los {alertas_por_mes:.0f} municipios alertados en un mes típico. El "
        "sistema sirve para priorizar la vigilancia, no para declarar que un "
        "municipio está seguro.",
    ]


# Escribe el .js que carga el aplicativo y el .json equivalente.
def escribir(datos: dict, ruta_js: Path = JS_SALIDA, ruta_json: Path = JSON_SALIDA) -> None:
    cabecera = (
        "/* =====================================================\n"
        "   SAT Santander · datos del modelo\n"
        "   Generado por src/publicar.py. No editar a mano.\n"
        f"   Corte: {datos['corte']} | umbral: {datos['umbral']} | "
        f"origen: {datos['origen']}\n"
        "   ===================================================== */\n"
    )

    ruta_js.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta_js, "w", encoding="utf-8") as fh:
        fh.write(cabecera)
        fh.write("window.SAT_DATOS = ")
        json.dump(datos, fh, ensure_ascii=False, indent=1)
        fh.write(";\n")

    with open(ruta_json, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=1)


# Los CSV de outputs/ se escriben en la misma corrida que el JSON.
#
# AntesVivian sueltos, de una corrida anterior con el modelo balanceado, y
# mostraban un Brier de 0,21 frente al 0,08 que dice el aplicativo. Dos cifras
# del mismo modelo en el mismo repo, y la que se lee sin abrir el JSON es la
# vieja. Ahora no pueden quedar desincronizadas.
def escribir_csvs(pred: pd.DataFrame) -> None:
    C.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pred.to_csv(C.OUTPUT_DIR / "predicciones_backtest.csv", index=False, encoding="utf-8")
    ev.evaluar(pred).to_csv(C.OUTPUT_DIR / "resumen_backtest.csv", index=False, encoding="utf-8")
    ev.resumen_anual(pred).to_csv(C.OUTPUT_DIR / "resumen_anual.csv", index=False, encoding="utf-8")


# Ruta completa: carga, arma variables, hace el backtest, entrena el final y
# exporta. Es lo que corre el aplicativo.
def main() -> dict:
    import sys

    sys.path.insert(0, str(C.RAIZ / "cuaderno"))
    from boletines import nivel_de

    datos = dc.cargar_todo()
    marco = ft.marco_de_modelo(ft.construir_variables(datos), datos.panel)
    pred = ev.predicciones(marco)
    salida = construir_datos(marco, pred)
    escribir(salida)
    escribir_csvs(pred)

    conteo = {"rojo": 0, "amarillo": 0, "verde": 0}
    for m in salida["municipios"]:
        conteo[nivel_de(m["prob"], salida["umbral"], salida["factor_amarillo"])] += 1

    print(f"corte {salida['corte']} | umbral {salida['umbral']} | "
          f"alertas/mes historicas {salida['metricas']['alertas_por_mes']}")
    print(f"municipios: {len(salida['municipios'])} | "
          f"rojo {conteo['rojo']} amarillo {conteo['amarillo']} verde {conteo['verde']}")
    print(f"boletines generados: {len(salida['boletines'])}")
    print(f"escrito: {JS_SALIDA.relative_to(C.RAIZ)} y {JSON_SALIDA.relative_to(C.RAIZ)}")
    return salida


if __name__ == "__main__":
    main()