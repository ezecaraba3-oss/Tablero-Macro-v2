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
    return "" if x is None else f"{round(x, dec):.{dec}f}".rstrip("0").rstrip(".")


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

    # Comercio: agosto revisado y septiembre, ya presentes en comercio_paises.
    for mes in ("2026-08", "2026-09"):
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
    for mes in ("2026-08", "2026-09"):
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
    for r in filas:
        if r["anio"] == "2026":
            meses = [f"2026-{i:02d}" for i in range(1, 10)]
            e = sum(num(M[m]["expo"]) for m in meses)
            i = sum(num(M[m]["impo"]) for m in meses)
            r.update(expo=fmt(e, 1), impo=fmt(i, 1), saldo=fmt(e - i, 1), cobertura=fmt(e / i * 100, 1),
                     meses="9", periodo="ene–sep (parcial)")
    obj["comercio_anual"] = escribir_tabla(cols, filas)


def actualizar_ultimos(obj, M):
    cols, filas = leer_tabla(obj["ultimos"])
    mes, previo = "2026-09", "2025-09"
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--actualizar-itcrm", action="store_true")
    args = ap.parse_args()
    if args.actualizar_itcrm or not ITCRM_CSV.exists():
        bajar_itcrm()
    ini, obj, fin = leer_datos(BASE)
    corregir_comercio_rubros(obj)
    quitar_s68(obj)
    M = actualizar_mensual(obj)
    actualizar_inv_mensual(obj, M)
    actualizar_comercio_anual(obj, M)
    actualizar_ultimos(obj, M)
    SALIDA.write_text(ini + json.dumps(obj, ensure_ascii=False) + fin, encoding="utf-8", newline="\n")
    print(f"Escrito {SALIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
