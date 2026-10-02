from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from . import features as ft

# Primer mes que se predice. Antes se exige al menos 2017-2019 en_entrenamiento:
# son 36 meses y unos 290 positivos, el minimo para que un modelo tabular
# tenga algo que aprender. Empezar antes daria folds con tan pocos positivos
# que las metricas por mes serian ruido.
PRIMER_PERIODO_PRUEBA = 2020 * 12 + 1

# Con 87 municipios, alertar los K de mayor puntaje es la decision operativa.
# K=10 es un presupuesto de horas: un equipo que visita unos 10 municipios al mes.
K_ALERTA = 10
K_ALERTA_ALTO = 20


# --------------------------------------------------------------------------- #
# Baselines
# --------------------------------------------------------------------------- #


# Tasa de MM en el MISMO mes del ano, promediada sobre anos anteriores.
#
# No es un modelo: es la frase "en marzo aqui casi siempre hay movimiento". Se
# construye igual que la climatologia de lluvia, con acumulacion y un desplazamiento
# de un ano, para que use hasta diciembre del ano anterior y nunca el ano en curso.
def tasa_mensual_causal(marco: pd.DataFrame) -> pd.Series:
    grupo = marco.groupby(["codigo_dane", "mes"])
    acumulado = grupo["mm_mes_calc"].cumsum() - marco["mm_mes_calc"]
    previos = grupo.cumcount()
    tasa = acumulado / previos.replace(0, np.nan)
    return tasa.fillna(0.0)


# Anade al marco las columnas de puntaje de cada baseline.
#
# Todos los puntajes mas altos significan mas riesgo, para que se puedan ordenar
# y comparar con la salida del modelo sin transformar nada. Los tres se calculan
# solo con variables que ya eran conocidas al inicio del mes.
def agregar_baselines(marco: pd.DataFrame) -> pd.DataFrame:
    salida = marco.copy()
    salida["base_frecuencia_historica"] = salida["mm_tasa_historica"]
    salida["base_frecuencia_del_mes"] = tasa_mensual_causal(salida)
    salida["base_lluvia_3m"] = salida["lluvia_suma_3m"]
    # Piso de referencia: un puntaje constante no ordena nada, asi que su ROC-AUC
    # da 0.5 y su average precision da exactamente la tasa de positivos. Sirve
    # para leer los numeros del modelo sin estar chasing metricas.
    salida["base_azar"] = 1.0
    return salida


BASELINES = [
    "base_frecuencia_historica",
    "base_frecuencia_del_mes",
    "base_lluvia_3m",
    "base_azar",
]


# --------------------------------------------------------------------------- #
# Modelos
# --------------------------------------------------------------------------- #


# Dos familias a proposito. La regresion logistica obliga a que las variables
# sumen de forma monotona y es legible para un boletin; el gradient boosting
# captura interacciones (por ejemplo "lluvia alta Y municipio con historial") y
# es el que gana si hay senal. Si los dos empatan, la conclusion honesta es que
# la relacion es esencialmente lineal y basta el modelo simple.
#
# class_weight va en None a proposito. Con "balanced" el orden no mejora
# (ROC-AUC 0.712 contra 0.707, AP 0.189 contra 0.188) pero las probabilidades
# se inflan: la mediana sale 0.42 cuando la tasa real de positivos es 9.5 %, y el
# Brier se va de 0.083 a 0.213. El aplicativo le dice al municipio "probabilidad
# del X %", asi que lo que se publica tiene que estar calibrado. Este mismo
# ajuste se usa en src/publicar.py: si aqui cambia, cambia alla.
def _modelos() -> dict:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return {
        "logistica": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=5000, C=1.0),
        ),
        "gradient_boosting": HistGradientBoostingClassifier(
            max_iter=150,
            early_stopping=False,
            learning_rate=0.06,
            max_leaf_nodes=15,
            min_samples_leaf=40,
            l2_regularization=1.0,
            random_state=C.SEMILLA,
        ),
    }


# --------------------------------------------------------------------------- #
# Metricas
# --------------------------------------------------------------------------- #


# Precision y recall en los K municipios de mayor puntaje.
#
# K es un presupuesto real: al final del mes solo se alcanzan K municipios, y lo
# que se pregunta es cuantos de los que de verdad hubo se atraparon. Un ROC-AUC
# alto sin recall@K alto no sirve para operar.
def _top_k(y: np.ndarray, s: np.ndarray, k: int) -> tuple[float, float]:
    orden = np.argsort(-s, kind="stable")[:k]
    atrapados = int(y[orden].sum())
    total = int(y.sum())
    recall = atrapados / total if total else np.nan
    precision = atrapados / min(k, len(y))
    return recall, precision


# Recall@K que se obtendria si se alertaran K municipios al azar.
#
# Sin este numero un recall de 0.20 se lee como "el modelo acierta el 20% de los
# casos" y no como "el modelo casi duplica lo que ya entregaria el azar". Con
# cerca de 7 positivos mensuales en 87 municipios, elegir 10 al azar ya atrapa
# cerca del 11%. El margen real del modelo es el recall menos ese piso.
def recall_azar(k: int = K_ALERTA) -> float:
    return k / 87.0


# Metricas de ORDEN: valen sobre cualquier conjunto de filas, agregado o mensual,
# porque solo miran el orden del puntaje y no cuanto puntaje hay.
#
# es_probabilidad controla el Brier. ROC-AUC y average precision aceptan milimetros
# o una tasa historica igual que una probabilidad, porque solo dependen del
# ranking. El Brier mide calibration, asi que solo tiene sentido si el puntaje
# esta en [0,1]: pasarlo a la lluvia acumulada daria un numero sin lectura.
def metricas_de_orden(y: np.ndarray, s: np.ndarray, es_probabilidad: bool = True) -> dict:
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

    y = np.asarray(y).astype(int)
    s = np.asarray(s, dtype=float)

    if len(np.unique(y)) < 2:
        # Sin positivos o sin negativos no hay un orden que evaluar. Se deja NaN
        # y no cero, porque cero significaria "el modelo nunca acierta".
        roc = np.nan
        ap = float(y.mean()) if len(y) else np.nan
    else:
        roc = float(roc_auc_score(y, s))
        ap = float(average_precision_score(y, s))

    if es_probabilidad and len(y) and s.min() >= 0.0 and s.max() <= 1.0:
        brier = float(brier_score_loss(y, s))
    else:
        brier = np.nan

    return {
        "n": int(len(y)),
        "positivos": int(y.sum()),
        "tasa_base": float(y.mean()) if len(y) else np.nan,
        "roc_auc": roc,
        "average_precision": ap,
        "lift_ap": float(ap / y.mean()) if y.mean() else np.nan,
        "brier": brier,
    }


# Metricas OPERATIVAS: solo tienen sentido sobre un mes completo.
#
# "Top 10" significa los 10 municipios de mayor puntaje entre los 87 del mes. Si
# se aplicaran a los 6.177 municipios de todo el periodo, el top 10 solo podria
# atrapar 10 de 590 positivos y el recall daria 1.7% por construccion, sin decir
# nada del modelo. Por eso el agregado usa el promedio de los valores mensuales
# y nunca un top 10 sobre todo el periodo.
def metricas_operativas(y: np.ndarray, s: np.ndarray, k: int = K_ALERTA) -> dict:
    y = np.asarray(y).astype(int)
    recall_k, precision_k = _top_k(y, np.asarray(s, dtype=float), k)
    recall_grande, precision_grande = _top_k(y, np.asarray(s, dtype=float), K_ALERTA_ALTO)
    return {
        f"recall_at_{k}": recall_k,
        f"precision_at_{k}": precision_k,
        f"recall_at_{K_ALERTA_ALTO}": recall_grande,
        f"precision_at_{K_ALERTA_ALTO}": precision_grande,
    }


# Solo los modelos producen probabilidades. La lluvia acumulada en mm y la tasa
# historica son puntajes de orden: sirven para comparar rankings, no calibration.
def _es_probabilidad(nombre: str) -> bool:
    return nombre.startswith("score_") or nombre == "base_azar"


# Las dos familias juntas, que es lo que se calcula mes a mes.
def metricas(y: np.ndarray, s: np.ndarray, k: int = K_ALERTA, es_probabilidad: bool = True) -> dict:
    return {
        **metricas_de_orden(y, s, es_probabilidad),
        **metricas_operativas(y, s, k),
    }


# --------------------------------------------------------------------------- #
# Backtest
# --------------------------------------------------------------------------- #


# Backtest expanding-window: para cada mes de prueba se entrena con TODO lo
# anterior y se predice el mes completo, los 87 municipios a la vez.
#
# Es el orden real del problema. El dia 1 de octubre el equipo conoce la lluvia
# de septiembre y los movimientos de septiembre, y nada mas. Por eso el corte es
# por periodo y no una fila al azar: un split aleatorio deja meses futuros en el
# entrenamiento y produce metricas que no se pueden reproducir.
def predicciones(marco: pd.DataFrame, primer_periodo: int = PRIMER_PERIODO_PRUEBA) -> pd.DataFrame:
    marco = agregar_baselines(marco).sort_values("periodo").reset_index(drop=True)
    periodos = np.sort(marco["periodo"].unique())
    prueba = periodos[periodos >= primer_periodo]

    modelos = _modelos()
    columnas = ft.VARIABLES
    partes: list[pd.DataFrame] = []

    for corte in prueba:
        entrenamiento = marco[marco["periodo"] < corte]
        evaluacion = marco[marco["periodo"] == corte]

        if entrenamiento[ft.OBJETIVO].sum() == 0 or evaluacion[ft.OBJETIVO].sum() == 0:
            # Un mes de prueba sin positivos no aporta a las metricas y uno de
            # entrenamiento vacio no se puede ajustar. Se omiten y queda constancia.
            continue

        bloque = evaluacion[
            ft.CLAVES + [ft.OBJETIVO] + BASELINES
        ].copy()

        for nombre, modelo in modelos.items():
            ajustado = modelo.fit(entrenamiento[columnas], entrenamiento[ft.OBJETIVO])
            bloque[f"score_{nombre}"] = ajustado.predict_proba(evaluacion[columnas])[:, 1]

        partes.append(bloque)

    if not partes:
        raise ValueError("no hay meses de prueba utilizables")

    return pd.concat(partes, ignore_index=True)


# Evalua cada modelo y cada baseline sobre las mismas predicciones, de dos formas.
#
# Agregado: se concatenan todos los meses y se mide una sola vez. Es la cifra
# que manda, porque promediar AUC de 72 meses con 8 positivos cada uno da un
# numero que no corresponde a ninguna situacion real.
#
# Por mes: se mide mes a mes para ver consistencia, no solo el promedio. Un
# modelo que gana en 40 meses y pierde en 32 no es dependable.
# Metricas mes a mes. Se arma con una lista explicita en vez de groupby.apply
# porque apply() devuelve la forma de acuerdo con la version de pandas y aqui
# hace falta una tabla estable con una columna por metrica.
def metricas_por_mes(pred: pd.DataFrame, columna: str, k: int = K_ALERTA) -> pd.DataFrame:
    filas = []
    for periodo, grupo in pred.groupby("periodo"):
        filas.append(
            {
                "periodo": int(periodo),
                **metricas(grupo[ft.OBJETIVO].to_numpy(), grupo[columna].to_numpy(), k, _es_probabilidad(columna)),
            }
        )
    return pd.DataFrame(filas)


def evaluar(pred: pd.DataFrame, k: int = K_ALERTA) -> pd.DataFrame:
    nombres = [c for c in pred.columns if c.startswith("score_")] + BASELINES
    y = pred[ft.OBJETIVO].to_numpy()

    filas = []
    for nombre in nombres:
        es_prob = _es_probabilidad(nombre)
        # El orden se mide sobre todo el periodo junto: concatenar los meses da
        # 6.177 filas y una cifra estable, que es la que se reporta.
        orden = metricas_de_orden(y, pred[nombre].to_numpy(), es_prob)

        # Lo operativo se promedia mes a mes. Un top 10 sobre todo el periodo no
        # significa nada, asi que aqui nunca se calcula de esa forma.
        por_mes = metricas_por_mes(pred, nombre, k)
        operativas = por_mes[
            [c for c in por_mes.columns if c.startswith(("recall_at", "precision_at"))]
        ].mean()

        filas.append(
            {
                "metodo": nombre,
                **{f"agregado_{clave}": valor for clave, valor in orden.items()},
                **{f"mensual_{clave}": valor for clave, valor in operativas.items()},
                "meses_evaluados": int(len(por_mes)),
                "meses_con_recall_1": int((por_mes[f"recall_at_{k}"] == 1).sum()),
                "recall_k_mediana_mes": float(por_mes[f"recall_at_{k}"].median(skipna=True)),
                "recall_k_peor_mes": float(por_mes[f"recall_at_{k}"].min(skipna=True)),
                "ap_mediana_mes": float(por_mes["average_precision"].median(skipna=True)),
            }
        )

    return (
        pd.DataFrame(filas)
        .sort_values("agregado_average_precision", ascending=False)
        .reset_index(drop=True)
    )


# Resumen por ano. Todo se promedia sobre meses, nunca se aplica top K a un ano
# entero: alertar 10 municipios de los 1044 de un ano no es una decision posible
# en el terreno. Un ano con meses sin positivos aporta un recall NaN y se cuenta
# aparte, para que un 0.0 no se confunda con "el modelo no aro nada".
def resumen_anual(pred: pd.DataFrame, k: int = K_ALERTA) -> pd.DataFrame:
    nombres = [c for c in pred.columns if c.startswith("score_")] + BASELINES
    filas = []

    for nombre in nombres:
        por_mes = metricas_por_mes(pred, nombre, k)
        por_mes["anio"] = [C.anio_de_periodo(p) for p in por_mes["periodo"]]
        for anio, grupo in por_mes.groupby("anio"):
            filas.append(
                {
                    "metodo": nombre,
                    "anio": int(anio),
                    "meses": int(len(grupo)),
                    "meses_con_positivo": int((grupo["positivos"] > 0).sum()),
                    "positivos": int(grupo["positivos"].sum()),
                    "tasa_base": float(grupo["tasa_base"].mean()),
                    "roc_auc": float(grupo["roc_auc"].mean(skipna=True)),
                    "average_precision": float(grupo["average_precision"].mean(skipna=True)),
                    "lift_ap": float(grupo["lift_ap"].mean(skipna=True)),
                    f"recall_at_{k}": float(grupo[f"recall_at_{k}"].mean(skipna=True)),
                }
            )

    return pd.DataFrame(filas)


# Comparacion pareada mes a mes contra un metodo de referencia.
#
# Un promedio puede esconder que el modelo gane poco pero perder mucho. Cuenta
# en cuantos meses cada metodo supera al modelo elegido, usando el presupuesto
# operativo: cuantos de los K municipios alertados eran positivos.
def comparar_meses(pred: pd.DataFrame, referencia: str, k: int = K_ALERTA) -> pd.DataFrame:
    nombres = [c for c in pred.columns if c.startswith("score_")]
    referencia_mes = pred.groupby("periodo")[referencia]

    filas = []
    for nombre in nombres:
        propias = pred.groupby("periodo")[nombre]
        dif = []
        for (_, s_modelo), (_, s_ref) in zip(propias, referencia_mes):
            y = pred.loc[s_modelo.index, ft.OBJETIVO].to_numpy()
            if y.sum() == 0:
                continue
            r_modelo, _ = _top_k(y, s_modelo.to_numpy(), k)
            r_ref, _ = _top_k(y, s_ref.to_numpy(), k)
            dif.append(r_modelo - r_ref)

        d = np.asarray(dif, dtype=float)
        filas.append(
            {
                "metodo": nombre,
                "meses_comparables": int(len(d)),
                "meses_ganados": int((d > 0).sum()),
                "meses_empatados": int((d == 0).sum()),
                "meses_perdidos": int((d < 0).sum()),
                "diferencia_recall_k_media": round(float(d.mean()), 4) if len(d) else np.nan,
            }
        )

    return pd.DataFrame(filas)