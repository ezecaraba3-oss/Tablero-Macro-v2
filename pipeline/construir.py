"""Construye assets/datos.js de la v2 a partir de la base congelada de la v1.

Uso:
    python pipeline/construir.py                     usa el ITCRM guardado en pipeline/fuentes
    python pipeline/construir.py --actualizar-itcrm  vuelve a bajar el ITCRM del BCRA

Cada corrección está explicada en CORRECCIONES.md.
"""
import argparse
import csv
import datetime as dt
import io
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendario as cal  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
BASE = RAIZ / "pipeline" / "base" / "datos_v1.js"
ITCRM_CSV = RAIZ / "pipeline" / "fuentes" / "itcrm_mensual.csv"
SALIDA = RAIZ / "assets" / "datos.js"
ITCRM_URL = "https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/itcrm-serie.xlsx"
ITCRM_COLS = {"itcrm": "ITCRM", "itcrb_bra": "ITCRB Brasil", "itcrb_usa": "ITCRB Estados Unidos",
              "itcrb_chn": "ITCRB China", "itcrb_eur": "ITCRB Zona Euro"}
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def leer_datos(ruta):
    raw = ruta.read_text(encoding="utf-8")
    ini = raw.index("{", raw.index("window.DATOS"))
    obj, fin = json.JSONDecoder().raw_decode(raw[ini:])
    return raw[:ini], obj, raw[ini + fin:]


def leer_tabla(texto):
    lector = csv.DictReader(io.StringIO(texto))
    filas = list(lector)
    return list(lector.fieldnames), filas


def escribir_tabla(columnas, filas):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columnas, lineterminator="\n")
    w.writeheader()
    w.writerows(filas)
    return buf.getvalue().rstrip("\n")


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fmt(x, dec=4):
    if x is None:
        return ""
    texto = f"{round(x, dec):.{dec}f}"
    # Solo se quitan ceros decimales: en un entero, «130000» debe seguir siendo 130000.
    return texto.rstrip("0").rstrip(".") if "." in texto else texto


def mover_mes(mes, n):
    y, m = map(int, mes.split("-"))
    t = y * 12 + m - 1 + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def bajar_itcrm():
    pedido = urllib.request.Request(ITCRM_URL, headers={"User-Agent": "tablero-macro-v2/1.0"})
    with urllib.request.urlopen(pedido, timeout=120) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    textos = ["".join(t.text or "" for t in si.iter("{%s}t" % ns["m"]))
              for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
    filas = []
    for fila in ET.fromstring(z.read("xl/worksheets/sheet2.xml")).find("m:sheetData", ns):
        v = []
        for c in fila:
            e = c.find("m:v", ns)
            t = e.text if e is not None else ""
            v.append(textos[int(t)] if c.get("t") == "s" and t else t)
        filas.append(v)
    cab = [c.strip() for c in filas[1]]
    idx = {col: cab.index(nombre) for col, nombre in ITCRM_COLS.items()}
    salida = []
    for f in filas[2:]:
        if not (f and re.fullmatch(r"\d{5}(\.0)?", f[0] or "")):
            continue
        fecha = dt.date(1899, 12, 30) + dt.timedelta(days=int(float(f[0])))
        salida.append({"mes": fecha.strftime("%Y-%m"), **{c: fmt(num(f[i]), 3) for c, i in idx.items()}})
    actual = dt.date.today().strftime("%Y-%m")
    salida = [r for r in salida if r["mes"] < actual]
    meses = [r["mes"] for r in salida]
    if len(meses) != len(set(meses)):
        sys.exit("ITCRM: hay meses repetidos; revisar el archivo del BCRA")
    ITCRM_CSV.parent.mkdir(parents=True, exist_ok=True)
    ITCRM_CSV.write_text(escribir_tabla(["mes", *ITCRM_COLS], salida) + "\n", encoding="utf-8", newline="\n")
    print(f"ITCRM actualizado: {meses[0]}..{meses[-1]}")


def corregir_comercio_rubros(obj):
    """x00 y x01 traen valores repetidos en la fuente (jun y ago 2026)."""
    cols, filas = leer_tabla(obj["comercio_rubros"])
    _, paises = leer_tabla(obj["comercio_paises"])
    _, meta = leer_tabla(obj["comercio_meta"])
    x_tot = {r["mes"]: r["x_tot"] for r in paises}
    hijos_x01 = [r["clave"] for r in meta if r["padre"] == "x01"]
    for r in filas:
        if r["mes"] in ("2026-06", "2026-08"):
            r["x00"] = x_tot[r["mes"]]
        if r["mes"] == "2026-08":
            r["x01"] = fmt(sum(num(r[h]) or 0 for h in hijos_x01), 2)
    obj["comercio_rubros"] = escribir_tabla(cols, filas)


def quitar_s68(obj):
    """La subclase s68 no tiene datos en el catálogo oficial y era una copia del IPI general."""
    cols, filas = leer_tabla(obj["sectores"])
    cols.remove("s68")
    for r in filas:
        del r["s68"]
    obj["sectores"] = escribir_tabla(cols, filas)
    cols, filas = leer_tabla(obj["sectores_meta"])
    obj["sectores_meta"] = escribir_tabla(cols, [r for r in filas if r["clave"] != "s68"])


def recalcular_comercio(M, mes):
    r = M[mes]
    ventana = [mover_mes(mes, -i) for i in range(12)]
    previa = [mover_mes(mes, -12 - i) for i in range(12)]
    e12 = sum(num(M[m]["expo"]) for m in ventana)
    i12 = sum(num(M[m]["impo"]) for m in ventana)
    r["saldo_neto"] = fmt(num(r["expo"]) - num(r["impo"]), 1)
    r["expo_12m"], r["impo_12m"] = fmt(e12, 1), fmt(i12, 1)
    r["saldo_12m"] = r["saldo_neto_12m"] = fmt(e12 - i12, 1)
    r["cobertura_12m"] = fmt(e12 / i12 * 100, 3)
    r["expo_ia_12m"] = fmt((e12 / sum(num(M[m]["expo"]) for m in previa) - 1) * 100)
    r["impo_ia_12m"] = fmt((i12 / sum(num(M[m]["impo"]) for m in previa) - 1) * 100)


def actualizar_mensual(obj):
    cols, filas = leer_tabla(obj["mensual"])
    M = {r["mes"]: r for r in filas}
    _, paises = leer_tabla(obj["comercio_paises"])
    P = {r["mes"]: r for r in paises}

    # Comercio: desde agosto de 2026 (revisado en la v1) toma los totales de comercio_paises.
    for mes in sorted(m for m in P if m >= "2026-08" and m in M and num(P[m]["x_tot"]) is not None):
        M[mes]["expo"] = fmt(num(P[mes]["x_tot"]), 1)
        M[mes]["impo"] = fmt(num(P[mes]["m_tot"]), 1)
        recalcular_comercio(M, mes)

    # Inflación mensual de ene y feb 2017: se alinea con el IPC nacional.
    for mes, valor in (("2017-01", 1.6), ("2017-02", 2.1)):
        M[mes]["infl_mensual"] = fmt(valor, 1)
        M[mes]["tasa_real_pf_m"] = fmt(((1 + num(M[mes]["tem_pf"]) / 100) / (1 + valor / 100) - 1) * 100, 6)

    # Tasa real de préstamos: ex post a 12 meses y ex ante con REM.
    cols.append("tasa_real_personales_exante")
    for mes, r in M.items():
        tem = {m: num(M[m]["tasa_personales"]) if m in M else None for m in [mover_mes(mes, -i) for i in range(12)]}
        ia = num(r["infl_ia"])
        r["tasa_real_personales"] = ""
        if ia is not None and all(v is not None for v in tem.values()):
            acum = 1.0
            for v in tem.values():
                acum *= 1 + v * 30 / 365 / 100
            r["tasa_real_personales"] = fmt((acum / (1 + ia / 100) - 1) * 100)
        tna, rem = num(r["tasa_personales"]), num(r["rem_12m"])
        r["tasa_real_personales_exante"] = ""
        if tna is not None and rem is not None:
            tea = (1 + tna * 30 / 365 / 100) ** (365 / 30)
            r["tasa_real_personales_exante"] = fmt((tea / (1 + rem / 100) - 1) * 100)

    # ITCRM oficial.
    icols, ifilas = leer_tabla(ITCRM_CSV.read_text(encoding="utf-8"))
    I = {r["mes"]: r for r in ifilas}
    nuevas = [c for c in icols if c != "mes"]
    cols.extend(nuevas)
    for mes, r in M.items():
        for c in nuevas:
            r[c] = I.get(mes, {}).get(c, "")
    obj["mensual"] = escribir_tabla(cols, filas)
    return M


def actualizar_inv_mensual(obj, M):
    cols, filas = leer_tabla(obj["inv_mensual"])
    D = {r["mes"]: r for r in filas}
    for mes in sorted(m for m in D if m >= "2026-08" and num(M.get(m, {}).get("impo")) is not None and num(D[m]["der_imp"]) is not None and num(D[m]["tc"]) is not None):
        r = D[mes]
        r["impo"] = M[mes]["impo"]
        r["ar_efec"] = fmt(num(r["der_imp"]) / (num(r["impo"]) * num(r["tc"])) * 100)
        ventana = [mover_mes(mes, -i) for i in range(12)]
        pesos = sum(num(D[m]["der_imp"]) for m in ventana)
        base = sum(num(D[m]["impo"]) * num(D[m]["tc"]) for m in ventana)
        r["ar_efec_12m"] = fmt(pesos / base * 100)
    obj["inv_mensual"] = escribir_tabla(cols, filas)


def actualizar_comercio_anual(obj, M):
    cols, filas = leer_tabla(obj["comercio_anual"])
    A = {r["anio"]: r for r in filas}
    ultimo = max(m for m, r in M.items() if num(r["expo"]) is not None and num(r["impo"]) is not None)
    anio = ultimo[:4]
    if anio not in A:
        A[anio] = {**{c: "" for c in cols}, "anio": anio}
        filas.insert(0, A[anio]) if filas[0]["anio"] > filas[-1]["anio"] else filas.append(A[anio])
    meses = [f"{anio}-{i:02d}" for i in range(1, int(ultimo[5:]) + 1)]
    e = sum(num(M[m]["expo"]) for m in meses)
    i = sum(num(M[m]["impo"]) for m in meses)
    r = A[anio]
    r.update(expo=fmt(e, 1), impo=fmt(i, 1), saldo=fmt(e - i, 1), cobertura=fmt(e / i * 100, 1), meses=str(len(meses)),
             periodo="año completo" if len(meses) == 12 else f"ene–{MESES[len(meses) - 1]} (parcial)")
    previo = A.get(str(int(anio) - 1))
    if len(meses) == 12 and previo and num(previo["expo"]) and num(previo["impo"]):
        r.update(var_expo=fmt((e / num(previo["expo"]) - 1) * 100, 1), var_impo=fmt((i / num(previo["impo"]) - 1) * 100, 1))
    obj["comercio_anual"] = escribir_tabla(cols, filas)


def actualizar_ultimos(obj, M):
    cols, filas = leer_tabla(obj["ultimos"])
    mes = max(m for m, r in M.items() if num(r["expo"]) is not None and num(r["impo"]) is not None)
    previo = mover_mes(mes, -12)
    txt = f"{MESES[int(mes[5:]) - 1]} {mes[:4]}"
    nuevos = {
        "saldo_m": ("saldo_neto", lambda a, b: a - b, 1),
        "saldo_12m": ("saldo_neto_12m", lambda a, b: a - b, 1),
        "expo_12m": ("expo_12m", lambda a, b: (a / b - 1) * 100, 2),
        "impo_12m": ("impo_12m", lambda a, b: (a / b - 1) * 100, 2),
        "cobertura": ("cobertura_12m", None, 2),
    }
    for r in filas:
        if r["id"] in nuevos:
            c, var, dec = nuevos[r["id"]]
            a = num(M[mes][c])
            r["valor"] = fmt(a, 2 if r["id"] == "cobertura" else 1)
            r["periodo"], r["periodo_txt"] = mes, txt
            if var:
                r["variacion"] = fmt(var(a, num(M[previo][c])), dec)
    obj["ultimos"] = escribir_tabla(cols, filas)


def leer_fuente(nombre):
    return leer_tabla((RAIZ / "pipeline" / "fuentes" / nombre).read_text(encoding="utf-8"))


def trimestre_de(mes):
    return f"{mes[:4]}-T{(int(mes[5:]) + 2) // 3}"


def suma_12m(serie, mes):
    valores = [serie.get(mover_mes(mes, -i)) for i in range(12)]
    return None if any(v is None for v in valores) else sum(valores)


def pib_nominal(inv):
    """PIB nominal de inv_trim, ampliado con los trimestres nuevos de la fuente de demanda."""
    pib = {r["trimestre"]: num(r["pib_n"]) for r in inv}
    ruta = RAIZ / "pipeline" / "fuentes" / "demanda_trimestral.csv"
    if ruta.exists():
        cols, filas = leer_tabla(ruta.read_text(encoding="utf-8"))
        if "pib_n" in cols:
            for r in filas:
                if r["trimestre"] not in pib and num(r["pib_n"]) is not None:
                    pib[r["trimestre"]] = num(r["pib_n"])
    return pib


def extender_filas(obj):
    """Suma filas para los períodos nuevos. Las series que no tienen ese dato quedan vacías."""
    meses = set()
    for archivo in ("deuda_mensual.csv", "bcra_mensual.csv", "series_mensuales.csv", "fiscal_mensual.csv", "actividad_mensual.csv", "global_mensual.csv", "credito_mensual.csv", "itcrm_mensual.csv", "mercado_mensual.csv", "precios_mensual.csv", "emae_mensual.csv", "salarios_mensual.csv", "ipi_mensual.csv", "comercio_mensual.csv", "recaudacion_mensual.csv"):
        meses |= {r["mes"] for r in leer_fuente(archivo)[1]}
    cols, filas = leer_tabla(obj["mensual"])
    ultimo = filas[-1]["mes"]
    mes = mover_mes(ultimo, 1)
    tope = max(meses)
    while mes <= tope:
        filas.append({**{c: "" for c in cols}, "mes": mes})
        mes = mover_mes(mes, 1)
    obj["mensual"] = escribir_tabla(cols, filas)
    trimestres = set()
    for archivo in ("series_trimestrales.csv", "demanda_trimestral.csv", "eph_trimestral.csv"):
        trimestres |= {r["trimestre"] for r in leer_fuente(archivo)[1]}
    cols, filas = leer_tabla(obj["trimestral"])
    existentes = {r["trimestre"] for r in filas}
    for t in sorted(trimestres - existentes):
        filas.append({**{c: "" for c in cols}, "trimestre": t, "trim_inicio": f"{t[:4]}-{(int(t[-1]) - 1) * 3 + 1:02d}"})
    obj["trimestral"] = escribir_tabla(cols, filas)
    cols, filas = leer_tabla(obj["anual"])
    existentes = {r["anio"] for r in filas}
    for a in sorted({r["anio"] for r in leer_fuente("deuda_anual.csv")[1]} - existentes):
        filas.append({**{c: "" for c in cols}, "anio": a, "fecha": f"{a}-07"})
    obj["anual"] = escribir_tabla(cols, filas)


def aplicar_mercado(obj):
    """Cierra los meses con el dato completo y deriva las columnas con el método de la v1."""
    cols, filas = leer_tabla(obj["mensual"])
    M = {r["mes"]: r for r in filas}
    _, mf = leer_fuente("mercado_mensual.csv")
    for f in mf:
        r = M.get(f["mes"])
        if r is None:
            continue
        for c in ("tc_a3500", "reservas", "badlar", "tasa_pf30", "tasa_personales", "banda_inf", "banda_sup", "dolar_blue", "dolar_ccl", "riesgo_pais"):
            if num(f[c]) is not None:
                r[c] = fmt(num(f[c]), 3)
        tc = num(f["tc_a3500"])
        if tc is None:
            continue
        for col, base in (("tc_m", 1), ("tc_ia", 12)):
            prev = num(M[mover_mes(f["mes"], -base)]["tc_a3500"])
            r[col] = fmt((tc / prev - 1) * 100, 4)
        for col, origen in (("brecha_ccl", "dolar_ccl"), ("brecha_mep", "dolar_mep"), ("brecha_blue", "dolar_blue")):
            if num(f[origen]) is not None:
                r[col] = fmt((num(f[origen]) / tc - 1) * 100, 4)
        if num(f["tasa_pf30"]) is not None:
            r["tem_pf"] = fmt(num(f["tasa_pf30"]) * 30 / 365, 5)
            ant = M[mover_mes(f["mes"], -1)]
            if r["pf_index"] == "":  # depende del mes anterior: un valor ya cerrado no cambia
                r["pf_index"] = fmt(num(ant["pf_index"]) * (1 + num(ant["tem_pf"]) / 100), 3)
        if num(f["banda_sup"]) is not None:
            r["dist_techo"] = fmt((num(f["banda_sup"]) / tc - 1) * 100, 4)
            r["dist_piso"] = fmt((tc / num(f["banda_inf"]) - 1) * 100, 4)
    # Inflación: encadena el índice y actualiza lo que depende de él.
    _, pf = leer_fuente("precios_mensual.csv")
    for f in pf:
        r = M.get(f["mes"])
        if r is None or r["ipc_index"] != "":
            continue
        infl = num(f["infl_mensual"])
        if infl is None:
            continue
        prev = M[mover_mes(f["mes"], -1)]
        r["infl_mensual"] = fmt(infl, 1)
        r["infl_ia"] = fmt(num(f["infl_ia"]), 1)
        r["ipc_index"] = fmt(num(prev["ipc_index"]) * (1 + infl / 100), 3)
        if num(f["rem_12m"]) is not None:
            r["rem_12m"] = fmt(num(f["rem_12m"]), 1)
        atras = M.get(mover_mes(f["mes"], -12))
        if atras is not None:
            atras["infl_12m_despues"] = fmt(num(f["infl_ia"]), 1)
        tem = num(r["tem_pf"])
        if tem is not None:
            r["tasa_real_pf_m"] = fmt(((1 + tem / 100) / (1 + infl / 100) - 1) * 100, 6)
            if num(r["rem_12m"]) is not None:
                r["tasa_real_pf_exante"] = fmt(((1 + tem / 100) ** (365 / 30) / (1 + num(r["rem_12m"]) / 100) - 1) * 100, 4)
    ultimo_ipc = max(m for m, r in M.items() if num(r["ipc_index"]) is not None)
    if ultimo_ipc > "2026-09":
        ipc_u = num(M[ultimo_ipc]["ipc_index"])
        ref = M["2026-09"]
        k = num(ref["tc_real_index"]) / (num(ref["tc_a3500"]) / num(ref["ipc_index"]))
        for r in filas:
            i, t = num(r["ipc_index"]), num(r["tc_a3500"])
            if i and t:
                r["tc_pesos_hoy"] = fmt(t * ipc_u / i, 2)
                if r["mes"] > "2026-09":
                    r["tc_real_index"] = fmt(t / i * k, 3)
    obj["mensual"] = escribir_tabla(cols, filas)


def aplicar_indec_mensual(obj):
    """EMAE y salarios de INDEC: completa solo los meses vacíos, sin pisar la serie de la v1."""
    cols, filas = leer_tabla(obj["mensual"])
    M = {r["mes"]: r for r in filas}
    # Solo se agregan meses posteriores al último dato de la v1: los huecos viejos quedan como estaban.
    desde = {c: ultimo_con(M, c) for c in ("emae_desest", "emae_ia", "sal_ia", "sal_priv_ia", "sal_real", "sal_priv_real", "sal_pub_real")}
    _, ef = leer_fuente("emae_mensual.csv")
    for f in ef:
        r = M.get(f["mes"])
        if r is None:
            continue
        for c in ("emae_desest", "emae_ia"):
            if f["mes"] > desde[c] and num(f[c]) is not None:
                r[c] = fmt(num(f[c]), 6 if c == "emae_ia" else 3)
    # Salario real: el mismo índice de la v1, encadenado desde su último mes con el índice nominal y el IPC.
    _, sf = leer_fuente("salarios_mensual.csv")
    S = {f["mes"]: f for f in sf}
    reales = {"sal_real": "is_total", "sal_priv_real": "is_priv_reg", "sal_pub_real": "is_publico"}
    factor = {}
    for c, nominal in reales.items():
        ref = max(m for m, r in M.items() if num(r[c]) is not None and m in S and num(S[m][nominal]) and num(r["ipc_index"]))
        factor[c] = num(M[ref][c]) / (num(S[ref][nominal]) / num(M[ref]["ipc_index"]))
    for mes, f in S.items():
        r = M.get(mes)
        if r is None:
            continue
        hace_un_anio = S.get(mover_mes(mes, -12), {})
        for c, nominal in (("sal_ia", "is_total"), ("sal_priv_ia", "is_priv_reg")):
            a, b = num(f[nominal]), num(hace_un_anio.get(nominal))
            if mes > desde[c] and a and b:
                r[c] = fmt((a / b - 1) * 100)
        ipc = num(r["ipc_index"])
        for c, nominal in reales.items():
            if mes > desde[c] and ipc and num(f[nominal]):
                r[c] = fmt(num(f[nominal]) / ipc * factor[c])
    obj["mensual"] = escribir_tabla(cols, filas)
    # Trimestres completos: promedio de sus tres meses, como en la v1.
    tcols, tfilas = leer_tabla(obj["trimestral"])
    for t in tfilas:
        if "-T" not in t["trimestre"]:
            continue
        meses = [mover_mes(t["trim_inicio"], i) for i in range(3)]
        for c, dec in (("emae_ia", 3), ("sal_real", 3)):
            v = [num(M.get(m, {}).get(c)) for m in meses]
            if t[c] == "" and all(x is not None for x in v):
                t[c] = fmt(sum(v) / 3, dec)
    obj["trimestral"] = escribir_tabla(tcols, tfilas)


def aplicar_indec_sectores(obj):
    """EMAE por rama e IPI: suma los meses nuevos sin pisar la historia de la v1 (que no se revisa)."""
    cols, filas = leer_tabla(obj["sectores"])
    S = {r["mes"]: r for r in filas}
    desde = {c: ultimo_con(S, c) for c in cols[1:]}
    fuentes = [leer_fuente("emae_sectores.csv")[1], leer_fuente("ipi_sectores.csv")[1]]
    for mes in sorted({f["mes"] for fs in fuentes for f in fs} - set(S)):
        if mes > filas[-1]["mes"]:
            S[mes] = {**{c: "" for c in cols}, "mes": mes}
            filas.append(S[mes])
    for fs in fuentes:
        for f in fs:
            r = S.get(f["mes"])
            for c, v in f.items():
                if r is not None and c in desde and f["mes"] > desde[c] and num(v) is not None:
                    r[c] = fmt(num(v), 3)
    obj["sectores"] = escribir_tabla(cols, filas)
    # IPI en la tabla mensual: nivel desestacionalizado y variación interanual.
    cols, filas = leer_tabla(obj["mensual"])
    M = {r["mes"]: r for r in filas}
    desde = {c: ultimo_con(M, c) for c in ("ipi_ia", "ipi_desest")}
    for f in leer_fuente("ipi_mensual.csv")[1]:
        r = M.get(f["mes"])
        for c in desde:
            if r is not None and f["mes"] > desde[c] and num(f[c]) is not None:
                r[c] = fmt(num(f[c]), 6 if c == "ipi_ia" else 3)
    obj["mensual"] = escribir_tabla(cols, filas)


# Socios sin serie comparable con la v1 (ver CORRECCIONES.md): sus meses nuevos quedan vacíos.
SOCIOS_SIN_EMPALME = ("gbr", "bral", "bmor", "bres")


def aplicar_comercio(obj):
    """Comercio exterior de INDEC: suma los meses posteriores a la v1 en las tablas por socio y por rubro."""
    _, tf = leer_fuente("comercio_mensual.csv")
    T = {f["mes"]: f for f in tf}
    for tabla, fuente, tot in (("comercio_paises", "comercio_paises.csv", ("x_tot", "m_tot")), ("comercio_rubros", "comercio_rubros.csv", ("x00", "m00"))):
        cols, filas = leer_tabla(obj[tabla])
        F = {f["mes"]: f for f in leer_fuente(fuente)[1]}
        ultimo = filas[-1]["mes"]
        for mes in sorted(m for m in T if m > ultimo):
            r = {**{c: "" for c in cols}, "mes": mes, tot[0]: fmt(num(T[mes]["expo"]), 2), tot[1]: fmt(num(T[mes]["impo"]), 2)}
            for c in cols:
                if c in ("mes", *tot) or c.split("_")[-1] in SOCIOS_SIN_EMPALME:
                    continue
                if num(F.get(mes, {}).get(c)) is not None:
                    r[c] = fmt(num(F[mes][c]), 2)
            filas.append(r)
        obj[tabla] = escribir_tabla(cols, filas)


def aplicar_consumo(obj):
    """Ventas por rubro de INDEC: suma los meses posteriores a la v1 sin pisar su historia."""
    cols, filas = leer_tabla(obj["consumo_rubros"])
    C = {r["mes"]: r for r in filas}
    _, mf = leer_tabla(obj["mensual"])
    ipc = {r["mes"]: num(r["ipc_index"]) for r in mf}
    F = {f["mes"]: f for f in leer_fuente("consumo_rubros.csv")[1]}
    desde = {c: ultimo_con(C, c) for c in cols[1:]}
    # Shoppings a precios constantes: el índice de INDEC escalado como en la v1.
    ref = max(m for m in C if num(C[m]["sh_real"]) and num(F.get(m, {}).get("sh_indice_real")))
    k_shop = num(C[ref]["sh_real"]) / num(F[ref]["sh_indice_real"])
    for mes in sorted(m for m in F if m > filas[-1]["mes"]):
        C[mes] = {**{c: "" for c in cols}, "mes": mes}
        filas.append(C[mes])
    for mes, f in F.items():
        r = C.get(mes)
        if r is None:
            continue
        for c in cols[1:]:
            if mes <= desde[c]:
                continue
            if c == "ipc":
                v = ipc.get(mes)
            elif c == "sh_real":
                v = num(f["sh_indice_real"]) * k_shop if num(f["sh_indice_real"]) is not None else None
            else:
                v = num(f.get(c))
            if v is not None:
                r[c] = fmt(v, 3)
    obj["consumo_rubros"] = escribir_tabla(cols, filas)


def pib_12m(obj, mes):
    """PIB nominal de los 12 meses que terminan en mes, interpolado entre cierres de trimestre (pib_n está anualizado)."""
    _, inv = leer_tabla(obj["inv_trim"])
    pib = pib_nominal(inv)

    def pib_4t(m):
        y, q = int(m[:4]), (int(m[5:]) + 2) // 3
        valores = []
        for _ in range(4):
            valores.append(pib.get(f"{y}-T{q}"))
            q -= 1
            if q == 0:
                y, q = y - 1, 4
        return None if None in valores else sum(valores) / 4

    resto = (int(mes[5:]) - 1) % 3
    fin = pib_4t(mes)
    if resto == 2 or fin is None:
        return fin
    inicio = pib_4t(mover_mes(mes, -(resto + 1)))
    return None if inicio is None else inicio + (fin - inicio) * (resto + 1) / 3


def aplicar_recaudacion(obj):
    """Recaudación de ARCA: derechos de comercio, recaudación real y presión tributaria en los meses posteriores a la v1."""
    R = {f["mes"]: f for f in leer_fuente("recaudacion_mensual.csv")[1]}
    trib = {m: num(f["tributarios"]) for m, f in R.items()}
    cols, filas = leer_tabla(obj["mensual"])
    M = {r["mes"]: r for r in filas}
    desde = {c: ultimo_con(M, c) for c in ("recaudacion_real_ia", "presion_trib_12m")}
    for mes in sorted(R):
        r, previo = M.get(mes), M.get(mover_mes(mes, -12))
        if r is None:
            continue
        if mes > desde["recaudacion_real_ia"] and previo and trib.get(mover_mes(mes, -12)) and num(r["ipc_index"]) and num(previo["ipc_index"]):
            r["recaudacion_real_ia"] = fmt((trib[mes] / trib[mover_mes(mes, -12)] / (num(r["ipc_index"]) / num(previo["ipc_index"])) - 1) * 100, 6)
        s12, pib = suma_12m(trib, mes), pib_12m(obj, mes)
        if mes > desde["presion_trib_12m"] and s12 and pib:
            r["presion_trib_12m"] = fmt(s12 / pib * 100, 4)
    obj["mensual"] = escribir_tabla(cols, filas)
    # Derechos de importación y exportación, con el tipo de cambio del mes para la alícuota efectiva.
    icols, ifilas = leer_tabla(obj["inv_mensual"])
    D = {r["mes"]: r for r in ifilas}
    desde = {c: ultimo_con(D, c) for c in ("der_imp", "der_exp")}
    for mes in sorted(m for m in R if m > ifilas[-1]["mes"]):
        D[mes] = {**{c: "" for c in icols}, "mes": mes}
        ifilas.append(D[mes])
    for mes, f in R.items():
        r = D.get(mes)
        if r is None:
            continue
        for c in ("der_imp", "der_exp"):
            if mes > desde[c] and num(f[c]) is not None:
                r[c] = fmt(num(f[c]), 2)
        if r["tc"] == "" and num(M.get(mes, {}).get("tc_a3500")):
            r["tc"] = fmt(num(M[mes]["tc_a3500"]), 1)
    obj["inv_mensual"] = escribir_tabla(icols, ifilas)


def actualizar_kpi_recaudacion(obj):
    cols, filas = leer_tabla(obj["ultimos"])
    _, mf = leer_tabla(obj["mensual"])
    M = {r["mes"]: r for r in mf}
    for r in filas:
        col = {"recaud_real": "recaudacion_real_ia", "presion": "presion_trib_12m"}.get(r["id"])
        if not col:
            continue
        m = ultimo_con(M, col)
        if m <= r["periodo"]:
            continue
        a = num(M[m][col])
        r.update(valor=fmt(a, 2), periodo=m, periodo_txt=f"{MESES[int(m[5:]) - 1]} {m[:4]}")
        if col == "recaudacion_real_ia":
            r["estado"] = "bueno" if a > 0 else "malo"
        elif num(M.get(mover_mes(m, -12), {}).get(col)) is not None:
            r["variacion"] = fmt(a - num(M[mover_mes(m, -12)][col]), 2)
    obj["ultimos"] = escribir_tabla(cols, filas)


def aplicar_eph(obj):
    """Tasas de la EPH: suma los trimestres posteriores a la v1, con un decimal como INDEC."""
    cols, filas = leer_tabla(obj["trimestral"])
    T = {r["trimestre"]: r for r in filas if "-T" in r["trimestre"]}
    F = {f["trimestre"]: f for f in leer_fuente("eph_trimestral.csv")[1]}
    desde = {c: ultimo_con(T, c) for c in ("desempleo", "actividad", "empleo", "desempleo_dif_ia")}
    for t, f in sorted(F.items()):
        r = T.get(t)
        if r is None:
            continue
        for c in ("desempleo", "actividad", "empleo"):
            if t > desde[c] and num(f[c]) is not None:
                r[c] = fmt(num(f[c]), 1)
        previo = T.get(f"{int(t[:4]) - 1}-{t[5:]}")
        if t > desde["desempleo_dif_ia"] and previo and num(r["desempleo"]) is not None and num(previo["desempleo"]) is not None:
            r["desempleo_dif_ia"] = fmt(num(r["desempleo"]) - num(previo["desempleo"]), 1)
    obj["trimestral"] = escribir_tabla(cols, filas)


def actualizar_kpi_eph(obj):
    cols, filas = leer_tabla(obj["ultimos"])
    _, tf = leer_tabla(obj["trimestral"])
    T = {r["trimestre"]: r for r in tf if "-T" in r["trimestre"]}
    t = max(k for k, r in T.items() if num(r["desempleo"]) is not None)
    for r in filas:
        if r["id"] == "desempleo" and t > r["periodo"]:
            var = num(T[t]["desempleo_dif_ia"])
            r.update(valor=fmt(num(T[t]["desempleo"]), 1), periodo=t, periodo_txt=f"{t[-1]}.º trim. {t[:4]}", variacion=fmt(var, 1) if var is not None else "",
                     estado="malo" if (var or 0) > 0 else "bueno" if (var or 0) < 0 else "neutral")
    obj["ultimos"] = escribir_tabla(cols, filas)


TIPOS_IBIF = ("tot", "cons", "ocons", "maq", "maq_n", "maq_i", "tra", "tra_n", "tra_i", "otr")


def derivadas_inversion(I, t, ts):
    """Columnas derivadas de inv_trim con el método de la v1 (verificado en auditar.py)."""
    r = I[t]
    i = ts.index(t)
    previo = I.get(f"{int(t[:4]) - 1}-{t[5:]}")
    cuatro = [I[x] for x in ts[max(0, i - 3):i + 1]]
    s4 = (lambda k: sum(num(x[k]) for x in cuatro)) if len(cuatro) == 4 and all(num(x[k]) is not None for x in cuatro for k in ("n_tot", "r_tot")) else None
    out = {}
    if num(r["r_cons"]) is not None and num(r["r_ocons"]) is not None:
        out["r_construc"] = num(r["r_cons"]) + num(r["r_ocons"])
    if previo:
        for k in ("tot", "cons", "ocons", "maq", "maq_n", "maq_i", "tra", "otr"):
            if num(r["r_" + k]) and num(previo["r_" + k]):
                out[k + "_ia"] = (num(r["r_" + k]) / num(previo["r_" + k]) - 1) * 100
        if "r_construc" in out and num(previo["r_construc"]):
            out["construc_ia"] = (out["r_construc"] / num(previo["r_construc"]) - 1) * 100
    if num(r["n_tot"]) and num(r["pib_n"]):
        out["ibif_pib_t"] = num(r["n_tot"]) / num(r["pib_n"]) * 100
    if s4:
        out["ibif_idx"] = s4("r_tot") / 4
        for k in ("cons", "ocons", "maq", "tra", "otr"):
            if all(num(x["n_" + k]) is not None for x in cuatro):
                out["sh_" + k] = s4("n_" + k) / s4("n_tot") * 100
        if all(num(x["n_maq_i"]) is not None and num(x["n_maq"]) for x in cuatro):
            out["imp_maq_sh"] = s4("n_maq_i") / s4("n_maq") * 100
        if all(num(x["pib_n"]) for x in cuatro):
            out["ibif_pib_4t"] = s4("n_tot") / s4("pib_n") * 100
    if len(cuatro) == 4 and all(num(x["ied_flujo"]) is not None for x in cuatro):
        out["ied_flujo_4t"] = sum(num(x["ied_flujo"]) for x in cuatro)
    return out


def aplicar_inversion(obj):
    """Inversión por tipo e IED: suma los trimestres posteriores a la v1 y calcula sus derivadas."""
    cols, filas = leer_tabla(obj["inv_trim"])
    I = {r["trimestre"]: r for r in filas}
    F = {f["trimestre"]: f for f in leer_fuente("inversion_trimestral.csv")[1]}
    D = {f["trimestre"]: f for f in leer_fuente("demanda_trimestral.csv")[1]}
    desde = {c: ultimo_con(I, c) for c in cols[2:]}
    for t in sorted(x for x in F if x > filas[-1]["trimestre"] and num(F[x]["r_tot"]) is not None):
        I[t] = {**{c: "" for c in cols}, "trimestre": t, "trim_inicio": f"{t[:4]}-{(int(t[-1]) - 1) * 3 + 1:02d}"}
        filas.append(I[t])
    nuevos = [t for t in I if any(t > desde[p + k] for p in ("r_", "n_") for k in TIPOS_IBIF)]
    for t in sorted(I):
        r, f, dm = I[t], F.get(t, {}), D.get(t, {})
        for c in [p + k for p in ("r_", "n_") for k in TIPOS_IBIF] + ["ied_cap", "ied_deu"]:
            if t > desde[c] and num(f.get(c)) is not None:
                r[c] = fmt(num(f[c]), 3)
        if t > desde["ied_flujo"] and num(r["ied_cap"]) is not None and num(r["ied_deu"]) is not None:
            r["ied_flujo"] = fmt(num(r["ied_cap"]) + num(r["ied_deu"]), 3)
        for c, origen in (("pib_n", "pib_n"), ("pib_r", "d_pib")):
            if t > desde[c] and num(dm.get(origen)) is not None:
                r[c] = fmt(num(dm[origen]), 3)
    ts = sorted(I)
    for t in ts:
        for c, v in derivadas_inversion(I, t, ts).items():
            if t > desde[c] and (t in nuevos or c == "ied_flujo_4t"):
                I[t][c] = fmt(v, 3)
    obj["inv_trim"] = escribir_tabla(cols, filas)


def actualizar_kpi_indec(obj):
    cols, filas = leer_tabla(obj["ultimos"])
    _, mf = leer_tabla(obj["mensual"])
    M = {r["mes"]: r for r in mf}
    for r in filas:
        if r["id"] not in ("sal_real", "emae"):
            continue
        col = "sal_real" if r["id"] == "sal_real" else "emae_ia"
        m = ultimo_con(M, col)
        if m <= r["periodo"]:
            continue
        a = num(M[m][col])
        r.update(valor=fmt(a, 2), periodo=m, periodo_txt=f"{MESES[int(m[5:]) - 1]} {m[:4]}")
        if r["id"] == "sal_real":
            var = (a / num(M[mover_mes(m, -12)][col]) - 1) * 100
            r.update(variacion=fmt(var, 2), estado="bueno" if var > 0 else "malo")
        else:
            r["estado"] = "bueno" if a > 0 else "malo"
    obj["ultimos"] = escribir_tabla(cols, filas)


def actualizar_kpi_mercado(obj):
    cols, filas = leer_tabla(obj["ultimos"])
    _, mf = leer_tabla(obj["mensual"])
    M = {r["mes"]: r for r in mf}
    mapa = {"infl_m": "infl_mensual", "infl_ia": "infl_ia", "rem_12m": "rem_12m", "tasa_real": "tasa_real_pf_m", "tc": "tc_a3500", "brecha_ccl": "brecha_ccl", "riesgo": "riesgo_pais", "reservas": "reservas"}
    for r in filas:
        col = mapa.get(r["id"])
        if not col:
            continue
        m = ultimo_con(M, col)
        a = num(M[m][col])
        previo_m = num(M.get(mover_mes(m, -1), {}).get(col))
        previo_a = num(M.get(mover_mes(m, -12), {}).get(col))
        txt = r["variacion_txt"]
        r.update(valor=fmt(a, 2), periodo=m, periodo_txt=f"{MESES[int(m[5:]) - 1]} {m[:4]}")
        if txt in ("pp vs mes anterior", "pb vs mes anterior") and previo_m is not None:
            r["variacion"] = fmt(a - previo_m, 2)
        elif txt == "% interanual" and previo_a:
            r["variacion"] = fmt((a / previo_a - 1) * 100, 2)
        elif txt == "pp interanual" and previo_a is not None:
            r["variacion"] = fmt(a - previo_a, 2)
        if r["id"] == "tasa_real":
            r["variacion_txt"] = "positiva: el plazo fijo le gana a la inflación" if a > 0 else "negativa: la inflación le gana al plazo fijo"
    obj["ultimos"] = escribir_tabla(cols, filas)


def tabla_calendario(obj):
    """Tabla pública con el estado de cada fuente; depende solo de los datos, no de la fecha de hoy."""
    conf = cal.cargar()
    filas = []
    for f in conf["automaticas"]:
        u = cal.ultimo_periodo(f)
        filas.append({"dato": f["nombre"], "origen": f["origen"], "frecuencia": f["frecuencia"], "ultimo": cal.texto_periodo(u), "orden": cal.proxima_fecha(f["regla"], u).isoformat(),
                      "proxima": cal.proxima_fecha(f["regla"], u).strftime("%d/%m/%Y"), "estado": "Automática"})
    for f in conf["pendientes"]:
        _, tf = leer_tabla(obj[f["tabla"]])
        clave = list(tf[0])[0]
        valores = [r[clave] for r in tf if r.get(f["columna"]) not in ("", None)]
        u = max(valores, key=str) if clave != "semestre" else valores[-1]
        if "proxima_texto" in f:
            orden, prox = "9999", f["proxima_texto"]
        else:
            d = cal.proxima_fecha(f["regla"], u)
            orden, prox = d.isoformat(), d.strftime("%d/%m/%Y")
        filas.append({"dato": f["nombre"], "origen": f["origen"], "frecuencia": f["frecuencia"], "ultimo": cal.texto_periodo(u), "orden": orden, "proxima": prox, "estado": "Pendiente: sin descarga automática"})
    filas.sort(key=lambda x: (x["estado"] != "Automática", x["orden"]))
    obj["calendario_datos"] = escribir_tabla(["dato", "origen", "frecuencia", "ultimo", "proxima", "estado"], [{k: v for k, v in x.items() if k != "orden"} for x in filas])


def agregar_mensual_e2(obj):
    cols, filas = leer_tabla(obj["mensual"])
    M = {r["mes"]: r for r in filas}
    ultimo = filas[-1]["mes"]
    _, inv = leer_tabla(obj["inv_trim"])
    pib = pib_nominal(inv)

    def pib_4t(mes):
        t = trimestre_de(mes)
        y, q = int(t[:4]), int(t[-1])
        claves = []
        for _ in range(4):
            claves.append(f"{y}-T{q}")
            q -= 1
            if q == 0:
                y, q = y - 1, 4
        valores = [pib.get(k) for k in claves]
        # pib_n está anualizado: el PIB de cuatro trimestres es el promedio, no la suma.
        return None if any(v is None for v in valores) else sum(valores) / 4

    def pib_mes(mes):
        """PIB de 12 meses interpolado entre cierres de trimestre, como el primario de la v1."""
        resto = (int(mes[5:]) - 1) % 3
        fin = pib_4t(mes)
        if resto == 2 or fin is None:
            return fin
        inicio = pib_4t(mover_mes(mes, -(resto + 1)))
        return None if inicio is None else inicio + (fin - inicio) * (resto + 1) / 3

    nuevas = {}
    # Deuda y BCRA: columnas tal como vienen (solo meses dentro de la tabla).
    dcols, dfilas = leer_fuente("deuda_mensual.csv")
    for c in dcols[1:]:
        nuevas[c] = {r["mes"]: num(r[c]) for r in dfilas if num(r[c]) is not None}
    pagos_int = {m: nuevas["pagos_int_ars"].get(m, 0) + nuevas["pagos_int_me"].get(m, 0) for m in nuevas["pagos_total"]}
    nuevas["pagos_total_12m"] = {m: suma_12m(nuevas["pagos_total"], m) for m in nuevas["pagos_total"]}
    nuevas["pagos_me_12m"] = {m: suma_12m(nuevas["pagos_me"], m) for m in nuevas["pagos_total"]}
    nuevas["pagos_int_12m"] = {m: suma_12m(pagos_int, m) for m in nuevas["pagos_total"]}
    nuevas["deuda_pesos"] = {m: nuevas["deuda_ars_fija"][m] + nuevas["deuda_ars_cer"][m] for m in nuevas["deuda_ars_fija"]}
    nuevas["deuda_me_otras"] = {m: nuevas["deuda_eur"][m] + nuevas["deuda_jpy"][m] + nuevas["deuda_otras"][m] for m in nuevas["deuda_eur"]}

    bcols, bfilas = leer_fuente("bcra_mensual.csv")
    for c in bcols[1:]:
        nuevas[c] = {r["mes"]: num(r[c]) for r in bfilas if num(r[c]) is not None and r["mes"] <= ultimo}
    # En los meses posteriores a la base de la v1, el dólar y las reservas salen de la API del BCRA.
    for mes, r in M.items():
        if r["tc_a3500"] == "" and mes in nuevas.get("tc_ref", {}):
            r["tc_a3500"] = fmt(nuevas["tc_ref"][mes], 2)
        if r["reservas"] == "" and mes in nuevas.get("reservas_ult", {}):
            r["reservas"] = fmt(nuevas["reservas_ult"][mes], 0)
    nuevas["res_compras_12m"] = {m: suma_12m(nuevas["res_compras"], m) for m in nuevas["res_compras"]}
    nuevas["pasivos_rem"] = {m: nuevas["pases_pasivos"][m] + nuevas["leliq"][m] for m in nuevas["pases_pasivos"] if m in nuevas["leliq"]}
    nuevas["pasivos_rem_base"] = {m: v / nuevas["base_monetaria"][m] for m, v in nuevas["pasivos_rem"].items() if nuevas["base_monetaria"].get(m)}

    # Empleo y viajes.
    scols, sfilas = leer_fuente("series_mensuales.csv")
    serie = {c: {r["mes"]: num(r[c]) for r in sfilas if num(r[c]) is not None} for c in scols[1:]}
    for c in scols[1:]:
        if c.startswith("emp_"):
            nuevas[c] = serie[c]
    viajes = {m: serie["viajes_cobros"][m] - serie["viajes_pagos"][m] for m in serie["viajes_cobros"] if m in serie["viajes_pagos"]}
    nuevas["viajes_neto"] = viajes
    nuevas["viajes_neto_12m"] = {m: suma_12m(viajes, m) for m in viajes}

    # Fiscal: acumulado de 12 meses sobre el PIB de los últimos cuatro trimestres.
    fcols, ffilas = leer_fuente("fiscal_mensual.csv")
    F = {c: {r["mes"]: num(r[c]) for r in ffilas if num(r[c]) is not None} for c in fcols[1:]}
    componentes = ["f_prestaciones", "f_remuneraciones", "f_bienes_serv", "f_transf_provincias", "f_universidades", "f_transf_otras",
                   "f_deficit_empresas", "f_otros_corrientes", "f_transf_exterior", "f_intereses", "f_otras_rentas"]
    meses_f = sorted(F["f_gastos"])
    F["f_capital"] = {m: sum(F[c].get(m, 0) for c in ("f_capital_directa", "f_capital_provincias", "f_capital_otras", "f_capital_resto")) for m in meses_f}
    F["f_transf_priv_dif"] = {m: F["f_gastos_corrientes"][m] - sum(F[c].get(m, 0) for c in componentes) for m in meses_f}
    F["f_resto"] = {m: sum(F[c].get(m, 0) for c in ("f_transf_otras", "f_deficit_empresas", "f_otros_corrientes", "f_transf_exterior", "f_otras_rentas")) for m in meses_f}
    salida = {"fis_ingresos_pib": "f_ingresos", "fis_gastos_pib": "f_gastos", "fis_financiero_pib": "f_financiero", "fis_superavit_pib": "f_superavit",
              "fis_intereses_pib": "f_intereses", "fg_prestaciones": "f_prestaciones", "fg_transf_priv": "f_transf_priv_dif", "fg_remuneraciones": "f_remuneraciones",
              "fg_bienes_serv": "f_bienes_serv", "fg_provincias": "f_transf_provincias", "fg_universidades": "f_universidades", "fg_capital": "f_capital", "fg_resto": "f_resto"}
    for col, origen in salida.items():
        nuevas[col] = {}
        for m in meses_f:
            s, p = suma_12m(F[origen], m), pib_mes(m)
            if s is not None and p:
                nuevas[col][m] = s / p * 100
    # Agregar columnas.
    decimales = {"pasivos_rem_base": 3}
    for c, serie_c in nuevas.items():
        cols.append(c)
        dec = decimales.get(c, 3 if c.startswith(("fis_", "fg_")) else 1)
        for mes, r in M.items():
            v = serie_c.get(mes)
            r[c] = fmt(v, dec) if v is not None else ""
    obj["mensual"] = escribir_tabla(cols, filas)
    return M


def agregar_trimestral_e2(obj, M):
    cols, filas = leer_tabla(obj["trimestral"])
    _, sfilas = leer_fuente("series_trimestrales.csv")
    S = {r["trimestre"]: r for r in sfilas}
    _, inv = leer_tabla(obj["inv_trim"])
    pib = pib_nominal(inv)

    def previos(t, n=4):
        y, q = int(t[:4]), int(t[-1])
        out = []
        for _ in range(n):
            out.append(f"{y}-T{q}")
            q -= 1
            if q == 0:
                y, q = y - 1, 4
        return out

    def tc_prom(t):
        y, q = t[:4], int(t[-1])
        v = [num(M[f"{y}-{i:02d}"]["tc_a3500"]) for i in range((q - 1) * 3 + 1, q * 3 + 1) if f"{y}-{i:02d}" in M]
        return sum(v) / len(v) if len(v) == 3 else None

    vals = {t: {c: num(r[c]) for c in r if c != "trimestre"} for t, r in S.items()}
    for t, v in vals.items():
        if v.get("cc_rentas") is not None:
            v["cc_primario"] = v["cc_rentas"] + (v.get("cc_remuneraciones") or 0)
            v["cc_secundario"] = v["cc"] - v["cc_bienes"] - v["cc_servicios"] - v["cc_primario"]
    flujo = ["cc", "cc_bienes", "cc_servicios", "cc_primario", "cc_secundario", "cfin", "cfin_directa", "cfin_cartera", "cfin_otra"]
    nuevas = flujo + [c + "_4t" for c in flujo] + ["cc_pib_4t", "errores", "iip_neta", "iip_gobierno", "iip_bcra", "iip_bancos", "iip_otros", "subocupacion", "asal_sin_desc"]
    cols.extend(nuevas)
    for r in filas:
        t = r["trimestre"]
        v = vals.get(t, {})
        for c in nuevas:
            r[c] = ""
        if "-T" not in t or not v:
            continue
        for c in flujo + ["errores", "iip_neta", "iip_gobierno", "iip_bcra", "iip_bancos", "iip_otros"]:
            if v.get(c) is not None:
                r[c] = fmt(v[c], 1)
        for c in ("subocupacion", "asal_sin_desc"):
            if v.get(c) is not None:
                r[c] = fmt(v[c] * 100, 1)
        ventana = previos(t)
        for c in flujo:
            x = [vals.get(k, {}).get(c) for k in ventana]
            if all(i is not None for i in x):
                r[c + "_4t"] = fmt(sum(x), 1)
        ccs = [vals.get(k, {}).get("cc") for k in ventana]
        # pib_n está anualizado: cada trimestre aporta un cuarto.
        usd = [pib[k] / 4 / tc_prom(k) if pib.get(k) and tc_prom(k) else None for k in ventana]
        if all(i is not None for i in ccs + usd):
            r["cc_pib_4t"] = fmt(sum(ccs) / sum(usd) * 100, 2)
    obj["trimestral"] = escribir_tabla(cols, filas)


def agregar_anual_e2(obj):
    cols, filas = leer_tabla(obj["anual"])
    dcols, dfilas = leer_fuente("deuda_anual.csv")
    D = {r["anio"]: r for r in dfilas}
    cols.extend(dcols[1:])
    for r in filas:
        for c in dcols[1:]:
            r[c] = D.get(r["anio"], {}).get(c, "")
    obj["anual"] = escribir_tabla(cols, filas)


def agregar_tablas_e2(obj):
    for tabla, archivo in (("deuda_perfil", "deuda_perfil.csv"), ("deuda_resumen", "deuda_resumen.csv")):
        cols, filas = leer_fuente(archivo)
        obj[tabla] = escribir_tabla(cols, filas)


def ultimo_con(M, col):
    return max((m for m, r in M.items() if num(r.get(col)) is not None), default=None)


def agregar_ultimos_e2(obj):
    cols, filas = leer_tabla(obj["ultimos"])
    _, mfilas = leer_tabla(obj["mensual"])
    M = {r["mes"]: r for r in mfilas}
    _, tfilas = leer_tabla(obj["trimestral"])
    T = {r["trimestre"]: r for r in tfilas if "-T" in r["trimestre"]}
    _, afilas = leer_tabla(obj["anual"])
    A = {r["anio"]: r for r in afilas}
    res = dict((r["indicador"], r["valor"]) for r in leer_fuente("deuda_resumen.csv")[1])
    corte = res.pop("corte")
    res = {k: num(v) for k, v in res.items()}
    corte_txt = f"{int(corte[8:])} {MESES[int(corte[5:7]) - 1]} {corte[:4]}"

    def txt_mes(m):
        return f"{MESES[int(m[5:]) - 1]} {m[:4]}"

    def fila(i, nombre, valor, unidad, periodo, var, var_txt, txt, fuente, estado="neutral"):
        filas.append({"id": i, "indicador": nombre, "valor": fmt(valor, 2), "unidad": unidad, "periodo": periodo, "variacion": fmt(var, 2) if var is not None else "",
                      "variacion_txt": var_txt, "estado": estado, "fuente": fuente, "periodo_txt": txt})

    def desde_mes(i, nombre, col, unidad, var_tipo, fuente):
        m = ultimo_con(M, col)
        a, b = num(M[m][col]), num(M.get(mover_mes(m, -12), {}).get(col))
        var = None if b is None else ((a / b - 1) * 100 if var_tipo == "pct" else a - b)
        fila(i, nombre, a, unidad, m, var, "% interanual" if var_tipo == "pct" else f"{unidad} interanual", txt_mes(m), fuente)

    def desde_trim(i, nombre, col, unidad, fuente):
        t = max(k for k, r in T.items() if num(r.get(col)) is not None)
        a = num(T[t][col])
        b = num(T.get(f"{int(t[:4]) - 1}-{t[5:]}", {}).get(col))
        fila(i, nombre, a, unidad, t, None if b is None else a - b, f"{unidad} interanual", f"{t[-1]}.º trim. {t[:4]}", fuente)

    finanzas = "Secretaría de Finanzas"
    desde_mes("deuda_bruta", "Deuda bruta de la Administración Central", "deuda_bruta", "M US$", "pct", finanzas)
    desde_mes("deuda_fmi", "Deuda con el FMI", "deuda_fmi", "M US$", "pct", finanzas)
    desde_mes("pagos_12m", "Pagos de deuda en moneda extranjera (12 meses)", "pagos_me_12m", "M US$", "pct", finanzas)
    an = max(k for k, r in A.items() if num(r.get("deuda_pib")) is not None)
    previo = num(A[str(int(an) - 1)]["deuda_pib"])
    fila("deuda_pib", "Deuda bruta / PIB", num(A[an]["deuda_pib"]), "% PIB", an, num(A[an]["deuda_pib"]) - previo, "pp vs año anterior", an, finanzas)
    fila("tasa_deuda", "Tasa promedio de la deuda", res["tasa_promedio"], "%", corte[:7], None, "", corte_txt, finanzas)
    fila("vida_deuda", "Vida promedio de la deuda", res["vida_promedio"], "años", corte[:7], None, "", corte_txt, finanzas)
    indec = "INDEC, balance de pagos"
    desde_trim("cc_4t", "Cuenta corriente (4 trimestres)", "cc_4t", "M US$", indec)
    desde_trim("cc_pib", "Cuenta corriente / PIB (4 trimestres)", "cc_pib_4t", "pp", "INDEC, propio")
    desde_trim("iip", "Posición de inversión internacional neta", "iip_neta", "M US$", "INDEC")
    desde_trim("subocupacion", "Subocupación", "subocupacion", "pp", "INDEC, EPH")
    desde_trim("informalidad", "Asalariados sin descuento jubilatorio", "asal_sin_desc", "pp", "INDEC, EPH")
    desde_mes("viajes_12m", "Saldo de turismo y viajes (12 meses)", "viajes_neto_12m", "M US$", "dif", "BCRA, mercado de cambios")
    bcra = "BCRA"
    desde_mes("compras_12m", "Compras de divisas del BCRA (12 meses)", "res_compras_12m", "M US$", "dif", bcra)
    desde_mes("dep_usd", "Depósitos privados en dólares", "dep_usd_priv", "M US$", "pct", bcra)
    desde_mes("prest_usd", "Préstamos privados en dólares", "prest_usd_priv", "M US$", "pct", bcra)
    hacienda = "Hacienda e INDEC"
    desde_mes("fis_fin", "Resultado financiero (12 meses)", "fis_financiero_pib", "pp", "dif", hacienda)
    desde_mes("fis_int", "Intereses netos (12 meses)", "fis_intereses_pib", "pp", "dif", hacienda)
    trabajo = "Secretaría de Trabajo, SIPA"
    desde_mes("emp_total", "Trabajadores registrados", "emp_total", "miles", "pct", trabajo)
    desde_mes("emp_privado", "Asalariados privados registrados", "emp_privado", "miles", "pct", trabajo)
    obj["ultimos"] = escribir_tabla(cols, filas)


def agregar_etapa3(obj):
    # Mensual: actividad, contexto global y crédito.
    cols, filas = leer_tabla(obj["mensual"])
    M = {r["mes"]: r for r in filas}
    _, inv = leer_tabla(obj["inv_trim"])
    pib = pib_nominal(inv)
    ultimo = filas[-1]["mes"]
    for archivo, dec in (("actividad_mensual.csv", 2), ("global_mensual.csv", 3), ("credito_mensual.csv", 0)):
        fcols, ffilas = leer_fuente(archivo)
        F = {r["mes"]: r for r in ffilas}
        cols.extend(fcols[1:])
        for mes, r in M.items():
            for c in fcols[1:]:
                v = num(F.get(mes, {}).get(c))
                # Antes de 1995 Brasil tuvo otras monedas e hiperinflación: esos valores no son comparables.
                if c in ("brl", "selic") and mes < "1995-01":
                    v = None
                r[c] = fmt(v, dec) if v is not None else ""

    def ia(col, mes):
        a, b = num(M[mes][col]), num(M.get(mover_mes(mes, -12), {}).get(col))
        return None if a is None or not b else (a / b - 1) * 100

    derivadas = {"ibcbr_ia": "ibcbr", "isac_ia": "isac", "issp_ia": "issp", "soja_ia": "soja", "brent_ia": "brent"}
    cols.extend(derivadas)
    cols.extend(["credito_pib", "pagos_me_reservas"])
    for mes, r in M.items():
        for c, o in derivadas.items():
            r[c] = fmt(ia(o, mes), 2)
        r["credito_pib"] = ""
        credito = num(r["prestamos_priv"])
        if credito:
            q = (int(mes[5:]) + 2) // 3
            y = int(mes[:4])
            claves = []
            for _ in range(4):
                claves.append(f"{y}-T{q}")
                q -= 1
                if q == 0:
                    y, q = y - 1, 4
            v = [pib.get(k) for k in claves]
            if all(x is not None for x in v):
                r["credito_pib"] = fmt(credito / (sum(v) / 4) * 100, 2)
        pagos, res = num(r["pagos_me_12m"]), num(r["reservas"])
        r["pagos_me_reservas"] = fmt(pagos / res * 100, 1) if pagos is not None and res else ""
    obj["mensual"] = escribir_tabla(cols, filas)

    # Trimestral: demanda agregada, contribuciones al crecimiento y precios y cantidades.
    cols, filas = leer_tabla(obj["trimestral"])
    _, dfilas = leer_fuente("demanda_trimestral.csv")
    D = {r["trimestre"]: {k: num(v) for k, v in r.items() if k != "trimestre"} for r in dfilas}
    comp = {"d_cons_priv": 1, "d_cons_pub": 1, "d_ibif": 1, "d_expo": 1, "d_impo": -1}
    nuevas = ["d_pib", "d_cons_priv_ia", "d_cons_pub_ia", "d_ibif_ia", "d_expo_ia", "d_impo_ia"] + [f"ct_{c[2:]}" for c in comp] + ["ct_resto", "p_expo", "q_expo", "compras_12m_t"]
    cols.extend(nuevas)
    for r in filas:
        t = r["trimestre"]
        for c in nuevas:
            r[c] = ""
        if "-T" in t:
            cierre = f"{t[:4]}-{int(t[-1]) * 3:02d}"
            if cierre in M:
                r["compras_12m_t"] = M[cierre].get("res_compras_12m", "")
        d = D.get(t)
        if "-T" not in t or not d:
            continue
        for c in ("d_pib", "p_expo", "q_expo"):
            if d.get(c) is not None:
                r[c] = fmt(d[c], 1 if c == "d_pib" else 2)
        prev = D.get(f"{int(t[:4]) - 1}-{t[5:]}")
        if not prev or not prev.get("d_pib") or d.get("d_pib") is None:
            continue
        suma = 0
        for c, signo in comp.items():
            if d.get(c) is None or not prev.get(c):
                continue
            r[f"{c}_ia"] = fmt((d[c] / prev[c] - 1) * 100, 2)
            aporte = signo * (d[c] - prev[c]) / prev["d_pib"] * 100
            r[f"ct_{c[2:]}"] = fmt(aporte, 2)
            suma += aporte
        r["ct_resto"] = fmt((d["d_pib"] / prev["d_pib"] - 1) * 100 - suma, 2)
        if r.get("pib_ia", "") == "":  # trimestre posterior a la v1: el crecimiento sale de la misma serie
            r["pib_ia"] = fmt((d["d_pib"] / prev["d_pib"] - 1) * 100, 3)
    obj["trimestral"] = escribir_tabla(cols, filas)

    ccols, cfilas = leer_fuente("curva_pesos.csv")
    # Un rendimiento negativo indica un título con ajuste, no comparable con la curva a tasa nominal.
    obj["curva_pesos"] = escribir_tabla(ccols, [r for r in cfilas if num(r["tem"]) > 0])
    agregar_sostenibilidad(obj)
    agregar_ultimos_e3(obj)


def agregar_sostenibilidad(obj):
    """Compara cada indicador con un año antes, sin umbrales propios."""
    _, mf = leer_tabla(obj["mensual"])
    M = {r["mes"]: r for r in mf}
    _, tf = leer_tabla(obj["trimestral"])
    T = {r["trimestre"]: r for r in tf if "-T" in r["trimestre"]}
    _, af = leer_tabla(obj["anual"])
    A = {r["anio"]: r for r in af}
    filas = []

    def agregar(area, nombre, unidad, per, valor, per_prev, previo, mejor, dec=1):
        if valor is None or previo is None:
            sys.exit(f"Sostenibilidad: falta dato para {nombre}")
        filas.append({"area": area, "indicador": nombre, "unidad": unidad, "periodo": per, "valor": fmt(valor, dec), "periodo_previo": per_prev, "previo": fmt(previo, dec),
                      "lectura": "Mejoró" if (valor - previo) * mejor > 0 else ("Empeoró" if (valor - previo) * mejor < 0 else "Sin cambios")})

    def men(area, nombre, unidad, col, mejor, dec=1):
        m = ultimo_con(M, col)
        p = mover_mes(m, -12)
        agregar(area, nombre, unidad, f"{MESES[int(m[5:]) - 1]} {m[:4]}", num(M[m][col]), f"{MESES[int(p[5:]) - 1]} {p[:4]}", num(M[p][col]), mejor, dec)

    def tri(area, nombre, unidad, col, mejor, dec=1):
        t = max(k for k, r in T.items() if num(r.get(col)) is not None)
        p = f"{int(t[:4]) - 1}-{t[5:]}"
        agregar(area, nombre, unidad, f"{t[-1]}.º trim. {t[:4]}", num(T[t][col]), f"{p[-1]}.º trim. {p[:4]}", num(T[p][col]), mejor, dec)

    def anu(area, nombre, unidad, col, mejor, dec=1):
        a = max(k for k, r in A.items() if num(r.get(col)) is not None)
        p = str(int(a) - 1)
        agregar(area, nombre, unidad, a, num(A[a][col]), p, num(A[p][col]), mejor, dec)

    anu("Deuda", "Deuda bruta / PIB", "%", "deuda_pib", -1)
    anu("Deuda", "Deuda en moneda extranjera / exportaciones", "%", "deuda_me_expo", -1, 0)
    anu("Deuda", "Deuda en moneda extranjera / reservas", "%", "deuda_me_reservas", -1, 0)
    anu("Deuda", "Intereses / recursos tributarios", "%", "intereses_recursos", -1)
    anu("Deuda", "Vida promedio de la deuda", "años", "vida_promedio", 1)
    men("Fiscal", "Resultado primario (12 meses)", "% PIB", "fis_superavit_pib", 1, 2)
    men("Fiscal", "Intereses netos (12 meses)", "% PIB", "fis_intereses_pib", -1, 2)
    men("Fiscal", "Resultado financiero (12 meses)", "% PIB", "fis_financiero_pib", 1, 2)
    tri("Externo", "Cuenta corriente / PIB (4 trimestres)", "%", "cc_pib_4t", 1, 2)
    men("Externo", "Compras de divisas del BCRA (12 meses)", "M US$", "res_compras_12m", 1, 0)
    men("Externo", "Pagos de deuda en moneda extranjera / reservas brutas", "%", "pagos_me_reservas", -1)
    men("Externo", "Riesgo país", "pb", "riesgo_pais", -1, 0)
    cols = ["area", "indicador", "unidad", "periodo", "valor", "periodo_previo", "previo", "lectura"]
    obj["sostenibilidad"] = escribir_tabla(cols, filas)


def agregar_ultimos_e3(obj):
    cols, filas = leer_tabla(obj["ultimos"])
    _, mf = leer_tabla(obj["mensual"])
    M = {r["mes"]: r for r in mf}

    def fila(i, nombre, col, unidad, tipo, fuente):
        m = ultimo_con(M, col)
        a, b = num(M[m][col]), num(M.get(mover_mes(m, -12), {}).get(col))
        var = None if b is None else ((a / b - 1) * 100 if tipo == "pct" else a - b)
        filas.append({"id": i, "indicador": nombre, "valor": fmt(a, 2), "unidad": unidad, "periodo": m, "variacion": fmt(var, 2),
                      "variacion_txt": "% interanual" if tipo == "pct" else f"{unidad} interanual", "estado": "neutral", "fuente": fuente,
                      "periodo_txt": f"{MESES[int(m[5:]) - 1]} {m[:4]}"})

    fila("soja", "Soja", "soja", "US$/t", "pct", "FMI vía FRED")
    fila("brent", "Petróleo Brent", "brent", "US$/barril", "pct", "FMI vía FRED")
    fila("fed", "Tasa de la Reserva Federal", "fed_funds", "%", "dif", "Reserva Federal vía FRED")
    fila("ibcbr", "Actividad de Brasil (IBC-Br)", "ibcbr_ia", "%", "dif", "Banco Central de Brasil")
    fila("uci", "Uso de la capacidad industrial", "uci", "%", "dif", "INDEC")
    fila("isac", "Construcción (ISAC)", "isac", "índice", "pct", "INDEC")
    fila("issp", "Servicios públicos (ISSP)", "issp", "índice", "pct", "INDEC")
    fila("credito_pib", "Crédito al sector privado / PIB", "credito_pib", "%", "dif", "BCRA e INDEC")
    m = ultimo_con(M, "reservas")
    for r in filas:
        if r["id"] == "reservas" and m > r["periodo"]:
            r.update(valor=M[m]["reservas"], periodo=m, periodo_txt=f"{MESES[int(m[5:]) - 1]} {m[:4]}")
        if r["id"] == "tc":
            t = ultimo_con(M, "tc_a3500")
            if t > r["periodo"]:
                r.update(valor=M[t]["tc_a3500"], periodo=t, periodo_txt=f"{MESES[int(t[5:]) - 1]} {t[:4]}")
    obj["ultimos"] = escribir_tabla(cols, filas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--actualizar-itcrm", action="store_true")
    args = ap.parse_args()
    if args.actualizar_itcrm or not ITCRM_CSV.exists():
        bajar_itcrm()
    ini, obj, fin = leer_datos(BASE)
    extender_filas(obj)
    aplicar_mercado(obj)
    aplicar_indec_mensual(obj)
    aplicar_consumo(obj)
    corregir_comercio_rubros(obj)
    quitar_s68(obj)
    aplicar_indec_sectores(obj)
    aplicar_comercio(obj)
    aplicar_recaudacion(obj)
    aplicar_eph(obj)
    aplicar_inversion(obj)
    M = actualizar_mensual(obj)
    actualizar_inv_mensual(obj, M)
    actualizar_comercio_anual(obj, M)
    actualizar_ultimos(obj, M)
    M = agregar_mensual_e2(obj)
    agregar_trimestral_e2(obj, M)
    agregar_anual_e2(obj)
    agregar_tablas_e2(obj)
    agregar_ultimos_e2(obj)
    agregar_etapa3(obj)
    actualizar_kpi_mercado(obj)
    actualizar_kpi_indec(obj)
    actualizar_kpi_recaudacion(obj)
    actualizar_kpi_eph(obj)
    obj["diario"] = escribir_tabla(*leer_fuente("diario.csv"))
    tabla_calendario(obj)
    SALIDA.write_text(ini + json.dumps(obj, ensure_ascii=False) + fin, encoding="utf-8", newline="\n")
    print(f"Escrito {SALIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
