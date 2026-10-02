from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .data_clean import Datos

# Centinela para "sin movimientos en masa registrados". Es una convencion, no un
# dato: los municipios con un solo antecedente en 11 anos quedan dominados por
# este valor y el modelo debe poder aprender a ignorarlo.
SIN_ANTECEDENTE_MM = 999.0

# Variables numericas que alimentan el modelo. Es una lista blanca:
# construir_variables() devuelve exactamente estas columnas, lo que impide que
# una columna del mes objetivo se cuele por descuido.
VARIABLES = [
    "lluvia_lag1",
    "lluvia_lag2",
    "lluvia_lag3",
    "lluvia_lag6",
    "lluvia_suma_3m",
    "lluvia_suma_6m",
    "lluvia_acumulada_12m",
    "clima_lag1",
    "lluvia_lag1_anomalia",
    "lluvia_lag1_ratio_clima",
    "lluvia_suma_3m_anomalia",
    "mm_3m",
    "mm_6m",
    "mm_12m",
    "mm_24m",
    "eventos_12m",
    "dias_desde_ultimo_mm",
    "mm_tasa_historica",
    "inundacion_12m",
    "incendio_forestal_12m",
    "vendaval_12m",
    "creciente_subita_12m",
    "altitud_estatica",
    "latitud",
    "longitud",
    "mes_sin",
    "mes_cos",
]

# Columnas que identifican la fila y la etiqueta. No entran al modelo.
CLAVES = ["codigo_dane", "municipio", "anio", "mes", "periodo"]
OBJETIVO = "hubo_mm_calc"

# Columnas que describen el mes OBJETIVO. Se devuelven junto al marco para poder
# medir cuanto mejora el modelo cuando se las regala (ver
# demostrar_variable_trampa), pero jamas deben usarse como variables de entrada.
COLUMNAS_DEL_MES_OBJETIVO = ["lluvia_mm", "eventos_mes_calc", "mm_mes_calc"]

# Rezagos y ventanas, en meses.
RESAGOS_LLUVIA = [1, 2, 3, 6]
VENTANAS_MM = [3, 6, 12, 24]
VENTANA_EVENTOS = 12


# --------------------------------------------------------------------------- #
# Piezas de calculo
# --------------------------------------------------------------------------- #


# Climatologia causal: promedio historico de lluvia de cada mes del ano.
# Se apila el panel a una fila por (municipio, ano), se acumula en el tiempo y
# se desplaza un ano. Asi el valor disponible en el ano Y usa hasta diciembre de
# Y-1 y nunca el propio ano en curso, que es justo lo que haria una fuga sutil.
def _climatologia_causal(panel: pd.DataFrame) -> pd.DataFrame:
    tabla = panel.pivot_table(
        index=["codigo_dane", "anio"],
        columns="mes",
        values="lluvia_mm",
        aggfunc="first",
    )
    # Todas las operaciones se aplican DENTRO de cada municipio. Sin groupby, el
    # cumsum arrastra valores de un municipio al siguiente y el shift(1) del
    # primer ano de cada uno lee el ultimo ano del municipio anterior: la
    # climatologia de 2015 saldia contaminada con datos del municipio vecino.
    por_municipio = tabla.groupby(level="codigo_dane")
    acumulado = por_municipio.cumsum()
    conteo = tabla.notna().groupby(level="codigo_dane").cumsum()
    previos = acumulado.groupby(level="codigo_dane").shift(1)
    conteo_previo = conteo.groupby(level="codigo_dane").shift(1)
    media = previos / conteo_previo

    largo = media.reset_index().melt(
        id_vars=["codigo_dane", "anio"], var_name="mes", value_name="clima"
    )
    largo["mes"] = largo["mes"].astype("int64")
    return largo


# Dias transcurridos desde el movimiento en masa mas reciente ANTERIOR al mes M.
# Devuelve el centinela cuando el municipio no tiene ningun antecedente.
# Cruzar eventos con cortes de mes es mas barato con busqueda binaria que con
# un merge por rangos.
def _dias_desde_ultimo_mm(panel: pd.DataFrame, emergencias: pd.DataFrame) -> pd.Series:
    inicio_mes = pd.to_datetime({"year": panel["anio"], "month": panel["mes"], "day": 1})
    partes = []

    for codigo, filas in panel.groupby("codigo_dane", sort=False):
        fechas = np.sort(
            emergencias.loc[
                (emergencias["codigo_dane"] == codigo) & emergencias["es_mm"], "fecha"
            ].to_numpy()
        )
        cortes = inicio_mes.loc[filas.index].to_numpy()

        if fechas.size == 0:
            # El municipio no tiene ningun MM en los datos disponibles, por
            # ejemplo cuando la trunca de la auditoria se los elimina.
            partes.append(pd.Series(SIN_ANTECEDENTE_MM, index=filas.index, dtype="float64"))
            continue

        # side="left" cuenta los eventos estrictamente anteriores al corte del mes.
        cuantos = np.searchsorted(fechas, cortes, side="left")
        indice_previo = np.clip(cuantos - 1, 0, None)
        previos = np.where(cuantos > 0, fechas[indice_previo], np.datetime64("NaT"))

        dias = (cortes - previos).astype("timedelta64[D]").astype("float64")
        dias[cuantos == 0] = SIN_ANTECEDENTE_MM
        partes.append(pd.Series(dias, index=filas.index))

    return pd.concat(partes).sort_index()


# Convierte un tipo de evento en nombre de variable sin tildes ni espacios:
# "Creciente subita" con tilde -> "creciente_subita".
# "Movimiento en masa" nunca llega aqui porque se excluye de la lista.
def _nombre_variable(evento: str) -> str:
    minuscula = evento.lower()
    for con, sin in [("ó", "o"), ("é", "e"), ("í", "i"), ("á", "a"), ("ú", "u")]:
        minuscula = minuscula.replace(con, sin)
    return minuscula.replace(" ", "_")


# Cuenta eventos por tipo en cada mes de cada municipio.
def _conteo_mensual_por_tipo(emergencias: pd.DataFrame) -> pd.DataFrame:
    tipos = [t for t in C.EVENTOS_VALIDOS if t != C.EVENTO_MM]
    tabla = (
        emergencias.assign(uno=1)
        .pivot_table(
            index=["codigo_dane", "anio", "mes"],
            columns="evento",
            values="uno",
            aggfunc="sum",
            fill_value=0,
        )
        .reindex(columns=tipos, fill_value=0)
    )
    return tabla.astype("int64").reset_index()


# --------------------------------------------------------------------------- #
# Construccion
# --------------------------------------------------------------------------- #


# Construye el marco de variables: una fila por municipio y mes con las claves,
# la etiqueta, las columnas del mes objetivo (solo de referencia) y las
# columnas de la lista blanca VARIABLES.
def construir_variables(datos: Datos) -> pd.DataFrame:
    panel = datos.panel.sort_values(["codigo_dane", "anio", "mes"]).reset_index(drop=True)

    panel = panel.merge(_climatologia_causal(panel), on=["codigo_dane", "anio", "mes"], how="left")
    panel = panel.merge(_conteo_mensual_por_tipo(datos.emergencias), on=["codigo_dane", "anio", "mes"], how="left")
    panel = panel.sort_values(["codigo_dane", "anio", "mes"]).reset_index(drop=True)

    tipos = [t for t in C.EVENTOS_VALIDOS if t != C.EVENTO_MM]
    panel[tipos] = panel[tipos].fillna(0).astype("int64")

    grp = panel.groupby("codigo_dane", sort=False)

    # Lluvia: rezagos individuales y ventanas acumuladas. Todas miran de M-1
    # hacia atras. La lluvia del propio mes M no se toca en ningun momento.
    for r in RESAGOS_LLUVIA:
        panel[f"lluvia_lag{r}"] = grp["lluvia_mm"].shift(r)

    panel["lluvia_suma_3m"] = grp["lluvia_mm"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=3).sum()
    )
    panel["lluvia_suma_6m"] = grp["lluvia_mm"].transform(
        lambda s: s.shift(1).rolling(6, min_periods=6).sum()
    )

    # Anomalias contra la climatologia causal del municipio.
    panel["clima_lag1"] = grp["clima"].shift(1)
    panel["clima_suma_3m"] = grp["clima"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=3).sum()
    )
    panel["lluvia_lag1_anomalia"] = panel["lluvia_lag1"] - panel["clima_lag1"]
    panel["lluvia_lag1_ratio_clima"] = panel["lluvia_lag1"] / panel["clima_lag1"]
    panel["lluvia_suma_3m_anomalia"] = panel["lluvia_suma_3m"] - panel["clima_suma_3m"]

    # Historial de movimientos en masa, siempre excluyendo el mes actual.
    for ventana in VENTANAS_MM:
        panel[f"mm_{ventana}m"] = grp["mm_mes_calc"].transform(
            lambda s, v=ventana: s.shift(1).rolling(v, min_periods=v).sum()
        )
    panel["eventos_12m"] = panel["eventos_12m_calc"]

    panel["dias_desde_ultimo_mm"] = _dias_desde_ultimo_mm(panel, datos.emergencias)
    # Tasa historica de MM por mes: acumulado hasta M-1 dividido por los meses ya
    # transcurridos. Es la memoria larga del municipio, a diferencia de las
    # ventanas fijas.
    serie_mm = grp["mm_mes_calc"]
    acumulado_mm = serie_mm.cumsum() - panel["mm_mes_calc"]
    meses_transcurridos = grp.cumcount().clip(lower=1)
    panel["mm_tasa_historica"] = acumulado_mm / meses_transcurridos

    # Historial por tipo de evento en los 12 meses anteriores, que es el
    # historial por tipo que pide el enunciado.
    for tipo in tipos:
        panel[f"{_nombre_variable(tipo)}_12m"] = grp[tipo].transform(
            lambda s: s.shift(1).rolling(VENTANA_EVENTOS, min_periods=VENTANA_EVENTOS).sum()
        )

    # Atributos estaticos del municipio: no dependen del mes, asi que no pueden
    # filtrar informacion del futuro.
    catalogo = datos.municipios.set_index("codigo_dane")
    panel["latitud"] = panel["codigo_dane"].map(catalogo["latitud"])
    panel["longitud"] = panel["codigo_dane"].map(catalogo["longitud"])

    panel["mes_sin"] = np.sin(2 * np.pi * panel["mes"] / 12)
    panel["mes_cos"] = np.cos(2 * np.pi * panel["mes"] / 12)

    columnas = CLAVES + [OBJETIVO] + COLUMNAS_DEL_MES_OBJETIVO + VARIABLES
    return panel[columnas].copy()


# Filtra el marco a las filas utilizables: historia completa de 12 meses, sin el
# artefacto de lluvia de 2015-01 y sin nulos en ninguna variable.
#
# El marco arranca en enero de 2017, no en 2016. La restriccion la impone mm_24m:
# una ventana de 24 meses necesita dos anos de historico previo, y el panel solo
# empieza en 2015, asi que la primera fila con memoria completa es 2017-01. Se
# acepta perder 2016 porque mm_24m es una de las variables masometricsas del
# conjunto y porque 9.396 filas con 868 positivas siguen siendo suficientes para
# un modelo tabular. Es una decision que se declara, no un silencio.
def marco_de_modelo(variables: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    clave = ["codigo_dane", "anio", "mes"]
    marcas = panel[clave + ["historial_12m_completo", "artefacto_lluvia_imputada"]]
    marco = variables.merge(marcas, on=clave, how="left")
    usable = marco["historial_12m_completo"] & ~marco["artefacto_lluvia_imputada"]
    marco = marco.loc[usable & marco[VARIABLES].notna().all(axis=1)]
    return marco.reset_index(drop=True)


# Comprueba que la lista blanca este sana: sin repetidos y sin colision con las
# columnas del mes objetivo ni con la etiqueta. Se llama antes de entrenar para
# que una lista blanca mal escrita no pase desapercibida.
def verificar_lista_blanca() -> None:
    if len(set(VARIABLES)) != len(VARIABLES):
        raise ValueError("VARIABLES tiene columnas repetidas")
    prohibidas = set(COLUMNAS_DEL_MES_OBJETIVO) | {OBJETIVO}
    interseccion = set(VARIABLES) & prohibidas
    if interseccion:
        raise ValueError(f"VARIABLES incluye columnas del mes objetivo: {interseccion}")
    if "lluvia_mm" in VARIABLES or "mm_mes_calc" in VARIABLES:
        raise ValueError("una variable cruda del mes objetivo llego a la lista blanca")


# --------------------------------------------------------------------------- #
# Auditoria de fugas
# --------------------------------------------------------------------------- #


# Demuestra que ninguna variable mira hacia adelante.
#
# El procedimiento trunca el panel y el registro de emergencias en el periodo de
# corte, que es exactamente lo que el sistema puede ver el 1 de octubre de 2025,
# y vuelve a construir el marco. Si una variable de un mes anterior al corte
# cambiara, es porque estaba leyendo el futuro.
def auditar_fugas(datos: Datos, periodo_corte: int) -> dict:
    verificar_lista_blanca()
    completo = construir_variables(datos)

    periodo_emergencia = datos.emergencias["anio"] * 12 + datos.emergencias["mes"]
    truncado = Datos(
        panel=datos.panel[datos.panel["periodo"] < periodo_corte].copy(),
        emergencias=datos.emergencias[periodo_emergencia < periodo_corte].copy(),
        municipios=datos.municipios,
        geometrias=datos.geometrias,
    )
    recortado = construir_variables(truncado)

    antes_corte = completo["periodo"] < periodo_corte
    a = completo.loc[antes_corte, VARIABLES].reset_index(drop=True)
    b = recortado.loc[recortado["periodo"] < periodo_corte, VARIABLES].reset_index(drop=True)

    if len(a) != len(b):
        raise AssertionError(
            f"la trunca cambio el numero de filas anteriores al corte: {len(a)} vs {len(b)}"
        )

    # Se compara con centinela para que NaN contra NaN cuente como igual.
    centinela = -999.0
    sospechosas = []
    for col in VARIABLES:
        va = a[col].fillna(centinela).to_numpy()
        vb = b[col].fillna(centinela).to_numpy()
        if not np.array_equal(va, vb):
            sospechosas.append(
                {"variable": col, "filas_distintas": int((va != vb).sum())}
            )

    return {
        "periodo_corte": int(periodo_corte),
        "filas_verificadas": int(len(a)),
        "variables_verificadas": len(VARIABLES),
        "sin_fugas": not sospechosas,
        "variables_sospechosas": sospechosas,
    }


# Demuestra por que el esquema de validacion es necesario: entrena el mismo
# modelo regalandole el dato del mes que se quiere predecir y muestra hasta donde
# se infla el desempeño.
#
# Sin este contraste, un AUC de 0.99 parece un buen modelo cuando en realidad
# solo esta leyendo la respuesta dentro de la variable de entrada.
def demostrar_variable_trampa(marco: pd.DataFrame) -> dict:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    orden = marco.sort_values("periodo").reset_index(drop=True)
    limite = int(orden["periodo"].quantile(0.8))
    entrenamiento = orden[orden["periodo"] <= limite]
    prueba = orden[orden["periodo"] > limite]
    y_prueba = prueba[OBJETIVO]

    escenarios = {
        "historico_legitimo": VARIABLES,
        "regalando_lluvia_del_mes": VARIABLES + ["lluvia_mm"],
        "regalando_eventos_del_mes": VARIABLES + ["eventos_mes_calc"],
        "regalando_mm_del_mes": VARIABLES + ["mm_mes_calc"],
    }

    resultados = {}
    for nombre, columnas in escenarios.items():
        # El escalador va dentro del pipeline para que se ajuste solo con
        # entrenamiento. Las variables mezclan mm, dias y razones, asi que sin
        # escalar el modelo lineal ni converge ni compara bien las magnitudes.
        modelo = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=5000, class_weight="balanced"),
        )
        modelo.fit(entrenamiento[columnas], entrenamiento[OBJETIVO])
        predicho = modelo.predict_proba(prueba[columnas])[:, 1]
        resultados[nombre] = {
            "roc_auc": round(float(roc_auc_score(y_prueba, predicho)), 4),
            "average_precision": round(float(average_precision_score(y_prueba, predicho)), 4),
        }

    referencia = HistGradientBoostingClassifier(random_state=C.SEMILLA)
    referencia.fit(entrenamiento[VARIABLES], entrenamiento[OBJETIVO])
    predicho = referencia.predict_proba(prueba[VARIABLES])[:, 1]
    resultados["gradiente_historico_legitimo"] = {
        "roc_auc": round(float(roc_auc_score(y_prueba, predicho)), 4),
        "average_precision": round(float(average_precision_score(y_prueba, predicho)), 4),
    }

    resultados["_tasa_base_prueba"] = round(float(y_prueba.mean()), 4)
    resultados["_nota"] = (
        "Tasa base de positivos en prueba. Un ROC-AUC alto en los escenarios que "
        "regalan datos del mes objetivo no es logro del modelo: es fuga, y un "
        "modelo entrenado asi no sirve para avisar el 1 del mes."
    )
    return resultados