# Correcciones de la v2 respecto de la v1

Base: commit `aefbf40` de Tablero-Macro. La copia de sus datos está en `pipeline/base/datos_v1.js`.
Para repetir el proceso, ver `pipeline/README.md`.

## Datos corregidos

| Dato | Problema | Qué se hizo |
|---|---|---|
| Exportaciones totales por rubro (`x00`), jun y ago 2026 | Repetía 9.054,99 en ambos meses | Se usa el total por países: 9.111,85 y 8.865,88 |
| Productos primarios (`x01`), ago 2026 | La fuente oficial repite el valor de junio (1.886,36) | Se usa la suma de sus subrubros: 1.731,24 |
| Subclase «Reparación e instalación» (`s68`) | Era una copia del IPI general; la serie está vacía en el catálogo oficial | Se quitó |
| Exportaciones e importaciones en `mensual`, ago 2026 | Versión anterior a la revisión del INDEC | Expo 8.865,9 e impo 6.706,6, como en `comercio_paises` |
| Comercio en `mensual`, `inv_mensual`, `comercio_anual` e indicadores | Llegaban hasta agosto aunque ya estaba septiembre | Se sumó sep 2026: expo 10.036, impo 7.059,5, saldo 2.976,5 |
| Inflación mensual, ene y feb 2017 | Usaba 1,3 y 2,5, distintos del IPC nacional del propio índice | Pasa a 1,6 y 2,1, y se recalculó la tasa real de esos meses |

## Método cambiado

- **Tasa real de préstamos personales (`tasa_real_personales`).** Antes dividía una tasa anualizada actual por la inflación de los 12 meses anteriores. Ahora capitaliza las 12 tasas mensuales anteriores y descuenta la inflación del mismo período. Sep 2026: de 37,8 % a 45,6 %.
- **Tasa real esperada de préstamos (`tasa_real_personales_exante`).** Es nueva: usa la TEA y el REM a 12 meses, desde 2017. Sep 2026: 51,8 %.

## Datos agregados

- **ITCRM y bilaterales con Brasil, EE. UU., China y zona euro.** Planilla del BCRA, mensual desde enero de 1997. Datos provisorios.
- La relación entre dólar real y saldo comercial ahora usa el ITCRM, así que empieza en 1997.
- «Dólar oficial real» pasa a llamarse «Dólar oficial deflactado por IPC», porque no descuenta la inflación de EE. UU.

## Revisado y sin cambios

- **Energía eléctrica (`xd46`), sep 2021.** El valor de 257,82 M coincide con la fuente oficial, aunque los subrubros superen al total de combustibles y energía.
- **Importaciones de 2008 y 2016.** `mensual` y `comercio_rubros` difieren de `comercio_paises` y de la API en 12 meses. Falta decidir cuál usar.
- **Stock de IED, 1.er trim. 2026.** Sube 19.172 M con un flujo de 2.834 M, y el total (202.033 M) difiere del desglose (200.611 M). La serie consultada en la API vino vacía, así que sigue sin verificar y se avisa en la página.
- **Series cortadas.** Expectativas UTDT, neumáticos y otros productos de caucho terminan en enero de 2026; el gasto consolidado, en 2023. Se avisa en la página.
