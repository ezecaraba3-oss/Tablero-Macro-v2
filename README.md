# Tablero Macro 2.0 · Argentina

Versión en desarrollo, separada de [Tablero-Macro](https://github.com/ezecaraba3-oss/Tablero-Macro). Los cambios respecto de esa versión están en `CORRECCIONES.md`.

Tablero de indicadores económicos y sociales de Argentina desde 1875: inflación, tasas, dólar, salarios, pobreza, actividad, comercio exterior, cuentas públicas, balance del gobierno actual y comparación entre gobiernos.

## Archivos

- `index.html`: la página.
- `assets/datos.js`: todos los datos (series en formato CSV). Se genera con `pipeline/construir.py`; no se edita a mano.
- `pipeline/`: construcción y controles de los datos. Ver `pipeline/README.md`.
- `CORRECCIONES.md`: qué se corrigió, qué se agregó y qué sigue pendiente.
- `assets/dash.js`: el motor que lee los datos y dibuja los gráficos.
- `assets/d3.v7.9.0.min.js`: la librería de gráficos (D3, licencia ISC).

## Publicar con GitHub Pages

1. Subí todo el contenido de esta carpeta a la raíz de un repositorio público.
2. En el repositorio: Settings → Pages → Build and deployment → Source: «Deploy from a branch», rama `main`, carpeta `/ (root)` → Save.
3. En uno o dos minutos queda en `https://TU-USUARIO.github.io/NOMBRE-DEL-REPO/`.

## Fuentes

INDEC, BCRA, Ministerio de Economía, ARCA, ANSES, UTDT, ArgentinaDatos, Banco Mundial y Maddison Project Database (vía Our World in Data). Datos al 31 de octubre de 2026. Detalle de fuentes, empalmes y método en la sección «Fuentes y método» del sitio.

No constituye asesoramiento financiero.
