from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

DATOS_DIR = RAIZ / "datos"
OUTPUT_DIR = RAIZ / "outputs"

PANEL_CSV = DATOS_DIR / "panel_municipio_mes.csv"
EMERGENCIAS_CSV = DATOS_DIR / "emergencias_santander.csv"
MUNICIPIOS_CSV = DATOS_DIR / "municipios_santander.csv"
GEOJSON_MUNICIPIOS = DATOS_DIR / "santander_municipios.geojson"

ENCODING = "utf-8"
SEMILLA = 42

ANIO_INI = 2015
ANIO_FIN = 2025

FECHA_CORTE = (2025, 10)
MES_OBJETIVO = 10
ANIO_OBJETIVO = 2025

EVENTO_MM = "Movimiento en masa"
EVENTOS_VALIDOS = frozenset(
    {
        EVENTO_MM,
        "Inundación",
        "Incendio forestal",
        "Vendaval",
        "Creciente súbita",
    }
)

CRS_GEOJSON = "EPSG:4326"
CODIGO_DANE_LONGITUD = 5
PREFIJO_DANE = "68"

AREA_REAL_KM2 = 36713


# Decodifica periodo = anio * 12 + mes.
#
# El cociente de la division NO siempre da el ano: como mes va de 1 a 12,
# dividir sin corregir arrastra diciembre al ano siguiente. El periodo 24312,
# que es 2025-12, al cociente da 2026. Restar 1 antes de dividir deja el ano
# real, y el mes es lo que sobra.
def anio_de_periodo(periodo: int) -> int:
    return (int(periodo) - 1) // 12


def mes_de_periodo(periodo: int) -> int:
    return int(periodo) - 12 * anio_de_periodo(periodo)


def periodo_de(anio: int, mes: int) -> int:
    return int(anio) * 12 + int(mes)