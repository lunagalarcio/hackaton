"""
Boletines por municipio, con una plantilla por nivel del semáforo.

Cada número que aparece en el texto sale del diccionario `cifras`, que se
arma con los datos y el modelo. Al final se comprueba con verificar_cifras.
Si alguna cifra no está en el diccionario, el boletín no se exporta.

Uso en el cuaderno:
    from boletines import generar_boletin, verificar_cifras
"""
import re

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fmt(valor, decimales=None):
    """Número con coma decimal, como se escribe en el boletín."""
    if decimales is None:
        decimales = 0 if float(valor).is_integer() else (1 if round(valor, 1) == valor else 2)
    texto = f"{valor:.{decimales}f}"
    return texto.replace(".", ",")


def verificar_cifras(texto, cifras):
    """Devuelve la lista de números del texto que NO están en el diccionario."""
    permitidas = [float(v) for v in cifras.values()]
    encontrados = re.findall(r"\d+(?:,\d+)?", texto)
    return sorted({n for n in encontrados
                   if not any(abs(float(n.replace(",", ".")) - p) < 1e-9 for p in permitidas)})


def nivel_de(prob, umbral, factor_amarillo=0.6):
    if prob >= umbral:
        return "rojo"
    if prob >= umbral * factor_amarillo:
        return "amarillo"
    return "verde"


def razones_texto(v):
    """Las tres razones principales en el orden que entregue SHAP para ese municipio.
    `v["orden"]` es la lista de variables, de mayor a menor contribución."""
    textos = {
        "tasa_historica": ("Historial del municipio",
                           f"Movimiento en masa en el {fmt(v['tasa_hist_pct'])} % de los meses"),
        "lluvia_rel_promedio": ("Lluvia del mes anterior",
                                f"{fmt(v['lluvia_mm'])} mm en {v['mes_anterior']}, "
                                f"{fmt(v['lluvia_ratio'], 1)} veces su promedio"),
        "emergencias_12m": ("Emergencias recientes",
                            f"{fmt(v['emergencias_12m'])} emergencias en los últimos 12 meses"),
        "meses_mm_12m": ("Último año",
                         f"{fmt(v['meses_mm_12m'])} meses con movimiento en masa"),
        "mes_sin": ("Época del año", f"{v['mes'].capitalize()}, temporada de lluvias"
                    if v["temporada"] else f"{v['mes'].capitalize()}, fuera de temporada de lluvias"),
        "terreno": ("Terreno", f"Altitud media de {fmt(v['altitud_m'])} m sobre el mar"),
    }
    return [{"variable": k, "etiqueta": textos[k][0], "detalle": textos[k][1]} for k in v["orden"][:3]]


def generar_boletin(municipio, prob, puesto, total, umbral, v, corte_texto, mes_texto, anio,
                    factor_amarillo=0.6):
    """Arma título, párrafos y diccionario de cifras para un municipio.

    v: valores del municipio sacados del panel, todos conocidos al día 1:
       tasa_hist_pct, lluvia_mm, lluvia_ratio, mes_anterior, mes, temporada (bool),
       emergencias_12m, meses_mm_12m, altitud_m, orden (variables por contribución SHAP)
    """
    nivel = nivel_de(prob, umbral, factor_amarillo)
    p = round(prob * 100)
    u_am = round(umbral * factor_amarillo, 3)

    cifras = {
        "probabilidad_pct": p, "umbral": umbral, "umbral_precaucion": u_am,
        "puesto": puesto, "municipios_total": total,
        "tasa_hist_pct": v["tasa_hist_pct"], "lluvia_mm": v["lluvia_mm"],
        "lluvia_ratio": v["lluvia_ratio"], "emergencias_12m": v["emergencias_12m"],
        "meses_mm_12m": v["meses_mm_12m"], "ventana_meses": 12,
        "altitud_m": v["altitud_m"],
        "anio": anio, "dia_corte": 1, "temporadas": 2,
    }

    if puesto == 1:
        lugar = f"Es la probabilidad más alta de los {total} municipios del departamento."
    else:
        lugar = f"Ocupa el puesto {puesto} entre los {total} municipios del departamento."

    contexto = (f"{municipio} ha registrado movimientos en masa en el {fmt(v['tasa_hist_pct'])} % "
                f"de los meses de su historial. En {v['mes_anterior']} llovieron {fmt(v['lluvia_mm'])} mm, "
                f"{fmt(v['lluvia_ratio'], 1)} veces su promedio para ese mes.")
    if "emergencias_12m" in v["orden"][:3]:
        contexto += f" En los últimos 12 meses reportó {fmt(v['emergencias_12m'])} emergencias."
    elif "meses_mm_12m" in v["orden"][:3]:
        contexto += f" En el último año tuvo {fmt(v['meses_mm_12m'])} meses con movimiento en masa."
    if v["temporada"]:
        contexto += f" Además, {v['mes']} es una de las dos temporadas de mayor riesgo del año."

    if nivel == "rojo":
        titulo = f"Alerta por movimiento en masa en {municipio}"
        p1 = (f"Para {mes_texto}, el modelo estima una probabilidad del {p} % de que ocurra al menos "
              f"un movimiento en masa en {municipio}. Supera el umbral de alerta de {fmt(umbral, 2)}. {lugar}")
        p3 = ("Se recomienda al consejo municipal de gestión del riesgo revisar los sectores con "
              "antecedentes, verificar las rutas de evacuación y mantener activos los canales de aviso "
              "a la comunidad durante el mes.")
    elif nivel == "amarillo":
        titulo = f"Precaución por movimiento en masa en {municipio}"
        p1 = (f"Para {mes_texto}, el modelo estima una probabilidad del {p} % de que ocurra al menos "
              f"un movimiento en masa en {municipio}. No alcanza el umbral de alerta de {fmt(umbral, 2)}, "
              f"pero supera el nivel de precaución de {fmt(u_am, 3)}. {lugar}")
        p3 = ("Se recomienda al consejo municipal hacer seguimiento a las lluvias y a los sectores con "
              "antecedentes, y estar listo para activar los protocolos si la situación cambia.")
    else:
        titulo = f"Sin alerta por movimiento en masa en {municipio}"
        p1 = (f"Para {mes_texto}, el modelo estima una probabilidad del {p} % de que ocurra al menos "
              f"un movimiento en masa en {municipio}, por debajo del nivel de precaución de {fmt(u_am, 3)}. {lugar}")
        p3 = ("No se recomiendan acciones adicionales. Un nivel bajo no descarta eventos causados por "
              "lluvias fuertes de pocas horas, así que se recomienda mantener el monitoreo habitual y "
              "reportar cualquier evento al sistema.")

    p4 = f"El historial usado en este boletín llega hasta el {corte_texto}."
    parrafos = [p1, contexto, p3, p4]
    razones = razones_texto(v)

    texto_completo = " ".join([titulo] + parrafos + [r["detalle"] for r in razones])
    faltantes = verificar_cifras(texto_completo, cifras)
    if faltantes:
        raise ValueError(f"{municipio}: cifras sin respaldo en el boletín: {faltantes}")

    return {"nivel": nivel, "titulo": titulo, "parrafos": parrafos, "razones": razones, "cifras": cifras}
