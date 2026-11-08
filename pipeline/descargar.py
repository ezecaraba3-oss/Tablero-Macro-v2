"""Baja fuentes y las guarda en pipeline/fuentes/.

    python pipeline/descargar.py            todas
    python pipeline/descargar.py fiscal     solo las indicadas (ver FUENTES_POR_ID)

Para el uso diario está pipeline/actualizar.py, que baja solo lo vencido.

Las URL de la Secretaría de Finanzas cambian con cada publicación: se buscan en estas
páginas, y DEUDA_MENSUAL_URL y DEUDA_TRIM_URL quedan como respaldo:
https://www.argentina.gob.ar/economia/finanzas/datos-mensuales y
https://www.argentina.gob.ar/economia/finanzas/datos-trimestrales-de-la-deuda
"""
import csv
import datetime as dt
import io
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = Path(__file__).resolve().parent.parent
FUENTES = RAIZ / "pipeline" / "fuentes"
UA = {"User-Agent": "tablero-macro-v2/1.0"}
DEUDA_MENSUAL_URL = "https://www.argentina.gob.ar/sites/default/files/boletin_mensual_30_09_2026_0.xlsx"
DEUDA_TRIM_URL = "https://www.argentina.gob.ar/sites/default/files/deuda_publica_30-06-2026_0.xlsx"
BCRA_URL = "https://api.bcra.gob.ar/estadisticas/v4.0/Monetarias"
X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RX = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}

SERIES_TRIM = {
    "cc": "160.2_TL_CUENNTE_0_T_22", "cc_bienes": "160.2_CTA_CORNES_0_T_46", "cc_servicios": "160.2_CTA_CORIOS_0_T_49",
    "cc_rentas": "160.2_CTA_CORION_0_T_58", "cc_remuneraciones": "160.2_CTA_CORDOS_0_T_49", "cap": "160.2_TL_CUENTAL_0_T_20",
    "cfin": "160.2_TL_CUENERA_0_T_23", "cfin_directa": "160.2_CTA_FINCTA_0_T_41", "cfin_cartera": "160.2_CTA_FINERA_0_T_41",
    "cfin_otra": "160.2_CTA_FINION_0_T_38", "cfin_derivados": "160.2_CTA_FINROS_0_T_36", "errores": "160.2_ERES_OMTOS_0_T_23",
    "iip_neta": "144.4_PCIONETA_0_T_37", "iip_gobierno": "144.4_GERNOGRAL_0_T_22", "iip_bcra": "144.4_BOCENTRAL_0_T_19",
    "iip_bancos": "144.4_SEDADESTOS_0_T_31", "iip_otros": "144.4_OSSECTRES_0_T_14",
    "subocupacion": "46.2_ECTST_0_T_36", "asal_sin_desc": "52.2_ASDJ_0_0_37",
}
SERIES_MES = {
    # emp_publico y emp_casas usan la versión con estacionalidad: la desestacionalizada está vacía en la API.
    "emp_total": "151.1_TL_SIN_TAC_2012_M_15", "emp_privado": "151.1_AARIADOTAC_2012_M_26", "emp_publico": "151.1_AARIADODAD_2012_M_30",
    "emp_casas": "151.1_AARIADODAD_2012_M_45", "emp_autonomos": "151.1_IPENDIETAC_2012_M_34", "emp_monotributo": "151.1_IPENDIETAC_2012_M_36",
    "emp_mono_social": "151.1_IPENDIETAC_2012_M_43",
    "viajes_cobros": "185.1_COBRO_SERVJES_0_M_30", "viajes_pagos": "185.1_PAGO_SERVIJES_0_M_29",
}
# Sector Público Nacional, base caja, metodología 2017 (millones de pesos).
SERIES_FISCAL = {
    "f_ingresos": "379.9_ING_ANTES_017__26_83", "f_ing_primarios": "379.9_ING_PRIMAR017__36_12",
    "f_gastos": "379.9_GTOS_ANTES017__27_85", "f_gastos_corrientes": "379.9_GTOS_CORR_017__14_1",
    "f_superavit": "379.9_SUPERAVIT_017__23_94",
    "f_financiero": "379.9_RESULTADO_017__36_89", "f_intereses": "379.9_GTOS_CORR_017__40_84",
    "f_int_local": "379.9_GTOS_CORR_017__42_6", "f_int_extranjera": "379.9_GTOS_CORR_017_1_0_M_44_46",
    "f_prestaciones": "379.9_GTOS_CORR_017__35_92", "f_remuneraciones": "379.9_GTOS_CORR_017__49_26",
    "f_bienes_serv": "379.9_GTOS_CORR_017__51_65", "f_transf_provincias": "379.9_GTOS_CORR_017_5_0_M_51_42",
    "f_universidades": "379.9_GTOS_CORR_017_7_0_M_38_20", "f_transf_otras": "379.9_GTOS_CORR_017_8_0_M_37_3",
    "f_deficit_empresas": "379.9_GTOS_CORR_017_X_0_M_45_99", "f_otros_corrientes": "379.9_GTOS_CORR_017__28_34",
    "f_transf_exterior": "379.9_GTOS_CORR_017__34_72", "f_otras_rentas": "379.9_GTOS_CORR_017__37_97",
    "f_capital_directa": "379.9_GTOS_CAP_I017__36_40", "f_capital_provincias": "379.9_GTOS_CAP_T017__50_91",
    "f_capital_otras": "379.9_GTOS_CAP_T017__27_3", "f_capital_resto": "379.9_GTOS_CAP_R017__19_90",
}
BCRA_FLUJO = {"res_compras": 78, "res_organismos": 79, "res_sector_publico": 80, "res_encajes": 81, "res_otras": 82}
BCRA_STOCK = {"reservas_ult": 1, "base_monetaria": 15, "dep_usd_priv": 108, "prest_usd_priv": 125, "pases_pasivos": 152, "leliq": 155, "lebac_bopreal": 158}


def bajar(url, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def api(ids):
    """Series de datos.gob.ar, de a 30 por pedido: {clave: {AAAA-MM: valor}}."""
    salida = {k: {} for k in ids}
    claves = list(ids)
    for i in range(0, len(claves), 30):
        lote = claves[i:i + 30]
        u = "https://apis.datos.gob.ar/series/api/series/?" + urllib.parse.urlencode(
            {"ids": ",".join(ids[k] for k in lote), "limit": 5000, "format": "json"})
        datos = json.loads(bajar(u))["data"]
        for fila in datos:
            for k, v in zip(lote, fila[1:]):
                if v is not None:
                    salida[k][fila[0][:7]] = v
    vacias = [k for k, v in salida.items() if not v]
    if vacias:
        print(f"AVISO: series sin datos en la API: {vacias}")
    return {k: v for k, v in salida.items() if v}


def bcra(idv, desde="2010-01-01", hasta=None):
    """Serie diaria del BCRA, paginada: [(AAAA-MM-DD, valor)]."""
    hasta = hasta or dt.date.today().isoformat()
    filas, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"desde": desde, "hasta": hasta, "limit": 3000, "offset": offset})
        res = json.loads(bajar(f"{BCRA_URL}/{idv}?{q}", 180)).get("results", [])
        detalle = res[0].get("detalle", []) if res else []
        filas += [(d["fecha"], d["valor"]) for d in detalle]
        if len(detalle) < 3000:
            break
        offset += 3000
    return sorted(filas)


def libro(contenido):
    z = zipfile.ZipFile(io.BytesIO(contenido))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    textos = ["".join(t.text or "" for t in si.iter(X + "t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
    hojas = {}
    for h in wb.find(X + "sheets"):
        destino = rels[h.get(RX + "id")].lstrip("/")
        destino = destino if destino.startswith("xl/") else "xl/" + destino
        filas = {}
        for f in ET.fromstring(z.read(destino)).find(X + "sheetData"):
            v = {}
            for c in f:
                e = c.find(X + "v")
                if e is None or e.text is None:
                    continue
                n = 0
                for ch in re.match(r"[A-Z]+", c.get("r")).group():
                    n = n * 26 + ord(ch) - 64
                v[n - 1] = textos[int(e.text)] if c.get("t") == "s" else e.text
            if v:
                filas[int(f.get("r"))] = v
        hojas[h.get("name")] = filas
    return hojas


def mes_de(celda):
    """Convierte un encabezado de la planilla ('43466' o 'ago-26 (*)') en AAAA-MM."""
    celda = celda.strip()
    if re.fullmatch(r"\d{5}(\.0+)?", celda):
        return (dt.date(1899, 12, 30) + dt.timedelta(days=int(float(celda)))).strftime("%Y-%m")
    m = re.match(r"([a-z]{3})-(\d{2})", celda.lower())
    return f"20{m.group(2)}-{MESES[m.group(1)]:02d}" if m and m.group(1) in MESES else None


def columnas_mes(hoja, fila_titulo=None):
    """Busca la primera fila de encabezados con meses, a partir de fila_titulo."""
    for r in sorted(hoja):
        if fila_titulo and r < fila_titulo:
            continue
        cols = {c: mes_de(v) for c, v in hoja[r].items() if c >= 2 and mes_de(v)}
        if len(cols) > 12:
            return cols
    sys.exit("No encontré la fila de meses en la planilla de deuda")


def serie_fila(hoja, etiqueta, cols, desde=0, col_etiqueta=None):
    """Valores de la primera fila cuya etiqueta coincide exactamente, desde la fila indicada."""
    for r in sorted(hoja):
        if r < desde:
            continue
        v = hoja[r]
        textos = [str(x).strip() for c, x in v.items() if c <= 2 and (col_etiqueta is None or c == col_etiqueta)]
        if etiqueta in textos:
            return {m: float(v[c]) for c, m in cols.items() if c in v and re.fullmatch(r"-?[\d.]+(E-?\d+)?", str(v[c]))}
    sys.exit(f"No encontré la fila «{etiqueta}» en la planilla de deuda")


def enlace(pagina, patron, defecto):
    """Busca el archivo vigente en la página oficial: el nombre cambia con cada publicación."""
    try:
        m = re.search(patron, bajar(pagina).decode("utf-8", "replace"))
        return m.group(0) if m else defecto
    except Exception:
        return defecto


def deuda_mensual():
    h = libro(bajar(enlace("https://www.argentina.gob.ar/economia/finanzas/datos-mensuales", r"https://[^\"']+boletin_mensual[^\"']+\.xlsx", DEUDA_MENSUAL_URL)))
    a1, a2, a3, a5 = h["A.1"], h["A.2"], h["A.3"], h["A.5"]
    c1, c2, c3, c5 = columnas_mes(a1), columnas_mes(a2), columnas_mes(a3), columnas_mes(a5)
    fila_comp = next(r for r, v in a3.items() if "COMPOSICIÓN POR MONEDA" in " ".join(map(str, v.values())))
    fila_tasa = next(r for r, v in a3.items() if "COMPOSICIÓN POR TASA" in " ".join(map(str, v.values())))
    sal = {
        "deuda_bruta": serie_fila(a1, "A- DEUDA BRUTA ( I + II  + III)", c1),
        "deuda_org_int": serie_fila(a1, "ORGANISMOS INTERNACIONALES", c1),
        "deuda_fmi": serie_fila(a1, "FMI", c1),
        "deuda_oficiales": serie_fila(a1, "ORGANISMOS OFICIALES", c1),
        "deuda_titulos": serie_fila(a1, "TÍTULOS PÚBLICOS", c1),
        "deuda_ley_arg": serie_fila(a2, "I- LEGISLACIÓN ARGENTINA", c2),
        "deuda_ley_ext": serie_fila(a2, "II- LEGISLACIÓN EXTRANJERA", c2),
        "deuda_normal": serie_fila(a3, "DEUDA BRUTA EN SITUACIÓN DE PAGO NORMAL", c3),
        "deuda_ars_fija": serie_fila(a3, "Pesos no ajustable por CER", c3, fila_comp),
        "deuda_ars_cer": serie_fila(a3, "Pesos ajustable por CER", c3, fila_comp),
        "deuda_usd": serie_fila(a3, "Dólares", c3, fila_comp),
        "deuda_eur": serie_fila(a3, "Euros", c3, fila_comp),
        "deuda_jpy": serie_fila(a3, "Yenes", c3, fila_comp),
        "deuda_deg": serie_fila(a3, "DEG", c3, fila_comp),
        "deuda_otras": serie_fila(a3, "Otras monedas", c3, fila_comp),
        "deuda_tasa_fija": serie_fila(a3, "Tasa Fija", c3, fila_tasa),
        "deuda_tasa_cero": serie_fila(a3, "Tasa Cero", c3, fila_tasa),
        "deuda_tasa_var": serie_fila(a3, "Tasa Variable", c3, fila_tasa),
        "pagos_total": serie_fila(a5, "TOTAL PAGADO POR MONEDA", c5),
    }
    fila_mn = next(r for r, v in a5.items() if str(v.get(1, "")).strip() == "- MONEDA NACIONAL")
    fila_me = next(r for r, v in a5.items() if str(v.get(1, "")).strip() == "- MONEDA EXTRANJERA")
    sal["pagos_int_ars"] = serie_fila(a5, "INTERES", c5, fila_mn)
    sal["pagos_int_me"] = serie_fila(a5, "INTERES", c5, fila_me)
    sal["pagos_me"] = serie_fila(a5, "- MONEDA EXTRANJERA", c5)
    return sal


def deuda_trimestral():
    url = enlace("https://www.argentina.gob.ar/economia/finanzas/datos-trimestrales-de-la-deuda", r"https://[^\"']+deuda_publica_\d{2}-\d{2}-\d{4}[^\"']*\.xlsx", DEUDA_TRIM_URL)
    m = re.search(r"deuda_publica_(\d{2})-(\d{2})-(\d{4})", url)
    corte = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    h = libro(bajar(url))
    # Indicadores de sostenibilidad (anuales)
    s = h["A.4.7"]
    anios = {c: re.match(r"\s*(\d{4})", str(v)).group(1) for c, v in s[8].items() if c >= 3 and re.match(r"\s*\d{4}", str(v))}
    filas = {"deuda_pib": 10, "deuda_ext_pib": 11, "intereses_pib": 12, "servicios_pib": 13, "deuda_me_pct": 14, "deuda_cer_pct": 15,
             "vence_2a_pct": 19, "vida_promedio": 21, "deuda_me_reservas": 23, "deuda_me_expo": 26, "intereses_recursos": 29}
    rotulos = {"deuda_pib": "Deuda Bruta de la Administración Central", "deuda_ext_pib": "Deuda Externa", "intereses_pib": "Intereses Totales", "servicios_pib": "Servicios Totales",
               "deuda_me_pct": "Deuda en Moneda Extranjera", "deuda_cer_pct": "Deuda Ajustable por CER", "vence_2a_pct": "Servicios de Capital", "vida_promedio": "Vida Promedio",
               "deuda_me_reservas": "Deuda en Moneda Extranjera", "deuda_me_expo": "Deuda en Moneda Extranjera", "intereses_recursos": "Intereses Totales"}
    anual = {}
    for col, r in filas.items():
        if not str(s[r].get(2, "")).startswith(rotulos[col]):
            sys.exit(f"Indicadores de deuda: la fila {r} ya no es «{rotulos[col]}»: {s[r].get(2)}")
        escala = 1 if col == "vida_promedio" else 100
        anual[col] = {a: float(s[r][c]) * escala for c, a in anios.items() if c in s[r] and re.fullmatch(r"-?[\d.]+(E-?\d+)?", str(s[r][c]))}
    # Perfil anual de vencimientos
    p = h["A.3.6"]
    fila_cab = next(r for r, v in p.items() if str(v.get(1, "")).strip() == "TIPO DE ACREEDOR")
    cols = {c: str(v).strip() for c, v in p[fila_cab].items() if c >= 2 and str(v).strip() != "TOTAL"}
    fila_total = next(r for r, v in p.items() if str(v.get(1, "")).strip() == "TOTAL")
    capital = next(r for r in sorted(p) if r > fila_total and str(p[r].get(1, "")).strip() == "CAPITAL")
    interes = next(r for r in sorted(p) if r > fila_total and str(p[r].get(1, "")).strip() == "INTERÉS")
    perfil = [{"anio": a, "capital": round(float(p[capital][c]) / 1000, 1), "interes": round(float(p[interes][c]) / 1000, 1),
               "total": round(float(p[fila_total][c]) / 1000, 1)} for c, a in sorted(cols.items())]
    # Tasa y vida promedio al último trimestre
    tasas = h["A.1.5"]
    resumen = {"tasa_promedio": float(tasas[11][2]) * 100, "tasa_ars_fija": float(tasas[13][2]) * 100, "tasa_ars_cer": float(tasas[20][2]) * 100,
               "tasa_usd": float(tasas[27][2]) * 100, "tasa_fmi_deg": float(tasas[43][2]) * 100, "vida_promedio": float(h["A.1.6"][12][2])}
    return anual, perfil, resumen, corte


def guardar(nombre, columnas, filas):
    buf = io.StringIO()
    w = csv.DictWriter(buf, columnas, lineterminator="\n")
    w.writeheader()
    w.writerows(filas)
    (FUENTES / nombre).write_text(buf.getvalue(), encoding="utf-8", newline="\n")
    print(f"{nombre}: {len(filas)} filas, {len(columnas) - 1} columnas")


def a_filas(series, clave):
    indices = sorted({k for s in series.values() for k in s})
    return [{clave: i, **{c: ("" if i not in s else round(s[i], 4)) for c, s in series.items()}} for i in indices]


# Etapa 3
SERIES_DEMANDA = {
    "d_pib": "4.2_OGP_2004_T_17", "d_cons_priv": "4.2_MGCP_2004_T_25", "d_cons_pub": "4.2_DGCP_2004_T_30", "d_ibif": "4.2_DGIT_2004_T_25",
    "d_expo": "4.2_DGE_2004_T_26", "d_impo": "4.2_OGI_2004_T_25", "d_existencias": "4.2_VE_2004_T_21", "pib_n": "4.4_OGP_2004_T_17",
    "p_expo": "80.2_IIPENG_0_T_45", "q_expo": "80.2_IICENG_0_T_47",
}
SERIES_ACTIVIDAD = {
    "uci": "31.3_UNG_2004_M_18", "uci_metales": "31.3_UIMB_2004_M_33", "uci_quimicos": "31.3_USPQ_2004_M_34", "uci_textiles": "31.3_UPT_2004_M_23",
    "isac": "33.2_ISAC_SIN_EDAD_0_M_23_56", "issp": "302.3_S_DESEST_NRAL_0_S_19",
}
FRED = {"fed_funds": "FEDFUNDS", "ust10": "DGS10", "brent": "POILBREUSDM", "soja": "PSOYBUSDM", "maiz": "PMAIZMTUSDM", "trigo": "PWHEAMTUSDM"}
BCB = {"ibcbr": 24364, "brl": 3698, "selic": 4189}
LETRAS_URL = "https://api.argentinadatos.com/v1/finanzas/letras"


def fred(serie):
    """Promedio mensual de una serie de FRED: {AAAA-MM: valor}."""
    filas = list(csv.DictReader(io.StringIO(bajar(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie}").decode("utf-8"))))
    grupos = {}
    for f in filas:
        v = f.get(serie)
        if v not in (None, "", "."):
            grupos.setdefault(f["observation_date"][:7], []).append(float(v))
    return {m: sum(v) / len(v) for m, v in grupos.items()}


def bcb(serie):
    """Serie mensual del Banco Central de Brasil: {AAAA-MM: valor}."""
    d = json.loads(bajar(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados?formato=json"))
    return {f"{x['data'][6:10]}-{x['data'][3:5]}": float(x["valor"]) for x in d if x["valor"] not in ("", None)}


def cerrados(serie):
    """Deja solo meses terminados: un mes en curso cambiaría todos los días."""
    actual = dt.date.today().strftime("%Y-%m")
    return {m: v for m, v in serie.items() if m < actual}


DESDE_MERCADO = "2026-10-01"  # los meses anteriores salen de la base de la v1


def ad_dolar(casa):
    return [(x["fecha"], x["venta"]) for x in json.loads(bajar(f"https://api.argentinadatos.com/v1/cotizaciones/dolares/{casa}", 180))]


def ad_riesgo():
    return [(x["fecha"], x["valor"]) for x in json.loads(bajar("https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais", 180))]


def d_mercado():
    """Cierre mensual, con el mismo método de la v1: promedio del mes; reservas y bandas, último dato."""
    def promedio(filas):
        g = {}
        for f, v in filas:
            if f >= DESDE_MERCADO:
                g.setdefault(f[:7], []).append(v)
        return cerrados({m: sum(x) / len(x) for m, x in g.items()})

    def ultimo(filas):
        g = {}
        for f, v in sorted(filas):
            if f >= DESDE_MERCADO:
                g[f[:7]] = v
        return cerrados(g)

    s = {"tc_a3500": promedio(bcra(5, DESDE_MERCADO)), "reservas": ultimo(bcra(1, DESDE_MERCADO)), "badlar": promedio(bcra(7, DESDE_MERCADO)),
         "tasa_pf30": promedio(bcra(12, DESDE_MERCADO)), "tasa_personales": promedio(bcra(14, DESDE_MERCADO)),
         "banda_inf": ultimo(bcra(1187, DESDE_MERCADO)), "banda_sup": ultimo(bcra(1188, DESDE_MERCADO)),
         "dolar_blue": promedio(ad_dolar("blue")), "dolar_ccl": promedio(ad_dolar("contadoconliqui")), "dolar_mep": promedio(ad_dolar("bolsa")), "riesgo_pais": promedio(ad_riesgo())}
    guardar("mercado_mensual.csv", ["mes", *s], a_filas(s, "mes"))


def d_precios():
    s = {"infl_mensual": 27, "infl_ia": 28, "rem_12m": 29}
    out = {c: {f[:7]: v for f, v in bcra(i, "2026-09-01")} for c, i in s.items()}
    guardar("precios_mensual.csv", ["mes", *out], a_filas(out, "mes"))


def d_diario():
    """Último valor disponible de cada dato diario, con su fecha y el valor anterior."""
    desde = (dt.date.today() - dt.timedelta(days=25)).isoformat()
    fuentes = [("Dólar oficial mayorista", "$", bcra(5, desde)), ("Dólar blue", "$", ad_dolar("blue")), ("Dólar contado con liqui", "$", ad_dolar("contadoconliqui")),
               ("Dólar MEP", "$", ad_dolar("bolsa")), ("Riesgo país", "pb", ad_riesgo()), ("Reservas brutas", "M US$", bcra(1, desde)),
               ("Tasa BADLAR", "%", bcra(7, desde)), ("Tasa de plazo fijo a 30 días", "%", bcra(12, desde)), ("Techo de la banda cambiaria", "$", bcra(1188, desde)), ("Piso de la banda cambiaria", "$", bcra(1187, desde))]
    filas = []
    for nombre, unidad, serie in fuentes:
        serie = sorted(serie)
        f, v = serie[-1]
        filas.append({"indicador": nombre, "unidad": unidad, "fecha": f, "valor": v, "previo": serie[-2][1], "fecha_previa": serie[-2][0]})
    guardar("diario.csv", ["indicador", "unidad", "fecha", "valor", "previo", "fecha_previa"], filas)


def d_fiscal():
    d = api(SERIES_FISCAL)
    guardar("fiscal_mensual.csv", ["mes", *d], a_filas(d, "mes"))


def d_series_mensuales():
    d = api(SERIES_MES)
    guardar("series_mensuales.csv", ["mes", *d], a_filas(d, "mes"))


def d_series_trimestrales():
    d = api(SERIES_TRIM)
    trim = {c: {f"{m[:4]}-T{(int(m[5:]) + 2) // 3}": v for m, v in s.items()} for c, s in d.items()}
    guardar("series_trimestrales.csv", ["trimestre", *trim], a_filas(trim, "trimestre"))


def d_deuda_mensual():
    d = deuda_mensual()
    guardar("deuda_mensual.csv", ["mes", *d], a_filas(d, "mes"))


def d_deuda_trim():
    anual, perfil, resumen, corte = deuda_trimestral()
    guardar("deuda_anual.csv", ["anio", *anual], a_filas(anual, "anio"))
    guardar("deuda_perfil.csv", ["anio", "capital", "interes", "total"], perfil)
    guardar("deuda_resumen.csv", ["indicador", "valor"], [{"indicador": k, "valor": round(v, 3)} for k, v in resumen.items()] + [{"indicador": "corte", "valor": corte}])


def d_bcra():
    mes = {}
    for c, idv in BCRA_FLUJO.items():
        acum = {}
        for f, v in bcra(idv):
            acum[f[:7]] = acum.get(f[:7], 0) + v
        mes[c] = cerrados(acum)
    for c, idv in BCRA_STOCK.items():
        ult = {}
        for f, v in bcra(idv):
            ult[f[:7]] = v
        mes[c] = cerrados(ult)
    grupos = {}
    for f, v in bcra(5):
        grupos.setdefault(f[:7], []).append(v)
    mes["tc_ref"] = cerrados({m: sum(v) / len(v) for m, v in grupos.items()})
    guardar("bcra_mensual.csv", ["mes", *mes], a_filas(mes, "mes"))


def d_demanda():
    d = api(SERIES_DEMANDA)
    trim = {c: {f"{m[:4]}-T{(int(m[5:]) + 2) // 3}": v for m, v in s.items()} for c, s in d.items()}
    guardar("demanda_trimestral.csv", ["trimestre", *trim], a_filas(trim, "trimestre"))


def d_actividad():
    d = api(SERIES_ACTIVIDAD)
    guardar("actividad_mensual.csv", ["mes", *d], a_filas(d, "mes"))


def d_global():
    glob = {c: cerrados(fred(s)) for c, s in FRED.items()}
    glob.update({c: cerrados(bcb(s)) for c, s in BCB.items()})
    guardar("global_mensual.csv", ["mes", *glob], a_filas(glob, "mes"))


def d_credito():
    cred = {}
    for f, v in bcra(26):
        cred[f[:7]] = v
    guardar("credito_mensual.csv", ["mes", "prestamos_priv"], a_filas({"prestamos_priv": cerrados(cred)}, "mes"))


def d_curva():
    letras = json.loads(bajar(LETRAS_URL))
    fecha = letras["fechaActualizacion"][:10]
    guardar("curva_pesos.csv", ["ticker", "vencimiento", "dias", "tem", "tea", "precio", "fecha"],
            [{"ticker": x["ticker"], "vencimiento": x["fechaVencimiento"], "dias": x["diasAlVencimiento"], "tem": x["temPorcentaje"], "tea": x["teaPorcentaje"],
              "precio": x["precioArs"], "fecha": fecha} for x in sorted(letras["letras"], key=lambda y: y["diasAlVencimiento"])])


def d_itcrm():
    import construir
    construir.bajar_itcrm()


# Etapa 4: fuentes de INDEC que la API de datos.gob.ar publica con atraso.
INDEC = "https://www.indec.gob.ar/ftp/cuadros"
MESES_LARGOS = {n: i + 1 for i, n in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"])}


def xls(contenido):
    """Planilla .xls de INDEC (formato viejo de Excel): necesita xlrd."""
    import xlrd
    return xlrd.open_workbook(file_contents=contenido)


def d_emae():
    """EMAE mensual: serie original, variación interanual publicada y desestacionalizada."""
    h = xls(bajar(f"{INDEC}/economia/sh_emae_mensual_base2004.xls")).sheet_by_index(0)
    cab = " ".join(str(h.cell_value(2, c)) for c in range(h.ncols)).lower()
    if "original" not in cab or "desestacionalizada" not in cab:
        sys.exit(f"EMAE: cambió el formato de la planilla: {cab[:200]}")
    filas, anio = [], None
    for r in range(h.nrows):
        a, mes = h.cell_value(r, 0), str(h.cell_value(r, 1)).strip().lower()
        if isinstance(a, float) and a > 1990:
            anio = int(a)
        m = re.match(r"[a-z]+", mes)
        if anio and m and m.group() in MESES_LARGOS and isinstance(h.cell_value(r, 2), float):
            filas.append({"mes": f"{anio}-{MESES_LARGOS[m.group()]:02d}", "emae_original": round(h.cell_value(r, 2), 4),
                          "emae_ia": round(h.cell_value(r, 3), 4) if isinstance(h.cell_value(r, 3), float) and anio > 2004 else "",  # 2004 no tiene año previo
                          "emae_desest": round(h.cell_value(r, 4), 4) if isinstance(h.cell_value(r, 4), float) else ""})
    if len(filas) < 200 or filas[0]["mes"] != "2004-01":
        sys.exit(f"EMAE: la planilla trae {len(filas)} meses desde {filas[0]['mes'] if filas else '—'}")
    guardar("emae_mensual.csv", ["mes", "emae_original", "emae_ia", "emae_desest"], filas)
    # Ramas (letras A a O), mismas claves que la tabla de sectores: e00 es el total original.
    h = xls(bajar(f"{INDEC}/economia/sh_emae_actividad_base2004.xls")).sheet_by_index(0)
    if not str(h.cell_value(2, 2)).startswith("A") or not str(h.cell_value(2, 16)).startswith("O"):
        sys.exit("EMAE por rama: cambió el orden de las columnas")
    total = {f["mes"]: f["emae_original"] for f in filas}
    ramas, anio = [], None
    for r in range(h.nrows):
        a, mes = h.cell_value(r, 0), str(h.cell_value(r, 1)).strip().lower()
        if isinstance(a, float) and a > 1990:
            anio = int(a)
        m = re.match(r"[a-z]+", mes)
        if anio and m and m.group() in MESES_LARGOS and isinstance(h.cell_value(r, 2), float):
            clave = f"{anio}-{MESES_LARGOS[m.group()]:02d}"
            ramas.append({"mes": clave, "e00": total.get(clave, ""), **{f"e{i:02d}": round(h.cell_value(r, 1 + i), 3) for i in range(1, 16)}})
    guardar("emae_sectores.csv", ["mes", *[f"e{i:02d}" for i in range(16)]], ramas)


# IPI manufacturero: nivel general (i00), 16 divisiones (i01 a i16) y sus subclases, en el orden de la planilla.
SUBCLASES_IPI = [13, 2, 4, 3, 3, 5, 8, 3, 6, 3, 3, 4, 3, 3, 2, 2]
DIVISIONES_IPI = ["Alimentos", "Productos de tabaco", "Productos textiles", "Prendas", "Madera", "Refinación", "Sustancias", "Productos de caucho", "Productos minerales",
                  "Industrias metálicas", "Productos de metal", "Maquinaria y equipo", "Otros equipos", "Vehículos", "Otro equipo", "Muebles"]


def claves_ipi():
    claves, s = ["i00"], 0
    for d, n in enumerate(SUBCLASES_IPI, start=1):
        claves.append(f"i{d:02d}")
        claves += [f"s{s + j:02d}" for j in range(1, n + 1)]
        s += n
    return claves


def d_ipi():
    # El nombre del archivo lleva el año: se busca en la página del IPI.
    ruta = enlace("https://www.indec.gob.ar/Nivel4/Tema/3/6/14", r"ftp/cuadros/economia/sh_ipi_manufacturero_\d{4}\.xls", "ftp/cuadros/economia/sh_ipi_manufacturero_2026.xls")
    libro_ipi = xls(bajar("https://www.indec.gob.ar/" + ruta))
    h, c1 = libro_ipi.sheet_by_name("Cuadro 2"), libro_ipi.sheet_by_name("Cuadro 1")
    claves = claves_ipi()
    cols = {k: 3 + i for i, k in enumerate(claves)}
    if "IPI" not in str(h.cell_value(3, 3)):
        sys.exit("IPI: la columna 3 ya no es el nivel general")
    for d, nombre in enumerate(DIVISIONES_IPI, start=1):
        if not str(h.cell_value(3, cols[f"i{d:02d}"])).startswith(nombre):
            sys.exit(f"IPI: la división i{d:02d} ya no es «{nombre}»: {h.cell_value(3, cols[f'i{d:02d}'])}")

    def meses(hoja, desde):
        """Filas de datos: el año solo figura en enero (a veces con asterisco)."""
        anio, out = None, {}
        for r in range(desde, hoja.nrows):
            a = re.match(r"\s*(\d{4})", str(hoja.cell_value(r, 1)).replace(".0", ""))
            if a:
                anio = int(a.group(1))
            m = re.match(r"[a-z]+", str(hoja.cell_value(r, 2)).strip().lower())
            if anio and m and m.group() in MESES_LARGOS:
                out[f"{anio}-{MESES_LARGOS[m.group()]:02d}"] = r
        return out

    filas_s = [{"mes": mes, **{k: (round(h.cell_value(r, c), 3) if isinstance(h.cell_value(r, c), float) else "") for k, c in cols.items()}} for mes, r in meses(h, 5).items()]
    if filas_s[0]["mes"] != "2016-01" or len(filas_s) < 100:
        sys.exit(f"IPI: la planilla empieza en {filas_s[0]['mes']} con {len(filas_s)} meses")
    filas_m = [{"mes": mes, "ipi_ia": round(c1.cell_value(r, 4), 6) if isinstance(c1.cell_value(r, 4), float) else "",
                "ipi_desest": round(c1.cell_value(r, 7), 3) if isinstance(c1.cell_value(r, 7), float) else ""} for mes, r in meses(c1, 7).items()]
    guardar("ipi_sectores.csv", ["mes", *claves], filas_s)
    guardar("ipi_mensual.csv", ["mes", "ipi_ia", "ipi_desest"], filas_m)


def d_salarios():
    """Índice de salarios de INDEC (base oct 2016 = 100), en su CSV oficial."""
    texto = bajar(f"{INDEC}/sociedad/indice_salarios.csv").decode("latin-1")
    cols = {"IS_indice_total": "is_total", "IS_sector_privado_registrado": "is_priv_reg", "IS_sector_publico": "is_publico",
            "IS_total_registrado": "is_total_reg", "IS_sector_no_registrado": "is_no_reg"}
    lector = csv.DictReader(io.StringIO(texto), delimiter=";")
    faltan = set(cols) - set(lector.fieldnames or [])
    if faltan:
        sys.exit(f"Salarios: faltan columnas en el CSV de INDEC: {faltan}")
    filas = []
    for r in lector:
        d, m, a = r["periodo"].split("/")
        filas.append({"mes": f"{a}-{int(m):02d}", **{n: ("" if r[c] in ("", "NA") else float(r[c].replace(",", "."))) for c, n in cols.items()}})
    filas.sort(key=lambda x: x["mes"])
    guardar("salarios_mensual.csv", ["mes", *cols.values()], filas)


# Comercio exterior (INDEC, Intercambio comercial argentino).
PAGINA_ICA = "https://www.indec.gob.ar/Nivel4/Tema/3/2/40"
MES3 = {n[:3]: i for n, i in MESES_LARGOS.items()}
PAISES = {"bra": "Brasil", "pry": "Paraguay", "ury": "Uruguay", "ven": "Venezuela", "bol": "Bolivia", "chl": "Chile", "col": "Colombia", "mex": "México", "per": "Perú",
          "ecu": "Ecuador", "can": "Canadá", "usa": "Estados Unidos", "deu": "Alemania", "aut": "Austria", "bel": "Bélgica", "esp": "España", "fra": "Francia", "ita": "Italia",
          "nld": "Países Bajos", "pol": "Polonia", "prt": "Portugal", "gbr": "Reino Unido", "che": "Suiza", "ind": "India", "rus": "Rusia", "chn": "China", "kor": "República de Corea",
          "idn": "Indonesia", "jpn": "Japón", "tha": "Tailandia", "twn": "Taiwán", "vnm": "Viet Nam", "isr": "Israel", "aus": "Australia", "nzl": "Nueva Zelandia", "ago": "Angola",
          "dza": "Argelia", "egy": "Egipto", "mar": "Marruecos", "zaf": "Sudáfrica"}
# Bloques con la misma definición que la v1 (verificada con el acumulado ene-sep 2026).
UE = ["Alemania", "Austria", "Bélgica", "Bulgaria", "Croacia", "Chipre", "Dinamarca", "Eslovaquia", "Eslovenia", "España", "Estonia", "Finlandia", "Francia", "Grecia", "Hungría",
      "Irlanda", "Italia", "Letonia", "Lituania", "Luxemburgo", "Malta", "Países Bajos", "Polonia", "Portugal", "Republica Checa", "Rumania", "Suecia"]
MEDIO_ORIENTE = ["Arabia Saudita", "Bahrein", "Emiratos Árabes Unidos", "Irán", "Iraq", "Israel", "Jordania", "Kuwait", "Líbano", "Omán", "Qatar", "Siria", "Yemen"]
ASIA_PACIFICO = ["China", "Japón", "República de Corea", "Taiwán", "Brunei Darussalam", "Camboya", "Filipinas", "Indonesia", "Malasia", "Myanmar", "Singapur", "Tailandia",
                 "Timor Oriental", "Viet Nam"]
BLOQUES = ["bmcs", "bral", "bnam", "buex", "basp", "bmor", "bafr", "bres"]


def mes_texto(texto):
    """'Septiembree', 'Sep', 'Ene-sep 2026e' (tras el guion) -> número de mes."""
    m = re.match(r"\s*([a-záéíóú]{3})", str(texto).lower())
    return MES3.get(m.group(1)) if m else None


def guardar_preservando(nombre, columnas, nuevas):
    """Agrega o reemplaza filas por mes y conserva las ya guardadas: INDEC solo publica el último mes."""
    previas = {}
    ruta = FUENTES / nombre
    if ruta.exists():
        previas = {r["mes"]: r for r in csv.DictReader(io.StringIO(ruta.read_text(encoding="utf-8")))}
    for f in nuevas:
        previas[f["mes"]] = {c: f.get(c, "") for c in columnas}
    guardar(nombre, columnas, [previas[m] for m in sorted(previas)])


def d_comercio():
    # 1. Totales mensuales desde 1990.
    h = xls(bajar(f"{INDEC}/economia/balanmensual.xls")).sheet_by_index(0)
    if "Exportaciones" not in str(h.cell_value(2, 2)) or "Importaciones" not in str(h.cell_value(2, 7)):
        sys.exit("Comercio: cambió el formato de balanmensual.xls")
    tot, anio = [], None
    for r in range(h.nrows):
        a = re.match(r"(\d{4})", str(h.cell_value(r, 0)))
        anio = int(a.group(1)) if a else anio
        m = mes_texto(h.cell_value(r, 1))
        if anio and m and isinstance(h.cell_value(r, 2), float):
            impo = h.cell_value(r, 7)
            tot.append({"mes": f"{anio}-{m:02d}", "expo": round(h.cell_value(r, 2), 2), "impo": round(impo, 2) if isinstance(impo, float) else ""})
    if tot[0]["mes"] != "1990-01":
        sys.exit(f"Comercio: balanmensual empieza en {tot[0]['mes']}")
    # Los demás archivos cambian de nombre con cada año o publicación: se buscan en la página.
    pagina = bajar(PAGINA_ICA).decode("utf-8", "replace")

    def libro_de(patron):
        m = sorted(set(re.findall(patron, pagina)))
        if not m:
            sys.exit(f"Comercio: no encontré {patron} en la página del ICA")
        return xls(bajar("https://www.indec.gob.ar/" + m[-1]))

    # 2. Grandes rubros y usos, mes a mes en el año en curso y el anterior.
    porm = {}
    for hoja, claves in ((libro_de(r"ftp/cuadros/economia/expo_grandes_rubros_\d{4}_\d{4}\.xls").sheet_by_index(0), ["x00", "x01", "x02", "x03", "x04"]),
                         (libro_de(r"ftp/cuadros/economia/impo_uso_economico_\d{4}_\d{4}\.xls").sheet_by_index(0), ["m00", "m01", "m02", "m03", "m04", "m05", "m06", "m07"])):
        anios = [int(re.search(r"\d{4}", str(hoja.cell_value(3, c))).group()) for c in (2, 3)]
        for r in range(9, hoja.nrows):
            m = mes_texto(hoja.cell_value(r, 1))
            if not m or "total" in str(hoja.cell_value(r, 1)).lower():
                continue
            for k, a in enumerate(anios):
                vals = [hoja.cell_value(r, 2 + 4 * i + k) for i in range(len(claves))]
                if all(isinstance(v, float) for v in vals):
                    porm.setdefault(f"{a}-{m:02d}", {"mes": f"{a}-{m:02d}"}).update({c: round(v, 2) for c, v in zip(claves, vals)})

    # 3. Subrubros de exportación del último mes (informe técnico, cuadro 12).
    c12 = libro_de(r"ftp/cuadros/economia/ica_cuadros_\d{2}_\d{2}_\d{2}\.xls").sheet_by_name("c12")
    anio12 = re.search(r"\d{4}", str(c12.cell_value(3, 3))).group()
    mes12 = f"{anio12}-{mes_texto(c12.cell_value(2, 3)):02d}"
    sub = {"PP": [], "MOA": [], "MOI": [], "CyE": []}
    grupo = None
    for r in range(5, c12.nrows):
        g, s, v = str(c12.cell_value(r, 1)).strip(), str(c12.cell_value(r, 2)).strip(), c12.cell_value(r, 3)
        if g:
            grupo = next((k for k in sub if f"({k})" in g), None)
        elif s and grupo and isinstance(v, float):
            sub[grupo].append(v)
    if [len(sub[k]) for k in sub] != [12, 16, 14, 5]:
        sys.exit(f"Comercio: cambió la lista de subrubros del cuadro 12: {[len(sub[k]) for k in sub]}")
    cye = sub["CyE"]  # crudo, carburantes, lubricantes, gas, resto
    # xd44 suma carburantes y lubricantes, como la v1; xd46 (energía eléctrica) ya no se publica aparte.
    xd = sub["PP"] + sub["MOA"] + sub["MOI"] + [cye[0], cye[1] + cye[2], cye[3], None, cye[4]]
    porm.setdefault(mes12, {"mes": mes12}).update({f"xd{i:02d}": ("" if v is None else round(v, 2)) for i, v in enumerate(xd, start=1)})
    cols_r = ["mes", "x00", "x01", "x02", "x03", "x04", *[f"xd{i:02d}" for i in range(1, 48)], "m00", "m01", "m02", "m03", "m04", "m05", "m06", "m07"]
    guardar_preservando("comercio_rubros.csv", cols_r, porm.values())

    # 4. Países y bloques: acumulado del año menos la foto del mes anterior.
    h = libro_de(r"ftp/cuadros/economia/balan_continentes_paises_\d{4}_\d{4}\.xls").sheet_by_index(0)
    enc = str(h.cell_value(4, 2))
    a, m = int(re.search(r"\d{4}", enc).group()), mes_texto(enc.split("-")[-1])
    if "Exportaciones" not in str(h.cell_value(3, 2)) or "Importaciones" not in str(h.cell_value(3, 6)) or not m:
        sys.exit(f"Comercio por país: cambió el formato: {enc}")
    filas = {}
    for r in range(h.nrows):
        n = str(h.cell_value(r, 1)).replace("\xa0", " ").strip()
        if n and n not in filas:  # la primera fila de cada país incluye sus zonas francas y territorios
            filas[n] = r
    faltan = [n for n in [*PAISES.values(), *UE, *MEDIO_ORIENTE, *ASIA_PACIFICO, "Total", "Total de América", "Total de África"] if n not in filas]
    if faltan:
        sys.exit(f"Comercio por país: faltan filas {faltan}")

    def valor(nombre, col):
        x = h.cell_value(filas[nombre], col)
        return x / 1000 if isinstance(x, float) else 0.0  # «s» (secreto) y «-» cuentan como cero

    acum = {}
    for fl, col in (("x", 2), ("m", 6)):
        for k, n in PAISES.items():
            acum[f"{fl}_{k}"] = valor(n, col)
        acum[f"{fl}_tot"] = valor("Total", col)
        acum[f"{fl}_bmcs"] = sum(acum[f"{fl}_{k}"] for k in ("bra", "pry", "ury", "ven"))
        acum[f"{fl}_bnam"] = acum[f"{fl}_usa"] + acum[f"{fl}_can"]
        acum[f"{fl}_bral"] = valor("Total de América", col) - acum[f"{fl}_bmcs"] - acum[f"{fl}_bnam"]
        acum[f"{fl}_buex"] = sum(valor(n, col) for n in UE)
        acum[f"{fl}_basp"] = sum(valor(n, col) for n in ASIA_PACIFICO)
        acum[f"{fl}_bmor"] = sum(valor(n, col) for n in MEDIO_ORIENTE)
        acum[f"{fl}_bafr"] = valor("Total de África", col)
        acum[f"{fl}_bres"] = acum[f"{fl}_tot"] - sum(acum[f"{fl}_{b}"] for b in BLOQUES[:-1])
    periodo = f"{a}-{m:02d}"
    ruta_foto = FUENTES / "comercio_paises_acum.csv"
    foto = {r["clave"]: r for r in csv.DictReader(io.StringIO(ruta_foto.read_text(encoding="utf-8")))} if ruta_foto.exists() else {}
    previo = next(iter(foto.values()), {}).get("periodo")
    nuevas = []
    if m == 1:
        nuevas.append({"mes": periodo, **{k: round(v, 2) for k, v in acum.items()}})
    elif previo == f"{a}-{m - 1:02d}":
        nuevas.append({"mes": periodo, **{k: round(v - float(foto[k]["valor"]), 2) + 0.0 for k, v in acum.items()}})
    elif previo != periodo:
        print(f"AVISO: comercio por país: la foto guardada es de {previo} y el acumulado llega a {periodo}; ese mes queda sin desglose")
    claves = ["mes"] + [f"{fl}_{k}" for fl in ("x", "m") for k in ["tot", *PAISES, *BLOQUES]]
    guardar_preservando("comercio_paises.csv", claves, nuevas)
    if previo != periodo:
        guardar("comercio_paises_acum.csv", ["periodo", "clave", "valor"], [{"periodo": periodo, "clave": k, "valor": round(v, 4)} for k, v in acum.items()])
    # Los totales van al final: si algo falla antes, la fuente sigue vencida y se reintenta al otro día.
    guardar("comercio_mensual.csv", ["mes", "expo", "impo"], tot)

FUENTES_POR_ID = {"diario": d_diario, "mercado": d_mercado, "precios": d_precios, "curva": d_curva, "bcra": d_bcra, "credito": d_credito, "itcrm": d_itcrm, "global": d_global, "deuda_mensual": d_deuda_mensual, "fiscal": d_fiscal,
                  "series_mensuales": d_series_mensuales, "actividad": d_actividad, "series_trimestrales": d_series_trimestrales, "demanda": d_demanda, "deuda_trim": d_deuda_trim,
                  "emae": d_emae, "salarios": d_salarios, "ipi": d_ipi, "comercio": d_comercio}


def main():
    FUENTES.mkdir(parents=True, exist_ok=True)
    elegidas = sys.argv[1:] or list(FUENTES_POR_ID)
    for f in elegidas:
        FUENTES_POR_ID[f]()


if __name__ == "__main__":
    main()
