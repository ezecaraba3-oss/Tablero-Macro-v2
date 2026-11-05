"""Revisa el calendario y actualiza solo las fuentes vencidas.

    python pipeline/actualizar.py                     actualiza lo que toca hoy
    python pipeline/actualizar.py --simular 2026-12-05  muestra qué tocaría esa fecha, sin cambiar nada
    python pipeline/actualizar.py --probar bcra       prueba si responde un origen (para la tarea de GitHub)

Si algo cambia fuera de lo que le corresponde a las fuentes actualizadas, o falla un control,
se restauran los archivos y no se publica nada.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
import calendario as cal  # noqa: E402

RAIZ = DIR.parent
DATOS = RAIZ / "assets" / "datos.js"
INDEX = RAIZ / "index.html"
TABLAS_DERIVADAS = {"ultimos", "sostenibilidad", "calendario_datos"}
ORIGENES = {
    "datosgob": "https://apis.datos.gob.ar/series/api/search/?q=ipc&limit=1",
    "bcra": "https://api.bcra.gob.ar/estadisticas/v4.0/Monetarias/1?limit=1",
    "finanzas": "https://www.argentina.gob.ar/economia/finanzas/datos-mensuales",
    "fred": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS",
    "bcb": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.3698/dados/ultimos/1?formato=json",
    "argentinadatos": "https://api.argentinadatos.com/v1/finanzas/letras",
}


def huella(ruta):
    return hashlib.sha256(ruta.read_bytes()).hexdigest() if ruta.exists() else None


def leer_datos(ruta):
    raw = ruta.read_text(encoding="utf-8")
    obj, _ = json.JSONDecoder().raw_decode(raw[raw.index("{", raw.index("window.DATOS")):])
    return obj


def tabla(texto):
    return list(csv.DictReader(io.StringIO(texto)))


def columnas_cambiadas(antes, despues):
    cambios = set()
    for n in set(antes) | set(despues):
        if n not in antes or n not in despues:
            cambios.add((n, "*"))
            continue
        if antes[n] == despues[n]:
            continue
        a, b = tabla(antes[n]), tabla(despues[n])
        clave = list((a or b)[0])[0]
        ia, ib = {r[clave]: r for r in a}, {r[clave]: r for r in b}
        for k in set(ia) | set(ib):
            ra, rb = ia.get(k, {}), ib.get(k, {})
            for c in set(ra) | set(rb):
                if c != clave and (ra.get(c) or "") != (rb.get(c) or ""):
                    cambios.add((n, c))
    return cambios


def permitido(tab, col, fuentes):
    if tab in TABLAS_DERIVADAS:
        return True
    for f in fuentes:
        patron = f["salidas"].get(tab)
        if patron and (col == "*" or re.search(patron, col)):
            return True
    return False


def correr(script):
    r = subprocess.run([sys.executable, str(DIR / script)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    fallas = [l for l in r.stdout.splitlines() if l.startswith("FALLA")]
    return r.returncode == 0, fallas or r.stderr.splitlines()[-3:]


def escribir_calendario(hoy):
    obj = leer_datos(DATOS)
    filas = tabla(obj["calendario_datos"])
    lineas = ["# Calendario de actualización", "", f"Generado el {hoy.strftime('%d/%m/%Y')} con `pipeline/actualizar.py`. Las reglas están en `pipeline/calendario.json`.", "",
              "| Dato | Origen | Frecuencia | Último dato | Próxima revisión | Actualización |", "|---|---|---|---|---|---|"]
    lineas += [f"| {f['dato']} | {f['origen']} | {f['frecuencia']} | {f['ultimo']} | {f['proxima']} | {f['estado']} |" for f in filas]
    (RAIZ / "CALENDARIO.md").write_text("\n".join(lineas) + "\n", encoding="utf-8", newline="\n")


def main():
    args = sys.argv[1:]
    if args[:1] == ["--probar"]:
        with urllib.request.urlopen(urllib.request.Request(ORIGENES[args[1]], headers={"User-Agent": "tablero-macro-v2/1.0"}), timeout=60) as r:
            print(args[1], r.status)
        return
    simular = args[1] if args[:1] == ["--simular"] else None
    hoy = dt.date.fromisoformat(simular) if simular else cal.hoy_ar()
    fuentes = cal.cargar()["automaticas"]
    vencidas = []
    print(f"Calendario al {hoy.isoformat()}")
    for f in fuentes:
        toca, motivo = cal.toca_revisar(f, hoy)
        print(f"  {'REVISAR' if toca else 'omitir '} {f['id']}: {motivo}")
        if toca:
            vencidas.append(f)
    if simular or not vencidas:
        print("Sin cambios." if not simular else "Simulación: no se cambió nada.")
        return

    import descargar  # noqa: E402
    respaldo = Path(tempfile.mkdtemp())
    for r in [DATOS, INDEX]:
        shutil.copy2(r, respaldo / r.name)
    shutil.copytree(cal.FUENTES, respaldo / "fuentes")
    antes_csv = {p.name: huella(p) for p in cal.FUENTES.glob("*.csv")}
    antes = leer_datos(DATOS)

    def restaurar():
        shutil.copy2(respaldo / DATOS.name, DATOS)
        shutil.copy2(respaldo / INDEX.name, INDEX)
        shutil.rmtree(cal.FUENTES)
        shutil.copytree(respaldo / "fuentes", cal.FUENTES)

    fallidas = []
    for f in vencidas:
        try:
            descargar.FUENTES_POR_ID[f["id"]]()
        except Exception as e:  # una fuente caída no frena a las demás
            print(f"AVISO: {f['id']} no respondió: {type(e).__name__}: {e}")
            fallidas.append(f["id"])
    actualizadas = [f for f in vencidas if huella(cal.FUENTES / f["archivo"]) != antes_csv.get(f["archivo"]) or
                    (f["id"] == "deuda_trim" and any(huella(cal.FUENTES / n) != antes_csv.get(n) for n in ("deuda_anual.csv", "deuda_perfil.csv")))]
    print("Con datos nuevos:", [f["id"] for f in actualizadas] or "ninguna")
    cambiaron_otros = [n for n, h in antes_csv.items() if huella(cal.FUENTES / n) != h and n not in {f["archivo"] for f in actualizadas} and n not in ("deuda_anual.csv", "deuda_perfil.csv")]
    if not actualizadas and not cambiaron_otros:
        restaurar()
        print("Las fuentes revisadas todavía no publicaron nada nuevo." + (f" Sin respuesta: {fallidas}" if fallidas else ""))
        return

    ok, det = correr("construir.py")
    if not ok:
        restaurar()
        sys.exit(f"Falló la construcción: {det}")
    fuera = sorted(c for c in columnas_cambiadas(antes, leer_datos(DATOS)) if not permitido(c[0], c[1], actualizadas))
    if fuera:
        restaurar()
        sys.exit(f"Cancelado: cambiaron datos que no tocaba actualizar: {fuera[:20]}")
    version = huella(DATOS)[:8]
    html = INDEX.read_bytes().decode("utf-8")
    INDEX.write_bytes(re.sub(r"assets/datos\.js\?v=[\w-]+", f"assets/datos.js?v={version}", html).encode("utf-8"))
    for script in ("auditar.py", "verificar_pagina.py"):
        ok, det = correr(script)
        if not ok:
            restaurar()
            sys.exit(f"Cancelado por {script}: {det}")
    escribir_calendario(hoy)
    print("Actualización lista.")


if __name__ == "__main__":
    main()
