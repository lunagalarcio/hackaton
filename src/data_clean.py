from __future__ import annotations

import json
import math
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config as C


# Excepcion que se lanza cuando una validacion de estructura o integridad falla.
class ContratoError(ValueError):
    pass


# Las diez columnas que vienen en el panel original. Se usan para comprobar que
# la limpieza no introducio nulos donde el archivo de origen no los tenia.
COLUMNAS_ORIGEN = [
    "codigo_dane",
    "municipio",
    "anio",
    "mes",
    "lluvia_mm",
    "lluvia_mm_mes_anterior",
    "eventos_mes",
    "eventos_12m",
    "altitud_m",
    "hubo_mm",
]


# Paquete de datos ya limpios. `informe` es la bitacora: una fila por decision
# de limpieza tomada, con cuantas filas afecto y por que.
@dataclass
class Datos:
    panel: pd.DataFrame
    emergencias: pd.DataFrame
    municipios: pd.DataFrame
    geometrias: dict
    informe: pd.DataFrame = field(default_factory=pd.DataFrame)

    # Catalogo de los 87 municipios con coordenadas y altitud, ordenado por
    # codigo_dane. Es la tabla que se cruzara con las predicciones para el mapa.
    @property
    def municipios_en_panel(self) -> pd.DataFrame:
        cols = [
            "codigo_dane",
            "municipio",
            "latitud",
            "longitud",
            "altitud_m",
        ]
        return self.municipios[cols].sort_values("codigo_dane").reset_index(drop=True)


# Normalizacion

# Normaliza texto a NFC y recorta espacios. Sin esto, "Peñon" puede venir como
# dos caracteres (NFD) en un archivo y como uno en otro, y la comparacion de
# nombres de municipio falla sin avisar.
def normalizar_texto(serie: pd.Series) -> pd.Series:
    return (
        serie.astype("string")
        .map(lambda v: unicodedata.normalize("NFC", v.strip()) if pd.notna(v) else pd.NA)
        .astype("string")
    )


# Lleva codigo_dane a int64 y valida que sea un DANE de 5 digitos con prefijo 68.
# Existe porque el GeoJSON trae el codigo como texto y los otros tres archivos
# como entero: mezclar ambos tipos produce un merge vacio sin error visible.
def normalizar_codigo(serie: pd.Series, origen: str) -> pd.Series:
    limpio = serie.astype("string").str.strip()
    if limpio.isna().any():
        raise ContratoError(f"{origen}: hay codigo_dane nulo")
    if not limpio.str.fullmatch(r"\d+").all():
        offending = limpio[~limpio.str.fullmatch(r"\d+")].unique().tolist()
        raise ContratoError(f"{origen}: codigo_dane no numerico: {offending[:5]}")
    if not limpio.str.fullmatch(rf"\d{{{C.CODIGO_DANE_LONGITUD}}}").all():
        raise ContratoError(f"{origen}: codigo_dane no tiene {C.CODIGO_DANE_LONGITUD} digitos")
    codigo = limpio.astype("int64")
    if not codigo.astype("string").str.startswith(C.PREFIJO_DANE).all():
        raise ContratoError(f"{origen}: codigo_dane fuera del prefijo {C.PREFIJO_DANE}")
    return codigo


# Normaliza el tipo de evento a NFC sin alterar mayusculas ni espacios internos,
# para que "Inundación" y "Inundacion" no queden como dos categorias distintas.
def normalizar_evento(serie: pd.Series) -> pd.Series:
    return serie.astype("string").map(
        lambda v: unicodedata.normalize("NFC", v.strip()) if pd.notna(v) else pd.NA
    ).astype("string")


# Anota una fila en la bitacora de limpieza.
def _log(informe: list[dict], artefacto: str, filas: int, detalle: str) -> None:
    informe.append({"artefacto": artefacto, "filas_afectadas": filas, "decision": detalle})


# Carga


# Carga el panel municipio-mes y valida su estructura interna: clave unica,
# mes y anio dentro de rango, objetivo binario, lluvia no negativa.
# Queda ordenado por municipio y tiempo, que es el orden que exigen los rezagos.
def cargar_panel(ruta: Path = C.PANEL_CSV) -> pd.DataFrame:
    panel = pd.read_csv(ruta, encoding=C.ENCODING)
    panel["codigo_dane"] = normalizar_codigo(panel["codigo_dane"], "panel")
    panel["municipio"] = normalizar_texto(panel["municipio"])

    panel["anio"] = panel["anio"].astype("int64")
    panel["mes"] = panel["mes"].astype("int64")
    for col in ["lluvia_mm", "lluvia_mm_mes_anterior"]:
        panel[col] = pd.to_numeric(panel[col], errors="raise").astype("float64")
    for col in ["eventos_mes", "eventos_12m", "altitud_m", "hubo_mm"]:
        panel[col] = pd.to_numeric(panel[col], errors="raise").astype("int64")

    if not panel["mes"].between(1, 12).all():
        raise ContratoError("panel: mes fuera de 1..12")
    if not panel["anio"].between(C.ANIO_INI, C.ANIO_FIN).all():
        raise ContratoError(f"panel: anio fuera de {C.ANIO_INI}..{C.ANIO_FIN}")
    if not panel["hubo_mm"].isin([0, 1]).all():
        raise ContratoError("panel: hubo_mm debe ser binaria")
    if (panel["lluvia_mm"] < 0).any() or (panel["lluvia_mm_mes_anterior"] < 0).any():
        raise ContratoError("panel: lluvia negativa")
    if panel.duplicated(["codigo_dane", "anio", "mes"]).any():
        raise ContratoError("panel: clave (codigo_dane, anio, mes) duplicada")

    return panel.sort_values(["codigo_dane", "anio", "mes"]).reset_index(drop=True)


# Carga el registro de emergencias, que es la fuente primaria del proyecto.
# Anade anio, mes y la bandera es_mm, que despues define la variable objetivo.
def cargar_emergencias(ruta: Path = C.EMERGENCIAS_CSV) -> pd.DataFrame:
    emer = pd.read_csv(ruta, encoding=C.ENCODING)
    emer["codigo_dane"] = normalizar_codigo(emer["codigo_dane"], "emergencias")
    emer["municipio"] = normalizar_texto(emer["municipio"])
    emer["evento"] = normalizar_evento(emer["evento"])
    emer["fecha"] = pd.to_datetime(emer["fecha"], format="%Y-%m-%d", errors="raise")
    for col in ["personas_afectadas", "viviendas_afectadas", "vias_afectadas"]:
        emer[col] = pd.to_numeric(emer[col], errors="raise").astype("int64")

    if not emer["fecha"].between(f"{C.ANIO_INI}-01-01", f"{C.ANIO_FIN}-12-31").all():
        raise ContratoError("emergencias: fecha fuera del rango del panel")
    if (emer[["personas_afectadas", "viviendas_afectadas", "vias_afectadas"]] < 0).any().any():
        raise ContratoError("emergencias: metricas de impacto negativas")
    if emer.duplicated(["fecha", "codigo_dane", "evento"]).any():
        raise ContratoError("emergencias: evento duplicado (fecha, municipio, tipo)")

    emer["anio"] = emer["fecha"].dt.year.astype("int64")
    emer["mes"] = emer["fecha"].dt.month.astype("int64")
    emer["es_mm"] = emer["evento"].eq(C.EVENTO_MM)
    return emer.sort_values(["fecha", "codigo_dane"]).reset_index(drop=True)


# Carga el catalogo de municipios y acota coordenadas a la caja de Santander,
# para detectar si algún punto quedo fuera del departamento.
def cargar_municipios(ruta: Path = C.MUNICIPIOS_CSV) -> pd.DataFrame:
    muni = pd.read_csv(ruta, encoding=C.ENCODING)
    muni["codigo_dane"] = normalizar_codigo(muni["codigo_dane"], "municipios")
    muni["municipio"] = normalizar_texto(muni["municipio"])
    for col in ["latitud", "longitud", "altitud_m"]:
        muni[col] = pd.to_numeric(muni[col], errors="raise")
    if not muni["latitud"].between(5.0, 8.5).all():
        raise ContratoError("municipios: latitud fuera de Santander")
    if not muni["longitud"].between(-75.5, -71.0).all():
        raise ContratoError("municipios: longitud fuera de Santander")
    return muni.sort_values("codigo_dane").reset_index(drop=True)


# Carga los limites municipales, castea codigo_dane a entero y declara el CRS
# que el archivo omite. Sin ese crs, Folium y GeoPandas no saben si las
# coordenadas son grados o metros. Tampoco se valida que el poligono no tenga
# autointersecciones: se verifico aparte que los 87 estan limpios.
def cargar_geometrias(ruta: Path = C.GEOJSON_MUNICIPIOS) -> dict:
    with open(ruta, encoding=C.ENCODING) as fh:
        geo = json.load(fh)

    if geo.get("type") != "FeatureCollection":
        raise ContratoError("geojson: no es un FeatureCollection")
    if "crs" not in geo:
        geo["crs"] = {"type": "name", "properties": {"name": C.CRS_GEOJSON}}

    for feat in geo["features"]:
        props = feat["properties"]
        props["codigo_dane"] = int(props["codigo_dane"])
        props["municipio"] = normalizar_texto(pd.Series([props.get("municipio")])).iloc[0]
        if feat["geometry"] is None:
            raise ContratoError("geojson: feature sin geometria")
        if feat["geometry"]["type"] not in {"Polygon", "MultiPolygon"}:
            raise ContratoError(f"geojson: tipo no soportado {feat['geometry']['type']}")

    codigos = [f["properties"]["codigo_dane"] for f in geo["features"]]
    if len(codigos) != len(set(codigos)):
        raise ContratoError("geojson: codigo_dane duplicado")
    return geo


# Area de un anillo en km2 con la formula del exceso esferico. Se usa solo para
# la bitacora: no hace falta proyectar ni proyectar con PyProj, y el geojson esta
# en lon/lat, que es justamente lo que la formula espera.
def _area_anillo_km2(anillo: list) -> float:
    radio = 6371.0088
    total = 0.0
    for i in range(len(anillo)):
        lon1, lat1 = anillo[i][0], anillo[i][1]
        lon2, lat2 = anillo[(i + 1) % len(anillo)][0], anillo[(i + 1) % len(anillo)][1]
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    return abs(total * radio * radio / 2)


# Suma el area de todos los municipios del geojson, aceptando Polygon y
# MultiPolygon. Los multipoligonos se resuelven como anillo exterior menos
# anillos interiores.
def _area_geometrias_km2(geometrias: dict) -> float:
    total = 0.0
    for feat in geometrias["features"]:
        geom = feat["geometry"]
        partes = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poligono in partes:
            total += _area_anillo_km2(poligono[0])
            for hueco in poligono[1:]:
                total -= _area_anillo_km2(hueco)
    return total


# --------------------------------------------------------------------------- #
# Recalculo de derivadas y marcado de artefactos
# --------------------------------------------------------------------------- #


# Suma movil de 12 meses por municipio, EXCLUYENDO el mes actual.
# El min_periods=12 es deliberado: si la ventana no esta completa el valor es
# desconocido, no cero, y por eso queda como NaN en vez de rellenarse con 0.
def _rango_por_municipio(panel: pd.DataFrame, col: str) -> pd.Series:
    return panel.groupby("codigo_dane", sort=False)[col].transform(
        lambda s: s.shift(1).rolling(12, min_periods=12).sum()
    )


# Recalcula desde el registro de emergencias las columnas derivadas del panel y
# marca los artefactos de arranque.
#
# Convencion de nombres: las columnas originales del panel se dejan intactas, y
# las recalculadas llevan sufijo _calc. El modelo usara solo las _calc; las
# originales quedan para poder auditar cuantas filas coinciden.
#
# Devuelve el panel ampliado y la bitacora de decisiones tomadas.
def recalcular_derivadas(
    panel: pd.DataFrame, emergencias: pd.DataFrame
) -> tuple[pd.DataFrame, list[dict]]:
    informe: list[dict] = []
    panel = panel.sort_values(["codigo_dane", "anio", "mes"]).reset_index(drop=True)

    por_mes = emergencias.groupby(["codigo_dane", "anio", "mes"]).agg(
        eventos_mes_calc=("evento", "size"),
        mm_mes_calc=("es_mm", "sum"),
    )
    panel = panel.merge(por_mes, on=["codigo_dane", "anio", "mes"], how="left")
    panel = panel.sort_values(["codigo_dane", "anio", "mes"]).reset_index(drop=True)
    panel["eventos_mes_calc"] = panel["eventos_mes_calc"].fillna(0).astype("int64")
    panel["mm_mes_calc"] = panel["mm_mes_calc"].fillna(0).astype("int64")
    panel["hubo_mm_calc"] = panel["mm_mes_calc"].gt(0).astype("int64")

    grp = panel.groupby("codigo_dane", sort=False)
    panel["eventos_12m_calc"] = _rango_por_municipio(panel, "eventos_mes_calc")
    panel["mm_12m_calc"] = _rango_por_municipio(panel, "mm_mes_calc")
    panel["historial_12m_completo"] = panel["eventos_12m_calc"].notna()

    panel["lluvia_mm_mes_anterior_calc"] = grp["lluvia_mm"].shift(1)
    panel["lluvia_acumulada_12m"] = grp["lluvia_mm"].transform(
        lambda s: s.shift(1).rolling(12, min_periods=12).sum()
    )
    panel["periodo"] = panel["anio"] * 12 + panel["mes"]
    panel["altitud_estatica"] = grp["altitud_m"].transform("first")

    # Detecta el valor fabricado de 2015-01: la columna trae un numero, pero el
    # shift(1) da NaN porque no existe mes anterior. Solo puede ocurrir ahi.
    panel["artefacto_lluvia_imputada"] = (
        panel["lluvia_mm_mes_anterior_calc"].isna()
        & panel["lluvia_mm_mes_anterior"].notna()
    )
    n_lluvia = int(panel["artefacto_lluvia_imputada"].sum())
    _log(
        informe,
        "lluvia_mm_mes_anterior",
        n_lluvia,
        "2015-01: el panel trae un valor que no puede ser shift(1) porque no hay "
        "mes anterior. Se marca artefacto_lluvia_imputada=True y esas filas se "
        "excluyen del modelado.",
    )

    # Compara el eventos_12m del panel contra la ventana parcial reproducible
    # con los datos entregados, para medir cuantas filas dependen de 2014.
    ventana_na = panel["eventos_12m_calc"].isna()
    parcial = grp["eventos_mes_calc"].transform(
        lambda s: s.shift(1).rolling(12, min_periods=1).sum()
    )
    year2015 = panel["anio"].eq(C.ANIO_INI)
    n_discrepan = int(panel.loc[year2015, "eventos_12m"].ne(parcial[year2015]).sum())
    _log(
        informe,
        "eventos_12m",
        n_discrepan,
        "La columna del panel usa una ventana calendario de 12 meses. Durante 2015 "
        "esa ventana alcanza a 2014, un ano que no viene en los archivos: por eso "
        f"discrepan en {n_discrepan} filas con un patron decreciente (87 en enero, 6 "
        "en diciembre). No es informacion del futuro, es historico que no nos "
        "entregaron, y por tanto no es reproducible ni auditable.",
    )
    # El costo de descartar 2015 se mide en positivos reales perdidos, no con
    # una cifra escrita a mano que deja de ser cierta si cambia el panel.
    positivos_perdidos = int(panel.loc[ventana_na, "hubo_mm_calc"].sum())
    positivos_totales = int(panel["hubo_mm_calc"].sum())
    _log(
        informe,
        "ventana_12m",
        int(ventana_na.sum()),
        "Filas sin historial completo de 12 meses: todo 2015 "
        f"({panel.loc[ventana_na, 'codigo_dane'].nunique()} municipios x "
        f"{panel.loc[ventana_na, 'mes'].nunique()} meses). No son 0 eventos, son "
        "informacion ausente: van como NaN y esas filas quedan fuera del modelado. "
        f"Costo: {positivos_perdidos} de los {positivos_totales} positivos "
        f"historicos ({positivos_perdidos / positivos_totales:.1%}).",
    )

    _log(
        informe,
        "lluvia_mm",
        int((panel["lluvia_mm"] > 1000).sum()),
        "Meses con mas de 1000 mm. No es error: se concentran en Puerto Parra y "
        "Puerto Wilches, los municipios mas humedos del departamento. Se "
        "conservan; el modelo usara rezagos y anomalias, no el valor crudo.",
    )

    vias = pd.to_numeric(emergencias["vias_afectadas"], errors="coerce")
    n_vias = int(vias.notna().sum())
    _log(
        informe,
        "vias_afectadas",
        n_vias,
        f"La columna toma solo valores {sorted(vias.dropna().unique().tolist())} en "
        f"los {n_vias} registros con dato: es una bandera, no un conteo. No se usa "
        "como magnitud de dano.",
    )

    return panel, informe


# Validacion de contratos

# Comprueba la integridad cruzada de los cuatro archivos. Se ejecuta en cada
# carga y falla ruidosamente en vez de rellenar Huecos, para que un cambio en
# los CSV no pase desapercibido.
def validar(datos: Datos) -> None:
    panel, emer, muni = datos.panel, datos.emergencias, datos.municipios
    geo_codigos = {f["properties"]["codigo_dane"] for f in datos.geometrias["features"]}

    sets = {
        "panel": set(panel["codigo_dane"].unique()),
        "municipios": set(muni["codigo_dane"]),
        "emergencias": set(emer["codigo_dane"]),
        "geojson": geo_codigos,
    }
    base = sets["panel"]
    if not base == sets["municipios"] == sets["geojson"]:
        raise ContratoError(f"los catalogos municipales no coinciden: {sets}")
    if not sets["emergencias"] <= base:
        raise ContratoError(f"emergencias con municipios fuera del panel: {sets['emergencias'] - base}")

    nombres_panel = (
        panel.drop_duplicates("codigo_dane").set_index("codigo_dane")["municipio"].astype(str)
    )
    referencias = {
        "municipios": muni.set_index("codigo_dane")["municipio"],
        "geojson": pd.Series(
            {f["properties"]["codigo_dane"]: f["properties"]["municipio"]
             for f in datos.geometrias["features"]}
        ),
        "emergencias": emer.drop_duplicates("codigo_dane").set_index("codigo_dane")["municipio"],
    }
    for nombre, ref in referencias.items():
        comparado = ref.reindex(nombres_panel.index).astype(str)
        if not comparado.equals(nombres_panel):
            distintos = nombres_panel.index[comparado.values != nombres_panel.values].tolist()
            raise ContratoError(
                f"nombres de municipio inconsistentes en {nombre} para {distintos}"
            )

    esperadas = len(base) * (C.ANIO_FIN - C.ANIO_INI + 1) * 12
    if len(panel) != esperadas:
        faltantes = esperadas - len(panel)
        raise ContratoError(f"panel incompleto: {len(panel)} filas, faltan {faltantes}")

    origen = COLUMNAS_ORIGEN
    if panel[origen].isna().any().any():
        raise ContratoError(f"panel con nulos en columnas de origen: {origen}")

    # Los NaN de las columnas nuevas solo pueden aparecer donde la marca de
    # calidad dice que la ventana de 12 meses esta incompleta.
    ventana_na = panel["eventos_12m_calc"].isna()
    if not ventana_na.eq(~panel["historial_12m_completo"]).all():
        raise ContratoError("eventos_12m_calc es NaN fuera del arranque de la ventana de 12 meses")
    if not panel["mm_12m_calc"].isna().eq(ventana_na).all():
        raise ContratoError("mm_12m_calc no comparte la mascara de arranque con eventos_12m_calc")
    if not panel["lluvia_acumulada_12m"].isna().eq(ventana_na).all():
        raise ContratoError("lluvia_acumulada_12m no comparte la mascara de arranque")
    if not panel["lluvia_mm_mes_anterior_calc"].isna().eq(
        panel["artefacto_lluvia_imputada"]
    ).all():
        raise ContratoError("lluvia_mm_mes_anterior_calc deberia ser NaN solo en 2015-01")

    st = set(emer["evento"].unique())
    if st != set(C.EVENTOS_VALIDOS):
        raise ContratoError(f"tipos de evento inesperados: {st ^ set(C.EVENTOS_VALIDOS)}")

    # El panel debe ser reproducible desde el registro de emergencias.
    mal = panel[panel["hubo_mm"] != panel["hubo_mm_calc"]]
    if len(mal):
        raise ContratoError(f"hubo_mm no reproducible desde emergencias en {len(mal)} filas")
    mal = panel[panel["eventos_mes"] != panel["eventos_mes_calc"]]
    if len(mal):
        raise ContratoError(f"eventos_mes no reproducible desde emergencias en {len(mal)} filas")

    if not panel["lluvia_mm_mes_anterior_calc"].equals(
        panel["lluvia_mm_mes_anterior"].where(~panel["artefacto_lluvia_imputada"])
    ):
        raise ContratoError("lluvia_mm_mes_anterior no es shift(1) fuera de 2015-01")


# Filtra el panel a las filas utilizables para entrenar.
# Se descarta 2015 completo: su ventana de 12 meses depende de 2014, que no viene
# en los datos. Desde 2016-01 la ventana es reproducible y el marco queda en
# 87 municipios x 120 meses = 10.440 filas, con 906 positivos.
def filas_modelables(panel: pd.DataFrame) -> pd.DataFrame:
    usable = panel["historial_12m_completo"] & ~panel["artefacto_lluvia_imputada"]
    return panel.loc[usable].reset_index(drop=True)


# Punto de entrada

# Carga los cuatro archivos, recalcula las derivadas, valida los contratos y
# devuelve el paquete completo con su bitacora.
def cargar_todo() -> Datos:
    informe: list[dict] = []
    panel = cargar_panel()
    emer = cargar_emergencias()
    muni = cargar_municipios()
    geo = cargar_geometrias()
    panel, informe_panel = recalcular_derivadas(panel, emer)
    informe.extend(informe_panel)

    datos = Datos(panel=panel, emergencias=emer, municipios=muni, geometrias=geo)
    validar(datos)
    informe.append(
        {
            "artefacto": "validacion_contratos",
            "filas_afectadas": 0,
            "decision": "Los cuatro archivos cruzan 87/87 por codigo_dane, panel "
            "balanceado y sin nulos, y hubo_mm y eventos_mes son reproducibles "
            "desde el registro de emergencias.",
        }
    )

    # El area se mide aca y no en recalcular_derivadas porque es el unico punto
    # donde se tiene el geojson a mano. Se compara contra la superficie real del
    # departamento para dejar por escrito que los limites son aproximados.
    area_geojson = _area_geometrias_km2(geo)
    n_poligonos = len(geo["features"])
    _log(
        informe,
        "geometria",
        n_poligonos,
        f"Limites aproximados: {n_poligonos} poligonos sin autointersecciones, "
        f"area total medida {area_geojson:,.0f} km2 frente a {C.AREA_REAL_KM2:,.0f} "
        f"km2 reales del departamento ({area_geojson / C.AREA_REAL_KM2:.0%}). El "
        "coropleto es ilustrativo, no cartografia oficial: sirve para ubicar el "
        "municipio en el mapa, no para medir damnificados.",
    )

    datos.informe = pd.DataFrame(informe)
    return datos