"""Reglas del calendario: qué período debería estar publicado y cuándo toca revisar cada fuente."""
import csv
import datetime as dt
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUENTES = RAIZ / "pipeline" / "fuentes"
DIAS_ATRASO = 30


def hoy_ar():
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)).date()


def cargar():
    return json.loads((RAIZ / "pipeline" / "calendario.json").read_text(encoding="utf-8"))


def _mes_mas(y, m, n):
    t = y * 12 + (m - 1) + n
    return t // 12, t % 12 + 1


def _fin_trimestre(y, q):
    yy, mm = _mes_mas(y, q * 3, 1)
    return dt.date(yy, mm, 1) - dt.timedelta(days=1)


def periodo_esperado(regla, hoy):
    """Último período que ya debería estar publicado en esa fecha."""
    if regla["tipo"] == "diaria":
        d = hoy
        while d.weekday() >= 5:
            d -= dt.timedelta(days=1)
        return d.isoformat()
    if regla["tipo"] == "mensual":
        atras = regla["rezago"] + (0 if hoy.day >= regla["dia"] else 1)
        y, m = _mes_mas(hoy.year, hoy.month, -atras)
        return f"{y:04d}-{m:02d}"
    y, q = hoy.year, (hoy.month + 2) // 3
    while _fin_trimestre(y, q) + dt.timedelta(days=regla["rezago_dias"]) > hoy:
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return f"{y}-T{q}"


def proxima_fecha(regla, ultimo):
    """Fecha en la que debería publicarse el período siguiente al último disponible."""
    if regla["tipo"] == "diaria":
        d = dt.date.fromisoformat(ultimo) + dt.timedelta(days=1)
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        return d
    if regla["tipo"] == "mensual":
        y, m = map(int, ultimo.split("-"))
        y, m = _mes_mas(y, m, 1 + regla["rezago"])
        return dt.date(y, m, regla["dia"])
    y, q = int(ultimo[:4]), int(ultimo[-1]) + 1
    if q == 5:
        y, q = y + 1, 1
    return _fin_trimestre(y, q) + dt.timedelta(days=regla["rezago_dias"])


def ultimo_periodo(fuente):
    """Período que tiene el archivo guardado. Con varias columnas, manda la más atrasada."""
    ruta = FUENTES / fuente["archivo"]
    if not ruta.exists():
        return None
    filas = list(csv.DictReader(ruta.read_text(encoding="utf-8").splitlines()))
    if not filas:
        return None
    if "fecha_col" in fuente:
        return max(f[fuente["fecha_col"]] for f in filas)
    if "fila_fecha" in fuente:
        corte = next(f["valor"] for f in filas if f["indicador"] == fuente["fila_fecha"])
        return f"{corte[:4]}-T{(int(corte[5:7]) + 2) // 3}"
    clave = list(filas[0])[0]
    if "columna_clave" in fuente:
        return max(f[clave] for f in filas if f[fuente["columna_clave"]] != "")
    ultimos = [max(f[clave] for f in filas if f[c] != "") for c in filas[0] if c != clave and any(f[c] != "" for f in filas)]
    return min(ultimos) if ultimos else None


def toca_revisar(fuente, hoy):
    """Devuelve (sí o no, motivo). Una fuente muy atrasada se revisa solo los lunes."""
    ultimo = ultimo_periodo(fuente)
    if ultimo is None:
        return True, "sin datos guardados"
    esperado = periodo_esperado(fuente["regla"], hoy)
    if ultimo >= esperado:
        return False, f"al día ({ultimo})"
    atraso = (hoy - proxima_fecha(fuente["regla"], ultimo)).days
    if atraso > DIAS_ATRASO and hoy.weekday() != 0:
        return False, f"atrasada {atraso} días; se revisa los lunes ({ultimo})"
    return True, f"tiene {ultimo} y debería tener {esperado}"


def texto_periodo(p):
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    if not p:
        return "—"
    if "-T" in p:
        return f"{p[-1]}.º trim. {p[:4]}"
    partes = p.split("-")
    if len(partes) == 2 and partes[1].isdigit():
        return f"{meses[int(partes[1]) - 1]} {partes[0]}"
    if len(partes) == 3:
        return f"{partes[2]}/{partes[1]}/{partes[0]}"
    return p
