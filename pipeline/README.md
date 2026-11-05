# Proceso de datos

Requiere Python 3, sin paquetes adicionales. Se corre desde la raíz del repo:

```
python pipeline/construir.py                     # arma assets/datos.js
python pipeline/construir.py --actualizar-itcrm  # además vuelve a bajar el ITCRM
python pipeline/descargar.py                     # baja deuda, balance de pagos, fiscal, empleo y BCRA
python pipeline/auditar.py                       # controles de datos; sale con código 1 si algo falla
python pipeline/verificar_pagina.py              # abre cada sección en Edge o Chrome y busca gráficos vacíos
```

- `base/datos_v1.js`: datos de la v1, sin modificar. No se edita.
- `fuentes/itcrm_mensual.csv`: copia del ITCRM del BCRA, para reconstruir sin conexión.
- `construir.py`: aplica las correcciones de `CORRECCIONES.md` sobre la base y agrega el ITCRM.
- `auditar.py`: controla que los datos cierren y que no cambie ninguna celda fuera de la lista prevista.

## Alcance actual

Se descargan automáticamente el ITCRM y todas las series de la etapa 2. Las series de la v1 siguen saliendo de la base congelada, porque ese repo no incluye sus scripts de descarga. Para actualizarlas hay que sumarlas a `descargar.py`.

Las URL de la Secretaría de Finanzas cambian con cada publicación: hay que renovarlas al comienzo de `descargar.py`. Al actualizar, también hay que revisar los controles con valores fijos de `auditar.py`, como el último dato de deuda.

Las correcciones apuntan a meses concretos de 2026 y 2017. Al renovar la base hay que revisarlas, y también la lista de cambios permitidos de `auditar.py`.
