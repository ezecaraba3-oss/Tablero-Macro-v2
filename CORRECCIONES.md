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

## Etapa 2: variables agregadas

Cada fuente se baja con `pipeline/descargar.py` y queda guardada en `pipeline/fuentes/`.

| Área | Qué se sumó | Fuente | Período |
|---|---|---|---|
| Deuda (sección nueva) | Stock por moneda, tasa, legislación e instrumento; FMI y organismos; pagos; vencimientos; ratios | Secretaría de Finanzas | Mensual desde 2019; ratios desde 2000; vencimientos al 30 jun 2026 |
| Sector externo (sección nueva) | Cuenta corriente, cuenta financiera, posición internacional, turismo | INDEC y BCRA vía datos.gob.ar | Desde 2006; posición desde 2016; turismo desde 2003 |
| BCRA (sección nueva) | Factores de variación de reservas, compras de divisas, depósitos y préstamos en dólares, pases y LELIQ | API del BCRA | Desde 2010 |
| Fiscal (ampliada) | Ingresos, gastos, intereses, resultado financiero y composición del gasto | Hacienda vía datos.gob.ar | Desde 2015 |
| Empleo (ampliada) | Trabajadores registrados, informalidad, subocupación | Secretaría de Trabajo e INDEC vía datos.gob.ar | Desde 2012; EPH desde 2003 |

Decisiones de método:

- **Reservas netas: no se publican.** El swap con China, los encajes y otros pasivos no tienen una serie oficial actualizada que permita calcularlas sin supuestos.
- **Fiscal:** se usa el Sector Público Nacional, base caja, metodología 2017. La serie IMIG se descartó porque tiene series vacías o cortadas en la API.
- **PIB fiscal:** `pib_n` está anualizado, así que el PIB de 12 meses es el promedio de 4 trimestres, interpolado entre cierres como en la v1. El superávit primario coincide con el de la v1 en los 127 meses.
- **Calculados por faltar en la API:** transferencias al sector privado (por diferencia), gasto de capital (suma de partes), ingreso primario (rentas + remuneraciones) e ingreso secundario (por diferencia).
- **Empleo:** sector público y casas particulares usan la serie con estacionalidad, porque la desestacionalizada está vacía.
- **Sin incorporar:** RIPTE, porque su serie está vacía en la API.

## Etapa 3: contexto y sostenibilidad

| Dónde | Qué se sumó | Fuente | Período |
|---|---|---|---|
| Sostenibilidad (sección nueva) | 12 indicadores contra un año antes, sin puntaje ni umbrales | Elaboración con datos del tablero | Según cada indicador |
| Contexto global (sección nueva) | Soja, maíz, trigo, Brent, Fed, bono a 10 años, IBC-Br, real y Selic | FRED (incluye FMI) y Banco Central de Brasil | Desde 1954-1992 según la serie; Brasil desde 1995 o 2003 |
| Actividad | Demanda agregada y aportes al crecimiento | INDEC | Desde 2004 |
| Actividad | Capacidad instalada, ISAC e ISSP | INDEC | Desde 2012 o 2016 |
| Balanza | Precio y cantidad de exportaciones | INDEC | Desde 1990 |
| Inflación y tasas | Curva de tasas en pesos | ArgentinaDatos (no oficial) | Foto del 5 nov 2026 |
| Actividad | Crédito al sector privado / PIB | BCRA e INDEC | Desde 2010 |

Decisiones de método:

- **Sostenibilidad:** muestra la dirección frente a un año antes. No hay puntaje porque cualquier ponderación sería arbitraria.
- **Aportes al crecimiento:** salen de los componentes a precios de 2004. «Resto» se calcula por diferencia e incluye existencias y discrepancia estadística.
- **Curva en pesos:** se excluye TTD26, con TEM de −6,55 %, porque un rendimiento negativo no es comparable con el resto.
- **Brasil:** el real y la Selic se recortan desde 1995, porque antes hubo otras monedas e hiperinflación.
- **Sin incorporar:** precio y cantidad de importaciones (series vacías en la API), morosidad (sin serie vigente localizada), historia de la curva en pesos.

## Calendario de actualización

- **Horario:** una corrida diaria a las 18:00 de Argentina. Los datos diarios se actualizan en ella los días hábiles; los mensuales y trimestrales, solo el día en que les toca.
- **Conectados al calendario:** dólar, tasas, riesgo país, reservas e inflación. Antes dependían de la base de la v1.
- **Octubre de 2026 corregido:** la v1 lo había bajado antes del cierre. Reservas pasa de 50.208 a 48.565 M US$; riesgo país, de 644 a 661 pb; dólar oficial, de 1.523 a 1.525 $.
- **Método validado:** promedios y últimos datos reproducen los valores de septiembre de 2026 de la v1.
- **Todavía sin conectar:** los grupos marcados como pendientes en `CALENDARIO.md`. Tampoco M2, préstamos reales ni la tabla de «quién le ganó a la inflación» (`carrera`).

## Revisado y sin cambios

- **Energía eléctrica (`xd46`), sep 2021.** El valor de 257,82 M coincide con la fuente oficial, aunque los subrubros superen al total de combustibles y energía.
- **Importaciones de 2008 y 2016.** `mensual` y `comercio_rubros` difieren de `comercio_paises` y de la API en 12 meses. Falta decidir cuál usar.
- **Stock de IED, 1.er trim. 2026.** Sube 19.172 M con un flujo de 2.834 M, y el total (202.033 M) difiere del desglose (200.611 M). La serie consultada en la API vino vacía, así que sigue sin verificar y se avisa en la página.
- **Series cortadas.** Expectativas UTDT, neumáticos y otros productos de caucho terminan en enero de 2026; el gasto consolidado, en 2023. Se avisa en la página.
