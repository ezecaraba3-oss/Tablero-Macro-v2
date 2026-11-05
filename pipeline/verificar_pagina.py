"""Abre cada sección en Edge o Chrome sin ventana y controla que los gráficos se dibujen.

    python pipeline/verificar_pagina.py

Sale con código 1 si un gráfico queda vacío o sin dibujar, o si hay errores de JavaScript.
Algunos gráficos no tienen datos en el período por defecto: se listan en SIN_DATOS_ESPERADO.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = Path(__file__).resolve().parent.parent
NAVEGADORES = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
               r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
               r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
SIN_DATOS_ESPERADO = set()

nav = next((n for n in NAVEGADORES if Path(n).exists()), None)
if not nav:
    sys.exit("No encontré Edge ni Chrome")
html = (RAIZ / "index.html").read_text(encoding="utf-8")
secciones = re.findall(r'<section data-sec="(\w+)"', html)
url = (RAIZ / "index.html").as_uri()
fallas = []
with tempfile.TemporaryDirectory() as perfil:
    for sec in secciones:
        r = subprocess.run([nav, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={perfil}", "--enable-logging=stderr",
                            "--virtual-time-budget=15000", "--window-size=1400,3000", "--dump-dom", f"{url}#{sec}"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        dom = r.stdout
        ini = dom.find(f'<section data-sec="{sec}"')
        fin = dom.find("</section>", ini)
        cuerpo = dom[ini:fin]
        tarjetas = re.findall(r'<article class="card[^"]*" id="(c-[^"]+)".*?</article>', cuerpo, flags=re.S)
        vacias, sin_svg = [], []
        for m in re.finditer(r'<article class="card[^"]*" id="(c-[^"]+)".*?</article>', cuerpo, flags=re.S):
            art, cid = m.group(0), m.group(1)
            for ch in re.finditer(r'<div class="chart"[^>]*>(.*?)(?=<details|</article>)', art, flags=re.S):
                if "Sin datos" in ch.group(1):
                    vacias.append(cid)
                elif "<svg" not in ch.group(1):
                    sin_svg.append(cid)
        errores = [l for l in r.stderr.splitlines() if re.search(r"Uncaught|Error en el dibujo", l)]
        ok = not (set(vacias) - SIN_DATOS_ESPERADO or sin_svg or errores or ini < 0)
        print(("OK    " if ok else "FALLA ") + f"{sec}: {len(tarjetas)} tarjetas" + (f" | vacías={vacias}" if vacias else "") + (f" | sin dibujo={sin_svg}" if sin_svg else "") + (f" | errores={errores[:2]}" if errores else ""))
        if not ok:
            fallas.append(sec)
print("\nTodas las secciones se dibujan" if not fallas else f"\nFALLARON: {fallas}")
sys.exit(1 if fallas else 0)
