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
- **EMAE y salarios conectados (8 nov 2026):** se bajan directo de INDEC (`sh_emae_mensual_base2004.xls` e `indice_salarios.csv`), porque la API de datos.gob.ar seguía en julio. Suman agosto de 2026 y los KPI pasan a ago 2026.
- **Método de EMAE y salarios:** solo se agregan meses posteriores al último dato de la v1; la historia no se pisa. EMAE: desestacionalizado y variación interanual publicados por INDEC. Salario real: índice nominal / IPC, empalmado con el factor de la v1 (constante desde 2018, verificado). Trimestres: promedio de los tres meses, como en la v1. Aviso: INDEC revisa el desestacionalizado cada mes, así que la variación jul→ago en el tablero (+0,16 %) difiere de la publicada (+0,07 %).
- **IPI y EMAE por rama conectados (8 nov 2026):** el IPI manufacturero (nivel general, 16 divisiones y 67 subclases, más el desestacionalizado y la variación interanual) se baja de `sh_ipi_manufacturero_AAAA.xls`, buscado en la página del IPI porque el nombre cambia con el año. Suma septiembre de 2026. Las ramas del EMAE salen de `sh_emae_actividad_base2004.xls` y quedan atadas al EMAE. Neumáticos y otros productos de caucho siguen vacíos: INDEC los publica como «s» (secreto estadístico).
- **Comercio exterior conectado (8 nov 2026):** primera actualización automática con octubre (INDEC publica el 19/11). Totales mensuales de `balanmensual.xls`; grandes rubros y usos de `expo_grandes_rubros_AAAA_AAAA.xls` e `impo_uso_economico_AAAA_AAAA.xls`; subrubros de exportación del cuadro 12 del informe técnico (`ica_cuadros_DD_MM_AA.xls`). Los nombres se buscan en la página del ICA.
- **Comercio por socio:** INDEC solo publica el acumulado del año por país (`balan_continentes_paises_AAAA_AAAA.xls`). El mes sale de restar la foto del acumulado anterior, que se guarda en `pipeline/fuentes/comercio_paises_acum.csv`; en enero, el acumulado es el mes. Si se pierde un mes, ese mes queda sin desglose por socio (los totales no se afectan). Bloques: Mercosur = Brasil + Paraguay + Uruguay + Venezuela; EE. UU. y Canadá; Unión Europea (27); Asia-Pacífico (China, Japón, Corea, Taiwán y ASEAN); África; todos verificados contra la v1 (diferencias menores al 3 % en ene–sep 2026, atribuibles a revisiones).
- **Socios sin empalme (quedan vacíos en los meses nuevos):** Reino Unido (la v1 trae entre 4 y 5 veces lo que publica INDEC: 1.694 vs 349 M US$ de importaciones en ene–sep 2026), Resto de América Latina, Medio Oriente y Resto del mundo (la v1 usa otra definición: hasta 16 % de diferencia). Hay que revisar de dónde salían en la v1 antes de completarlos.
- **Subrubro energía eléctrica (`xd46`):** INDEC ya no lo publica aparte (va dentro de «Resto de CyE»); en los meses nuevos queda vacío, no en cero.
- **Consumo por rubros conectado (8 nov 2026):** supermercados y autoservicios mayoristas de `serie_supermercados.xlsx` y `serie_autoservicios_mayoristas.xlsx` (cuadros 3 y 5); centros de compras de `sh_compras_MM_AA.xls`, buscado en su página porque cambia de nombre cada mes. Shoppings a precios constantes: índice de INDEC escalado con el factor de la v1. La primera actualización automática será septiembre (25/11). La tabla de consumo físico (electricidad, gas, combustibles, autos, cemento y carne) sigue sin conectar.
- **Recaudación conectada (8 nov 2026):** se baja de las planillas anuales de ARCA (`serieAAAA.xls`, año en curso y anterior). Derechos de importación = derechos + tasa de estadística + factor de convergencia, como en la v1 (coinciden los 22 meses comparados). Recaudación real interanual: recursos tributarios deflactados por el IPC; presión tributaria: recursos tributarios de 12 meses sobre el PIB nominal interpolado entre trimestres. Ambas fórmulas reproducen exactamente la v1. La presión se completa cuando llega el PIB del trimestre y la recaudación real, cuando llega el IPC del mes: por eso esas fuentes también tienen permiso sobre esas columnas.
- **EPH conectada (8 nov 2026):** desempleo, actividad y empleo trimestrales de la API de datos.gob.ar (que replica a INDEC y está al día), con un decimal; reproduce la v1 en los 41 trimestres desde 2016. La diferencia interanual del desempleo se calcula. El Gini sigue sin conectar.
- **Control de cambios con filas nuevas:** un período nuevo (por ejemplo, un trimestre) trae columnas estructurales y derivadas de datos ya publicados; antes eso cancelaba la corrida. Ahora una fila nueva se acepta si alguna fuente actualizada escribe en esa tabla; las filas existentes siguen con el control columna por columna.
- **Inversión e IED conectadas (8 nov 2026):** formación bruta de capital fijo por tipo, a precios de 2004 y corrientes, de `sh_oferta_demanda_MM_AA.xls` (cuadros 6 y 14; la API trae vacías construcciones y otros activos). Flujos de IED (capital y deuda) de la API del balance de pagos. Reproducen la v1 desde 2005 (en 2004 la v1 usó el total del cuadro 1, que difiere en menos de 0,01 %). Las columnas derivadas (variaciones, participaciones, inversión / PIB, índice y flujo de 4 trimestres) siguen el método de la v1, verificado en todos los trimestres. El stock de IED no se completa: sigue sin fuente verificada.
- **Crecimiento del PIB en trimestres nuevos:** `pib_ia` no se calculaba para trimestres posteriores a la v1, y el control de aportes al crecimiento habría cancelado la actualización del 8 de enero. Ahora sale de la misma serie de PIB real.
- **M2, préstamos reales, canasta, salario mínimo y jubilación mínima conectados (8 nov 2026):** M2 privado = último dato del mes de la variable 25 del BCRA; octubre de 2026 se corrige (la v1 lo bajó antes del cierre: 20,6 → 21,1 %). Préstamos reales = préstamos en pesos al sector privado (`91.1_DETALLE_PRPOT_0_0_25`) deflactados por el IPC: reproduce la v1 en 104 meses. Canasta básica de `serie_cba_cbt.xls`; salario mínimo y haber mínimo de datos.gob.ar (el SMVM trae aumentos futuros: solo se toman meses cerrados). Salario mínimo y jubilación a pesos constantes con el factor de la v1, constante desde 2017.
- **Tabla «¿Quién le ganó a la inflación?» (`carrera`):** ahora se rearma en cada actualización con el último dato de cada serie; con los datos de la v1 reproduce sus 20 filas.
- **Todavía sin conectar:** los grupos marcados como pendientes en `CALENDARIO.md`. Tampoco M2, préstamos reales ni la tabla de «quién le ganó a la inflación» (`carrera`).

## Revisado y sin cambios

- **Energía eléctrica (`xd46`), sep 2021.** El valor de 257,82 M coincide con la fuente oficial, aunque los subrubros superen al total de combustibles y energía.
- **Importaciones de 2008 y 2016.** `mensual` y `comercio_rubros` difieren de `comercio_paises` y de la API en 12 meses. Falta decidir cuál usar.
- **Stock de IED, 1.er trim. 2026.** Sube 19.172 M con un flujo de 2.834 M, y el total (202.033 M) difiere del desglose (200.611 M). La serie consultada en la API vino vacía, así que sigue sin verificar y se avisa en la página.
- **Series cortadas.** Expectativas UTDT, neumáticos y otros productos de caucho terminan en enero de 2026; el gasto consolidado, en 2023. Se avisa en la página.
