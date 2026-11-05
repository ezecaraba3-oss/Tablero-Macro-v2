# Proceso de datos

Requiere Python 3, sin paquetes adicionales. Se corre desde la raíz del repo:

```
python pipeline/construir.py                     # arma assets/datos.js
python pipeline/construir.py --actualizar-itcrm  # además vuelve a bajar el ITCRM
python pipeline/auditar.py                       # controles; sale con código 1 si algo falla
```

- `base/datos_v1.js`: datos de la v1, sin modificar. No se edita.
- `fuentes/itcrm_mensual.csv`: copia del ITCRM del BCRA, para reconstruir sin conexión.
- `construir.py`: aplica las correcciones de `CORRECCIONES.md` sobre la base y agrega el ITCRM.
- `auditar.py`: controla que los datos cierren y que no cambie ninguna celda fuera de la lista prevista.

## Alcance actual

Solo el ITCRM se descarga automáticamente. El resto de las series sale de la base de la v1, porque ese repo no incluye sus scripts de descarga. Para actualizarlas hay que incorporar su descarga a `construir.py`.

Las correcciones apuntan a meses concretos de 2026 y 2017. Al renovar la base hay que revisarlas, y también la lista de cambios permitidos de `auditar.py`.
