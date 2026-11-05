"""Baja las fuentes de la etapa 2 y las guarda en pipeline/fuentes/.

    python pipeline/descargar.py

Las URL de la Secretaría de Finanzas cambian con cada publicación: al actualizar,
hay que renovar DEUDA_MENSUAL_URL y DEUDA_TRIM_URL con los enlaces de
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
BCRA_STOCK = {"base_monetaria": 15, "dep_usd_priv": 108, "prest_usd_priv": 125, "pases_pasivos": 152, "leliq": 155, "lebac_bopreal": 158}


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


def deuda_mensual():
    h = libro(bajar(DEUDA_MENSUAL_URL))
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
    h = libro(bajar(DEUDA_TRIM_URL))
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
    return anual, perfil, resumen


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


def main():
    FUENTES.mkdir(parents=True, exist_ok=True)
    d = api(SERIES_FISCAL)
    guardar("fiscal_mensual.csv", ["mes", *d], a_filas(d, "mes"))

    d = api(SERIES_MES)
    guardar("series_mensuales.csv", ["mes", *d], a_filas(d, "mes"))

    d = api(SERIES_TRIM)
    trim = {c: {f"{m[:4]}-T{(int(m[5:]) + 2) // 3}": v for m, v in s.items()} for c, s in d.items()}
    guardar("series_trimestrales.csv", ["trimestre", *trim], a_filas(trim, "trimestre"))

    d = deuda_mensual()
    guardar("deuda_mensual.csv", ["mes", *d], a_filas(d, "mes"))
    anual, perfil, resumen = deuda_trimestral()
    guardar("deuda_anual.csv", ["anio", *anual], a_filas(anual, "anio"))
    guardar("deuda_perfil.csv", ["anio", "capital", "interes", "total"], perfil)
    guardar("deuda_resumen.csv", ["indicador", "valor"], [{"indicador": k, "valor": round(v, 3)} for k, v in resumen.items()])

    mes = {}
    for c, idv in BCRA_FLUJO.items():
        acum = {}
        for f, v in bcra(idv):
            acum[f[:7]] = acum.get(f[:7], 0) + v
        mes[c] = acum
    for c, idv in BCRA_STOCK.items():
        ult = {}
        for f, v in bcra(idv):
            ult[f[:7]] = v
        mes[c] = ult
    guardar("bcra_mensual.csv", ["mes", *mes], a_filas(mes, "mes"))


if __name__ == "__main__":
    main()
