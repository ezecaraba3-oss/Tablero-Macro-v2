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
control("conserva las tablas de la v1 y suma las nuevas", set(nuevo) - set(base) == {"deuda_perfil", "deuda_resumen"} and set(base) <= set(nuevo))
inesperados = []
total = 0
for n in base:
    b, a = tabla(base, n), tabla(nuevo, n)
    if n == "sectores_meta":
        b = [r for r in b if r["clave"] != "s68"]
    if n == "ultimos":
        previos = {r["id"] for r in b}
        a = [r for r in a if r["id"] in previos]
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
            if c in COLUMNAS_LIBRES.get(n, ()) or c not in rb:
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

# 6. Etapa 2: identidades contables.
def fuente(n):
    return list(csv.DictReader(io.StringIO((RAIZ / "pipeline" / "fuentes" / n).read_text(encoding="utf-8"))))


meses_d = [m for m, x in M.items() if num(x["deuda_bruta"])]
control("deuda desde ene 2019 hasta sep 2026", min(meses_d) == "2019-01" and max(meses_d) == "2026-09", f"{min(meses_d)}..{max(meses_d)}")
control("el último dato de deuda es el publicado", cerca(num(M["2026-09"]["deuda_bruta"]), 486627.5, 0.1))
mal = [m for m in meses_d if not cerca(num(M[m]["deuda_ley_arg"]) + num(M[m]["deuda_ley_ext"]), num(M[m]["deuda_bruta"]), 2)]
control("deuda por legislación = deuda bruta", not mal, str(mal[:5]))
partes = ["deuda_ars_fija", "deuda_ars_cer", "deuda_usd", "deuda_eur", "deuda_jpy", "deuda_deg", "deuda_otras"]
mal = [m for m in meses_d if not cerca(sum(num(M[m][c]) for c in partes), num(M[m]["deuda_normal"]), 2)]
control("deuda por moneda = deuda en pago normal", not mal, str(mal[:5]))
tasas_d = ["deuda_tasa_fija", "deuda_tasa_cero", "deuda_tasa_var"]
mal = [m for m in meses_d if not cerca(sum(num(M[m][c]) for c in tasas_d), num(M[m]["deuda_normal"]), 2)]
control("deuda por tasa = deuda en pago normal", not mal, str(mal[:5]))
mal = [m for m in meses_d if num(M[m]["deuda_fmi"]) > num(M[m]["deuda_org_int"])]
control("FMI dentro de organismos internacionales", not mal)
perfil = tabla(nuevo, "deuda_perfil")
control("perfil: capital + interés = total", all(cerca(num(r["capital"]) + num(r["interes"]), num(r["total"]), 0.3) for r in perfil))
A = {r["anio"]: r for r in tabla(nuevo, "anual")}
control("deuda / PIB plausible", all(20 < num(r["deuda_pib"]) < 200 for r in A.values() if num(r["deuda_pib"])), f"2025={A['2025']['deuda_pib']}")

F = fuente("fiscal_mensual.csv")
mal = [r["mes"] for r in F if not cerca(num(r["f_ingresos"]) - num(r["f_gastos"]), num(r["f_financiero"]), 5)]
control("fiscal: ingresos − gastos = resultado financiero", not mal, f"{len(mal)} meses {mal[:5]}")
fm = {m: x for m, x in M.items() if num(x["fis_financiero_pib"]) is not None}
control("fiscal llega al último PIB (jun 2026)", max(fm) == "2026-06", max(fm))
mal = [m for m, x in fm.items() if not cerca(num(x["fis_ingresos_pib"]) - num(x["fis_gastos_pib"]), num(x["fis_financiero_pib"]), 0.02)]
control("fiscal / PIB cierra", not mal, str(mal[:5]))
partes_g = ["fg_prestaciones", "fg_transf_priv", "fg_remuneraciones", "fg_bienes_serv", "fg_provincias", "fg_universidades", "fg_capital", "fg_resto", "fis_intereses_pib"]
mal = [(m, round(sum(num(x[c]) for c in partes_g) - num(x["fis_gastos_pib"]), 2)) for m, x in fm.items() if not cerca(sum(num(x[c]) for c in partes_g), num(x["fis_gastos_pib"]), 0.15)]
control("composición del gasto = gasto total", not mal, str(mal[:5]))
mal = [m for m, x in fm.items() if num(x["fg_transf_priv"]) < 0]
control("transferencias al sector privado (por diferencia) no negativas", not mal, str(mal[:5]))
prim_v1 = {m: num(x["res_primario_pib_12m"]) for m, x in fm.items() if num(x["res_primario_pib_12m"]) is not None}
dif = {m: abs(num(fm[m]["fis_superavit_pib"]) - v) for m, v in prim_v1.items()}
peor = max(dif, key=dif.get)
control("superávit primario = resultado primario de la v1", dif[peor] <= 0.02, f"dif máx {dif[peor]:.3f} pp en {peor}; jun 2026: {fm['2026-06']['fis_superavit_pib']} vs {prim_v1['2026-06']}")
control("resultado financiero 2025 plausible", -1 < num(M["2025-12"]["fis_financiero_pib"]) < 1, M["2025-12"]["fis_financiero_pib"])
control("ingresos / PIB plausibles", all(10 < num(x["fis_ingresos_pib"]) < 30 for x in fm.values()), M["2025-12"]["fis_ingresos_pib"])

T = {r["trimestre"]: r for r in tabla(nuevo, "trimestral") if "-T" in r["trimestre"] and num(r["cc"]) is not None}
mal = [t for t, r in T.items() if not cerca(num(r["cc_bienes"]) + num(r["cc_servicios"]) + num(r["cc_primario"]) + num(r["cc_secundario"]), num(r["cc"]), 0.3)]
control("cuenta corriente = suma de componentes", not mal, str(mal[:5]))
Sf = {r["trimestre"]: r for r in fuente("series_trimestrales.csv")}
mal = [(t, round(num(r["cc"]) + num(Sf[t]["cap"]) + num(Sf[t]["errores"]) - num(r["cfin"]), 1)) for t, r in T.items() if not cerca(num(r["cc"]) + num(Sf[t]["cap"]) + num(Sf[t]["errores"]), num(r["cfin"]), 2)]
control("balance de pagos: cc + capital + errores = financiera", not mal, f"{len(mal)} trimestres {mal[:5]}")
control("subocupación e informalidad en porcentaje", all(0 < num(r["subocupacion"]) < 40 for r in T.values() if num(r["subocupacion"])), f"ult={T[max(T)]['subocupacion']} / {T[max(T)]['asal_sin_desc']}")
print("INFO  cuenta corriente / PIB últimos:", [(t, T[t]["cc_pib_4t"]) for t in sorted(T)[-3:]])
ms = {m: x for m, x in M.items() if num(x["emp_total"])}
ult_e = max(ms)
sum_emp = sum(num(ms[ult_e][c]) for c in ["emp_privado", "emp_publico", "emp_casas", "emp_autonomos", "emp_monotributo", "emp_mono_social"])
control("empleo: las categorías suman cerca del total", abs(sum_emp / num(ms[ult_e]["emp_total"]) - 1) < 0.02, f"{sum_emp:.0f} vs {ms[ult_e]['emp_total']}")
res = {m: x for m, x in M.items() if num(x["res_compras"]) is not None}
control("BCRA sin meses posteriores a la tabla", max(res) <= "2026-10", max(res))
kp = {r["id"] for r in tabla(nuevo, "ultimos")}
control("indicadores nuevos presentes", {"deuda_bruta", "deuda_pib", "cc_4t", "iip", "fis_fin", "emp_total", "compras_12m"} <= kp)

# 7. Página.
html = (RAIZ / "index.html").read_text(encoding="utf-8")
control("la página trae el ITCRM y su gráfico", 'id="c-itcrm"' in html and 'itcrm:{series' in html)
control("la página no referencia s68", "s68" not in html)
control("la página trae las secciones nuevas", all(f'data-sec="{s}"' in html for s in ("deuda", "externo", "bcra")))

print(f"\n{'FALLARON ' + str(len(fallas)) + ' controles' if fallas else 'Todos los controles pasaron'}")
sys.exit(1 if fallas else 0)
