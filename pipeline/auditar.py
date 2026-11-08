"""Controles de calidad de assets/datos.js. Sale con código 1 si alguno falla.

Además compara contra la base de la v1: toda celda que cambie fuera de la lista
de cambios permitidos se considera un error.
"""
import csv
import io
import json
import re
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


def fuente(n):
    return list(csv.DictReader(io.StringIO((RAIZ / "pipeline" / "fuentes" / n).read_text(encoding="utf-8"))))


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
    | {(m, c) for m in ("2017-01", "2017-02") for c in ("infl_mensual", "tasa_real_pf_m")}
    # Octubre de 2026 estaba incompleto en la v1: se reemplaza por el cierre del mes.
    | {("2026-10", c) for c in ("tc_a3500", "reservas", "badlar", "tasa_pf30", "tasa_personales", "banda_inf", "banda_sup", "dolar_blue", "dolar_ccl", "riesgo_pais", "tc_m", "tc_ia", "brecha_ccl", "brecha_mep", "brecha_blue", "tem_pf", "dist_techo", "dist_piso")},
    "comercio_rubros": {("2026-06", "x00"), ("2026-08", "x00"), ("2026-08", "x01")},
    "inv_mensual": {(m, c) for m in ("2026-08", "2026-09") for c in ("impo", "ar_efec", "ar_efec_12m")},
    "comercio_anual": {("2026", c) for c in ("expo", "impo", "saldo", "cobertura", "meses", "periodo")},
    "ultimos": {(k, c) for k in ("saldo_m", "saldo_12m", "expo_12m", "impo_12m", "cobertura") for c in ("valor", "periodo", "periodo_txt", "variacion")} | {(k, c) for k in ("reservas", "tc", "infl_m", "infl_ia", "rem_12m", "tasa_real", "brecha_ccl", "riesgo") for c in ("valor", "periodo", "periodo_txt", "variacion", "variacion_txt")}
    | {(k, c) for k in ("sal_real", "emae", "recaud_real", "presion", "desempleo") for c in ("valor", "periodo", "periodo_txt", "variacion", "estado")},
}
COLUMNAS_LIBRES = {"mensual": {"tc_pesos_hoy", "tasa_real_personales", "tasa_real_personales_exante", "itcrm", "itcrb_bra", "itcrb_usa", "itcrb_chn", "itcrb_eur"}}
control("conserva las tablas de la v1 y suma las nuevas", set(nuevo) - set(base) == {"deuda_perfil", "deuda_resumen", "curva_pesos", "sostenibilidad", "calendario_datos", "diario"} and set(base) <= set(nuevo))
inesperados = []
total = 0
for n in base:
    b, a = tabla(base, n), tabla(nuevo, n)
    if n == "sectores_meta":
        b = [r for r in b if r["clave"] != "s68"]
    clave_t = list(b[0])[0]
    previos = {r[clave_t] for r in b}
    a = [r for r in a if r[clave_t] in previos]  # las filas nuevas no existen en la v1
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
                if not rb.get(c) and n in ("mensual", "inv_mensual") and rb[clave] >= "2025-10":
                    continue  # completar celdas vacías recientes no pisa datos de la v1
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
ult_c = max(P)
control("mensual llega hasta el último mes de comercio", cerca(num(M[ult_c]["expo"]), num(P[ult_c]["x_tot"]), 0.1) and cerca(num(M[ult_c]["impo"]), num(P[ult_c]["m_tot"]), 0.1), ult_c)
for mes in sorted(m for m in P if m >= "2026-08"):
    ven = [mover(mes, -i) for i in range(12)]
    control(f"expo_12m e impo_12m cierran en {mes}",
            cerca(num(M[mes]["expo_12m"]), sum(num(M[m]["expo"]) for m in ven), 0.2)
            and cerca(num(M[mes]["impo_12m"]), sum(num(M[m]["impo"]) for m in ven), 0.2))
ven = [mover("2026-07", -i) for i in range(12)]
control("la fórmula de 12 meses reproduce la v1 (jul 2026)", cerca(sum(num(Mb[m]["expo"]) for m in ven), num(Mb["2026-07"]["expo_12m"]), 0.5))
ca = {r["anio"]: r for r in tabla(nuevo, "comercio_anual")}
n_c = int(ult_c[5:])
control(f"comercio_anual {ult_c[:4]} suma {n_c} meses", ca[ult_c[:4]]["meses"] == str(n_c) and cerca(num(ca[ult_c[:4]]["expo"]), sum(num(M[f"{ult_c[:4]}-{i:02d}"]["expo"]) for i in range(1, n_c + 1)), 0.2))
kpi = {r["id"]: r for r in tabla(nuevo, "ultimos")}
control("KPI de comercio al último mes", all(kpi[k]["periodo"] == ult_c for k in ("saldo_m", "saldo_12m", "expo_12m", "impo_12m", "cobertura")))
control("KPI saldo mensual cierra", cerca(num(kpi["saldo_m"]["valor"]), num(M[ult_c]["expo"]) - num(M[ult_c]["impo"]), 0.11))
tot_f = {x["mes"]: x for x in fuente("comercio_mensual.csv")}
nuevos_c = [m for m in P if m > max(r["mes"] for r in tabla(base, "comercio_paises"))]
mal = [m for m in nuevos_c if not (cerca(num(P[m]["x_tot"]), num(tot_f[m]["expo"]), 0.01) and cerca(num(R[m]["m00"]), num(tot_f[m]["impo"]), 0.01))]
control("comercio: meses nuevos iguales a INDEC", not mal, f"nuevos={nuevos_c}; {mal[:3]}")
mal = [m for m in nuevos_c if P[m]["x_bra"] and not cerca(sum(num(P[m][f"x_{k}"]) for k in ("bra", "pry", "ury", "ven")), num(P[m]["x_bmcs"]), 0.05)]
control("comercio: Mercosur = suma de sus países en los meses nuevos", not mal, str(mal))
mal = [m for m in nuevos_c if R[m]["x01"] and not cerca(sum(num(R[m][f"x0{i}"]) for i in range(1, 5)), num(R[m]["x00"]), 1)]
control("comercio: los grandes rubros suman el total en los meses nuevos", not mal, str(mal))

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
control("ITCRM desde 1997 hasta oct 2026 o más", min(itc) == "1997-01" and max(itc) >= "2026-10", f"{min(itc)}..{max(itc)} n={len(itc)}")
control("ITCRM sin huecos", len(itc) == (int(max(itc)[:4]) - 1997) * 12 + int(max(itc)[5:]))
control("ITCRM en rango razonable", 30 < min(itc.values()) and max(itc.values()) < 300, f"min={min(itc.values())} max={max(itc.values())}")

# 6. Etapa 2: identidades contables.
meses_d = [m for m, x in M.items() if num(x["deuda_bruta"])]
control("deuda desde ene 2019 hasta sep 2026 o más", min(meses_d) == "2019-01" and max(meses_d) >= "2026-09", f"{min(meses_d)}..{max(meses_d)}")
dm = fuente("deuda_mensual.csv")
control("el último dato de deuda es el de la fuente", cerca(num(M[max(meses_d)]["deuda_bruta"]), num(dm[-1]["deuda_bruta"]), 0.1))
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
control("fiscal llega a jun 2026 o más", max(fm) >= "2026-06", max(fm))
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
cal_d = tabla(nuevo, "calendario_datos")
control("calendario completo", len(cal_d) == 25 and sum(x["estado"] == "Automática" for x in cal_d) == 23, str(len(cal_d)))
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
import datetime as dt
control("BCRA solo con meses cerrados", max(res) < dt.date.today().strftime("%Y-%m"), max(res))
kp = {r["id"] for r in tabla(nuevo, "ultimos")}
control("indicadores nuevos presentes", {"deuda_bruta", "deuda_pib", "cc_4t", "iip", "fis_fin", "emp_total", "compras_12m"} <= kp)

# 7. Etapa 3.
Tt = {r["trimestre"]: r for r in tabla(nuevo, "trimestral") if "-T" in r["trimestre"]}
Inv = {r["trimestre"]: r for r in tabla(nuevo, "inv_trim")}
mal = [t for t, r in Tt.items() if num(r["d_pib"]) and t in Inv and not cerca(num(r["d_pib"]), num(Inv[t]["pib_r"]), 1)]
control("PIB real de demanda = PIB real de inversión", not mal, str(mal[:5]))
partes_ct = ["ct_cons_priv", "ct_cons_pub", "ct_ibif", "ct_expo", "ct_impo", "ct_resto"]
ct = {t: r for t, r in Tt.items() if num(r["ct_cons_priv"]) is not None}
mal = [t for t, r in ct.items() if not cerca(sum(num(r[c]) for c in partes_ct), num(r["pib_ia"]), 0.05)]
control("contribuciones = crecimiento del PIB", not mal, f"{len(ct)} trimestres; {mal[:5]}")
peor = max(abs(num(r["ct_resto"])) for r in ct.values())
print(f"INFO  existencias y discrepancia, mayor aporte absoluto: {peor:.1f} pp")
for col, lo, hi in (("uci", 30, 90), ("soja", 150, 900), ("brent", 5, 200), ("maiz", 50, 500), ("trigo", 80, 700), ("fed_funds", 0, 25), ("ust10", 0, 20), ("brl", 0.5, 8), ("selic", 1, 100), ("ibcbr", 50, 150)):
    v = {m: num(x[col]) for m, x in M.items() if num(x[col]) is not None}
    control(f"{col} en rango", lo <= min(v.values()) and max(v.values()) <= hi, f"{min(v)}..{max(v)} min={min(v.values()):.2f} max={max(v.values()):.2f}")
cv = {m: num(x["credito_pib"]) for m, x in M.items() if num(x["credito_pib"]) is not None}
control("crédito / PIB plausible", 2 < min(cv.values()) and max(cv.values()) < 30, f"{min(cv)}..{max(cv)} ult={cv[max(cv)]}")
curva = tabla(nuevo, "curva_pesos")
control("curva ordenada por plazo", [int(x["dias"]) for x in curva] == sorted(int(x["dias"]) for x in curva) and len(curva) >= 5, f"{len(curva)} títulos al {curva[0]['fecha']}")
control("curva en rango", all(0 < num(x["tem"]) < 15 for x in curva))
sost = tabla(nuevo, "sostenibilidad")
control("sostenibilidad completa", len(sost) == 12 and all(x["lectura"] in ("Mejoró", "Empeoró", "Sin cambios") for x in sost))
# Los enteros no deben perder ceros al formatearse.
rc = {m: num(x["res_compras"]) for m, x in M.items() if num(x["res_compras"]) is not None}
mal = [m for m, x in M.items() if num(x["res_compras_12m"]) is not None and not cerca(num(x["res_compras_12m"]), sum(rc[mover(m, -i)] for i in range(12)), 12)]
control("compras de 12 meses = suma de compras mensuales", not mal, str(mal[:5]))
fuente_c = {r["mes"]: num(r["prestamos_priv"]) for r in fuente("credito_mensual.csv")}
mal = [m for m, x in M.items() if num(x["prestamos_priv"]) and not cerca(num(x["prestamos_priv"]), fuente_c[m], 1)]
control("préstamos iguales a la fuente", not mal, str(mal[:5]))
fila_r = next(x for x in sost if x["indicador"] == "Riesgo país")
ult_r = max(m for m, x in M.items() if num(x["riesgo_pais"]) is not None)
control("sostenibilidad: riesgo país coherente", cerca(num(fila_r["valor"]), num(M[ult_r]["riesgo_pais"]), 1), fila_r["valor"])
control("curva sin rendimientos negativos", all(num(x["tem"]) > 0 for x in curva))

# Mercado: el método debe reproducir la v1 y el cierre de octubre, la fuente.
mm = {x["mes"]: x for x in fuente("mercado_mensual.csv")}
control("octubre cerrado con el dato completo", cerca(num(M["2026-10"]["reservas"]), num(mm["2026-10"]["reservas"]), 0.5) and cerca(num(M["2026-10"]["riesgo_pais"]), num(mm["2026-10"]["riesgo_pais"]), 0.01), f"reservas {M['2026-10']['reservas']}, riesgo {M['2026-10']['riesgo_pais']}")
x = M["2026-10"]
control("brecha y distancia a la banda cierran", cerca(num(x["brecha_blue"]), (num(x["dolar_blue"]) / num(x["tc_a3500"]) - 1) * 100, 0.01) and cerca(num(x["dist_techo"]), (num(x["banda_sup"]) / num(x["tc_a3500"]) - 1) * 100, 0.01))
control("plazo fijo renovado encadena", cerca(num(x["pf_index"]), num(M["2026-09"]["pf_index"]) * (1 + num(M["2026-09"]["tem_pf"]) / 100), 0.05))
dia = tabla(nuevo, "diario")
control("datos diarios completos y con fecha", len(dia) == 10 and all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", z["fecha"]) and num(z["valor"]) for z in dia), f"hasta {max(z['fecha'] for z in dia)}")

# EMAE y salarios: los meses nuevos salen de INDEC y empalman con la v1.
em = {x["mes"]: x for x in fuente("emae_mensual.csv")}
nuevos = [m for m in M if num(M[m]["emae_desest"]) is not None and not num(Mb.get(m, {}).get("emae_desest") or None)]
mal = [m for m in nuevos if not (cerca(num(M[m]["emae_desest"]), num(em[m]["emae_desest"]), 0.001) and cerca(num(M[m]["emae_ia"]), num(em[m]["emae_ia"]), 0.0001))]
control("EMAE: meses nuevos iguales a INDEC", not mal, f"nuevos={nuevos}; {mal[:5]}")
ult_v1 = max(m for m, x in Mb.items() if num(x["emae_desest"]) is not None)
control("EMAE: la v1 y INDEC coinciden en el último mes común", cerca(num(Mb[ult_v1]["emae_desest"]), num(em[ult_v1]["emae_desest"]), 0.5), f"{ult_v1}: {Mb[ult_v1]['emae_desest']} vs {em[ult_v1]['emae_desest']}")
sa = {x["mes"]: x for x in fuente("salarios_mensual.csv")}
mal = []
for col, nominal in (("sal_real", "is_total"), ("sal_priv_real", "is_priv_reg"), ("sal_pub_real", "is_publico")):
    k = {m: num(M[m][col]) / (num(sa[m][nominal]) / num(M[m]["ipc_index"])) for m in M if m >= "2024-01" and m in sa and num(M[m][col]) and num(sa[m][nominal]) and num(M[m]["ipc_index"])}
    if max(k.values()) / min(k.values()) - 1 > 0.002:
        mal.append((col, round(min(k.values()), 5), round(max(k.values()), 5)))
control("salario real: el empalme con INDEC no tiene saltos", not mal, str(mal))
ult_s = max(m for m, x in M.items() if num(x["sal_ia"]) is not None)
control("salarios: variación interanual igual a INDEC", cerca(num(M[ult_s]["sal_ia"]), (num(sa[ult_s]["is_total"]) / num(sa[mover(ult_s, -12)]["is_total"]) - 1) * 100, 0.01), f"{ult_s}: {M[ult_s]['sal_ia']}")
control("KPI de EMAE y salario al último mes", kpi["emae"]["periodo"] == max(m for m, x in M.items() if num(x["emae_ia"]) is not None) and kpi["sal_real"]["periodo"] == max(m for m, x in M.items() if num(x["sal_real"]) is not None))

# Sectores e IPI: los meses nuevos salen de INDEC.
Sb = {r["mes"]: r for r in tabla(base, "sectores")}
Sn = {r["mes"]: r for r in S}
ipi_f = {x["mes"]: x for x in fuente("ipi_sectores.csv")}
ema_f = {x["mes"]: x for x in fuente("emae_sectores.csv")}
nuevos = sorted(set(Sn) - set(Sb))
mal = [(m, c) for m in nuevos for c, v in Sn[m].items() if c != "mes" and v != "" and not cerca(num(v), num((ipi_f if c[0] in "is" else ema_f)[m][c]), 0.001)]
control("sectores: meses nuevos iguales a INDEC", not mal, f"nuevos={nuevos}; {mal[:5]}")
ult = max(Sb)
dif = max(abs(num(Sb[ult][c]) / num(ipi_f[ult][c]) - 1) for c in ("i00", "i01", "i04", "i07", "i14") if num(ipi_f[ult][c]))
control("IPI: la v1 y INDEC coinciden en el último mes común (revisión menor al 2 %)", dif < 0.02, f"{ult}: {dif:.4f}")
ipi_m = {x["mes"]: x for x in fuente("ipi_mensual.csv")}
ult_i = max(m for m, x in M.items() if num(x["ipi_desest"]) is not None)
control("IPI mensual al día con INDEC", ult_i == max(ipi_m) and cerca(num(M[ult_i]["ipi_ia"]), num(ipi_m[ult_i]["ipi_ia"]), 0.0001), ult_i)

# Consumo: los meses nuevos salen de INDEC.
Cb = {r["mes"]: r for r in tabla(base, "consumo_rubros")}
Cn = {r["mes"]: r for r in tabla(nuevo, "consumo_rubros")}
cf = {x["mes"]: x for x in fuente("consumo_rubros.csv")}
nuevos = [m for m in Cn if m not in Cb]
mal = [(m, c) for m in nuevos for c in Cn[m] if c[:2] in ("sp", "my", "sh") and c not in ("sh_real",) and Cn[m][c] != "" and not cerca(num(Cn[m][c]), num(cf[m][c]), 0.01)]
control("consumo: meses nuevos iguales a INDEC", not mal, f"nuevos={nuevos}; {mal[:4]}")
mal = [(m, p) for m in nuevos for p, n in (("sp", 11), ("my", 10), ("sh", 10)) if Cn[m][f"{p}00"] and not cerca(sum(num(Cn[m][f"{p}{i:02d}"]) or 0 for i in range(1, n + 1)), num(Cn[m][f"{p}00"]), num(Cn[m][f"{p}00"]) * 0.01)]
control("consumo: los rubros suman el total en los meses nuevos", not mal, str(mal))
ult = max(Cb)
control("consumo: la v1 y INDEC coinciden en el último mes común", all(cerca(num(Cb[ult][c]), num(cf[ult][c]), 1) for c in ("sp00", "my00", "sh00", "sp_real", "my_real")), ult)

# Recaudación: los meses nuevos salen de ARCA y las fórmulas reproducen la v1.
rf = {x["mes"]: x for x in fuente("recaudacion_mensual.csv")}
In = {r["mes"]: r for r in tabla(nuevo, "inv_mensual")}
Ib = {r["mes"]: r for r in tabla(base, "inv_mensual")}
nuevos = [m for m in In if not (Ib.get(m, {}).get("der_imp"))]
mal = [m for m in nuevos if In[m]["der_imp"] and not (cerca(num(In[m]["der_imp"]), num(rf[m]["der_imp"]), 0.01) and cerca(num(In[m]["der_exp"]), num(rf[m]["der_exp"]), 0.01))]
control("recaudación: derechos nuevos iguales a ARCA", not mal, f"nuevos={nuevos}; {mal[:3]}")
comunes = [m for m in rf if Ib.get(m, {}).get("der_imp")]
mal = [m for m in comunes if not (cerca(num(Ib[m]["der_imp"]), num(rf[m]["der_imp"]), 1) and cerca(num(Ib[m]["der_exp"]), num(rf[m]["der_exp"]), 1))]
control("recaudación: ARCA reproduce los derechos de la v1", not mal, f"{len(comunes)} meses; {mal[:3]}")
tr = {m: num(x["tributarios"]) for m, x in rf.items()}
dif = {m: abs((tr[m] / tr[mover(m, -12)] / (num(Mb[m]["ipc_index"]) / num(Mb[mover(m, -12)]["ipc_index"])) - 1) * 100 - num(Mb[m]["recaudacion_real_ia"]))
       for m in rf if mover(m, -12) in tr and num(Mb.get(m, {}).get("recaudacion_real_ia")) is not None}
control("recaudación real: la fórmula reproduce la v1", dif and max(dif.values()) < 0.1, f"{len(dif)} meses; dif máx {max(dif.values()):.3f} pp")

# EPH: la API reproduce la v1 y los trimestres nuevos salen de ella.
ef = {x["trimestre"]: x for x in fuente("eph_trimestral.csv")}
Tb = {r["trimestre"]: r for r in tabla(base, "trimestral") if "-T" in r["trimestre"]}
comunes = [t for t in ef if num(Tb.get(t, {}).get("desempleo")) is not None and t >= "2016-T2"]
mal = [t for t in comunes for c in ("desempleo", "actividad", "empleo") if not cerca(num(Tb[t][c]), num(ef[t][c]), 0.051)]
control("EPH: la API reproduce la v1 desde 2016", not mal, f"{len(comunes)} trimestres; {mal[:4]}")
nuevos = [t for t in ef if t in Tt and num(Tb.get(t, {}).get("desempleo")) is None and num(Tt[t]["desempleo"]) is not None]
mal = [t for t in nuevos if not cerca(num(Tt[t]["desempleo"]), num(ef[t]["desempleo"]), 0.051)]
control("EPH: trimestres nuevos iguales a la API", not mal, f"nuevos={nuevos}")

# Inversión: INDEC reproduce la v1 y las derivadas siguen su método.
inv_f = {x["trimestre"]: x for x in fuente("inversion_trimestral.csv")}
Ivb = {r["trimestre"]: r for r in tabla(base, "inv_trim")}
Ivn = {r["trimestre"]: r for r in tabla(nuevo, "inv_trim")}
# 2004: la v1 toma el total del cuadro 1 (difiere del cuadro 6 en menos de 0,01 %).
mal = [(t, c) for t in inv_f if t in Ivb and t >= "2005" for c in inv_f[t] if c != "trimestre" and num(Ivb[t].get(c)) is not None and inv_f[t][c] != ""
       and not cerca(num(Ivb[t][c]), num(inv_f[t][c]), max(0.01, abs(num(Ivb[t][c])) * 1e-6))]
control("inversión: INDEC y la API reproducen la v1", not mal, f"{len([t for t in inv_f if t in Ivb])} trimestres; {mal[:4]}")
sys.path.insert(0, str(RAIZ / "pipeline"))
import construir as _c  # noqa: E402
ts_b = sorted(Ivb)
mal = []
for t in ts_b:
    for c, v in _c.derivadas_inversion(Ivb, t, ts_b).items():
        if num(Ivb[t].get(c)) is not None and not cerca(v, num(Ivb[t][c]), 0.002 + abs(v) * 1e-4):
            mal.append((t, c, Ivb[t][c], round(v, 3)))
control("inversión: las fórmulas de las derivadas reproducen la v1", not mal, f"{mal[:4]}")
nuevos = [t for t in Ivn if t not in Ivb]
mal = [t for t in nuevos if not cerca(num(Ivn[t]["r_tot"]), num(inv_f[t]["r_tot"]), 0.01)]
control("inversión: trimestres nuevos iguales a INDEC", not mal, f"nuevos={nuevos}")

# 8. Página.
html = (RAIZ / "index.html").read_text(encoding="utf-8")
control("la página trae el ITCRM y su gráfico", 'id="c-itcrm"' in html and 'itcrm:{series' in html)
control("la página no referencia s68", "s68" not in html)
control("la página trae las secciones nuevas", all(f'data-sec="{s}"' in html for s in ("deuda", "externo", "bcra", "global", "sostenibilidad")))

print(f"\n{'FALLARON ' + str(len(fallas)) + ' controles' if fallas else 'Todos los controles pasaron'}")
sys.exit(1 if fallas else 0)
