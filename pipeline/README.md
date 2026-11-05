# Proceso de datos

## Actualización diaria

Una tarea de GitHub (`.github/workflows/actualizar.yml`) corre una vez por día a las 18:00 de Argentina. Los datos diarios se actualizan en esa corrida los días hábiles; los mensuales y trimestrales entran en la misma corrida solo el día en que les toca, según `calendario.json`. Si una fuente demora, se revisa a diario, y tras 30 días de atraso, solo los lunes. Publica únicamente si hay datos nuevos y pasan todos los controles. Si cambia algo que no le corresponde a esa fuente, cancela y restaura los archivos.

```
python pipeline/actualizar.py                       # actualiza lo que toca hoy
python pipeline/actualizar.py --simular 2026-12-05  # muestra qué tocaría esa fecha, sin cambiar nada
```

`CALENDARIO.md` y la tarjeta «Cuándo se actualiza cada dato» muestran el estado de cada fuente. Las marcadas como pendientes todavía no tienen descarga automática.

## Comandos individuales

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

Las URL de la Secretaría de Finanzas se buscan en sus páginas oficiales; las de `descargar.py` quedan como respaldo.

Las correcciones apuntan a meses concretos de 2026 y 2017. Al renovar la base hay que revisarlas, y también la lista de cambios permitidos de `auditar.py`.
