"""Controles de calidad de assets/datos.js. Sale con código 1 si alguno falla.

Además compara contra la base de la v1: toda celda que cambie fuera de la lista
de cambios permitidos se considera un error.
"""
import csv
import io
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = Path(__file__).resolve().parent.parent
fallas = []


def leer(ruta):
    raw = ruta.read_text(encoding="utf-8")
    return json.JSONDecoder().raw_decode(raw[raw.index("{", raw.index("window.DATOS")):])[0]


def tabla(obj, n):
    return list(csv.DictReader(io.StringIO(obj[n])))


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def control(nombre, ok, detalle=""):
    print(("OK    " if ok else "FALLA ") + nombre + (f" | {detalle}" if detalle else ""))
    if not ok:
        fallas.append(nombre)


def cerca(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol


def mover(mes, n):
    y, m = map(int, mes.split("-"))
    t = y * 12 + m - 1 + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


base = leer(RAIZ / "pipeline" / "base" / "datos_v1.js")
nuevo = leer(RAIZ / "assets" / "datos.js")

# 1. Solo cambia lo permitido.
PERMITIDO = {
    "mensual": {("2026-08", c) for c in ["expo", "impo", "saldo_neto", "expo_12m", "impo_12m", "saldo_12m", "saldo_neto_12m", "cobertura_12m", "expo_ia_12m", "impo_ia_12m"]}
    | {("2026-09", c) for c in ["expo", "impo", "saldo_neto", "expo_12m", "impo_12m", "saldo_12m", "saldo_neto_12m", "cobertura_12m", "expo_ia_12m", "impo_ia_12m"]}
    | {(m, c) for m in ("2017-01", "2017-02") for c in ("infl_mensual", "tasa_real_pf_m")},
    "comercio_rubros": {("2026-06", "x00"), ("2026-08", "x00"), ("2026-08", "x01")},
    "inv_mensual": {(m, c) for m in ("2026-08", "2026-09") for c in ("impo", "ar_efec", "ar_efec_12m")},
    "comercio_anual": {("2026", c) for c in ("expo", "impo", "saldo", "cobertura", "meses", "periodo")},
    "ultimos": {(k, c) for k in ("saldo_m", "saldo_12m", "expo_12m", "impo_12m", "cobertura") for c in ("valor", "periodo", "periodo_txt", "variacion")},
}
COLUMNAS_LIBRES = {"mensual": {"tasa_real_personales", "tasa_real_personales_exante", "itcrm", "itcrb_bra", "itcrb_usa", "itcrb_chn", "itcrb_eur"}}
control("mismas tablas que la v1", set(base) == set(nuevo))
inesperados = []
total = 0
for n in base:
    b, a = tabla(base, n), tabla(nuevo, n)
    if n == "sectores_meta":
        b = [r for r in b if r["clave"] != "s68"]
    if len(b) != len(a):
        inesperados.append((n, "filas", len(b), len(a)))
        continue
    clave = list(b[0])[0]
    for rb, ra in zip(b, a):
        if rb[clave] != ra[clave]:
            inesperados.append((n, rb[clave], ra[clave]))
        for c in set(rb) | set(ra):
            if n == "sectores" and c == "s68":
                continue
            if c in COLUMNAS_LIBRES.get(n, ()):
                continue
            if rb.get(c) != ra.get(c):
                total += 1
                if (rb[clave], c) not in PERMITIDO.get(n, ()):
                    inesperados.append((n, rb[clave], c, rb.get(c), ra.get(c)))
control("no cambió ninguna celda fuera de lo permitido", not inesperados, f"celdas cambiadas={total}; inesperadas={inesperados[:5]}")

M = {r["mes"]: r for r in tabla(nuevo, "mensual")}
R = {r["mes"]: r for r in tabla(nuevo, "comercio_rubros")}
P = {r["mes"]: r for r in tabla(nuevo, "comercio_paises")}
S = tabla(nuevo, "sectores")
Mb = {r["mes"]: r for r in tabla(base, "mensual")}

# 2. Comercio.
mal = [m for m in R if not cerca(num(R[m]["x00"]), num(P[m]["x_tot"]), 1) and m >= "2017-01"]
control("x00 = x_tot desde 2017", not mal, str(mal[:6]))
control("x00 no repite valores en 2026", len({R[m]["x00"] for m in R if m.startswith("2026")}) == len([m for m in R if m.startswith("2026")]))
control("x01 no repite valores en 2026", len({R[m]["x01"] for m in R if m.startswith("2026")}) == len([m for m in R if m.startswith("2026")]))
control("mensual llega hasta el último mes de comercio", cerca(num(M["2026-09"]["expo"]), num(P["2026-09"]["x_tot"]), 0.1) and cerca(num(M["2026-09"]["impo"]), num(P["2026-09"]["m_tot"]), 0.1))
for mes in ("2026-08", "2026-09"):
    ven = [mover(mes, -i) for i in range(12)]
    control(f"expo_12m e impo_12m cierran en {mes}",
            cerca(num(M[mes]["expo_12m"]), sum(num(M[m]["expo"]) for m in ven), 0.2)
            and cerca(num(M[mes]["impo_12m"]), sum(num(M[m]["impo"]) for m in ven), 0.2))
ven = [mover("2026-07", -i) for i in range(12)]
control("la fórmula de 12 meses reproduce la v1 (jul 2026)", cerca(sum(num(Mb[m]["expo"]) for m in ven), num(Mb["2026-07"]["expo_12m"]), 0.5))
ca = {r["anio"]: r for r in tabla(nuevo, "comercio_anual")}
control("comercio_anual 2026 suma nueve meses", ca["2026"]["meses"] == "9" and cerca(num(ca["2026"]["expo"]), sum(num(M[f"2026-{i:02d}"]["expo"]) for i in range(1, 10)), 0.2))
kpi = {r["id"]: r for r in tabla(nuevo, "ultimos")}
control("KPI de comercio al último mes", all(kpi[k]["periodo"] == "2026-09" for k in ("saldo_m", "saldo_12m", "expo_12m", "impo_12m", "cobertura")))
control("KPI saldo mensual cierra", cerca(num(kpi["saldo_m"]["valor"]), num(M["2026-09"]["expo"]) - num(M["2026-09"]["impo"]), 0.11))

# 3. Sectores.
control("s68 eliminada", "s68" not in S[0] and all(r["clave"] != "s68" for r in tabla(nuevo, "sectores_meta")))
cols = [c for c in S[0] if c != "mes"]
series = {c: tuple(r[c] for r in S) for c in cols}
dup = [c for i, c in enumerate(cols) if series[c] in [series[x] for x in cols[:i]] and any(series[c])]
control("sin columnas sectoriales idénticas", not dup, str(dup))

# 4. Precios y tasas.
ipc = {m: num(r["ipc_index"]) for m, r in M.items() if num(r["ipc_index"])}
mal = [m for m in ipc if mover(m, -1) in ipc and num(M[m]["infl_mensual"]) is not None
       and not cerca((ipc[m] / ipc[mover(m, -1)] - 1) * 100, num(M[m]["infl_mensual"]), 0.15)]
control("infl_mensual coincide con ipc_index", not mal, str(mal))
r = M["2026-09"]
ven = [mover("2026-09", -i) for i in range(12)]
acum = 1.0
for m in ven:
    acum *= 1 + num(M[m]["tasa_personales"]) * 30 / 365 / 100
control("tasa real ex post a 12 meses", cerca((acum / (1 + num(r["infl_ia"]) / 100) - 1) * 100, num(r["tasa_real_personales"]), 0.01), f"{r['tasa_real_personales']}")
tea = (1 + num(r["tasa_personales"]) * 30 / 365 / 100) ** (365 / 30)
control("tasa real ex ante con REM", cerca((tea / (1 + num(r["rem_12m"]) / 100) - 1) * 100, num(r["tasa_real_personales_exante"]), 0.01), f"{r['tasa_real_personales_exante']}")

# 5. ITCRM.
itc = {m: num(x["itcrm"]) for m, x in M.items() if num(x["itcrm"])}
control("ITCRM desde 1997 hasta oct 2026", min(itc) == "1997-01" and max(itc) == "2026-10", f"{min(itc)}..{max(itc)} n={len(itc)}")
control("ITCRM sin huecos", len(itc) == (2026 - 1997) * 12 + 10)
control("ITCRM en rango razonable", 30 < min(itc.values()) and max(itc.values()) < 300, f"min={min(itc.values())} max={max(itc.values())}")

# 6. Página.
html = (RAIZ / "index.html").read_text(encoding="utf-8")
control("la página trae el ITCRM y su gráfico", 'id="c-itcrm"' in html and 'itcrm:{series' in html)
control("la página no referencia s68", "s68" not in html)

print(f"\n{'FALLARON ' + str(len(fallas)) + ' controles' if fallas else 'Todos los controles pasaron'}")
sys.exit(1 if fallas else 0)
