# Orden de carga fijo antes de Louvain: cifras anteriores y nuevas

Conjunto congelado `conjunto_demo_unq_20261013_con_orden.json` (50 perfiles
ficticios). Anteriores: código desplegado el 13/10/2026 (orden de carga de la
base), salidas en `../resultados_anteriores/`; son las cifras de la ponencia.
Nuevas: personas y temas ordenados por id antes de Louvain y `ORDER BY` en
`_cargar_grafo`, salidas en este directorio. Mismas semillas (30 para la
estabilidad, 12 para el consenso).

## Lo que no cambia

- Estructura de la red (personas, temas, vínculos, alcance por saltos), con y sin unificar.
- Comparación con la similitud semántica (Tabla 2).
- Las 8 actividades emergentes detectadas (mismos pares de temas, personas, demanda y oferta).
- Demanda formativa latente (mismos 8 temas, demanda, oferta y áreas).
- Pérdida de alcance de cada puente (temas y personas).
- Triangulación y umbrales (Tabla 5): no dependen de Louvain.

## Lo que cambia

| Cifra | Anterior | Nueva |
|---|---|---|
| **Red unificada** | | |
| Solapamiento corrida suelta vs. consenso de 30 semillas (Tabla 3) | 96 % (mín. 88 %) | 94 % (mín. 88 %) |
| Áreas por semilla (mediana) | 6,0 | 6,5 |
| Actividades presentes en las 30 corridas (Tabla 3) | 7 de 8 | 7 de 8 |
| Estabilidad en el sistema, 7 actividades (Tabla 4) | 1,00 | 1,00 |
| Estabilidad en el sistema, cooperativas + análisis territorial (Tabla 4) | 0,67 | 0,67 |
| Cooperativas + análisis territorial, semillas sueltas | 20/30 | 15/30 |
| Puente «territorio»: áreas que cruza | 4 | 5 |
| Puente «salud»: áreas | 1 | 2 |
| Persona puente 5: áreas que conecta | 1 | 2 |
| **Red sin unificar** | | |
| Solapamiento corrida suelta vs. consenso (Tabla 3) | 82 % (mín. 50 %) | 85 % (mín. 50 %) |
| Áreas por semilla (mediana) | 6,0 | 7,0 |
| Actividades presentes en las 30 corridas (Tabla 3) | 4 de 8 | 4 de 8 |
| Estabilidad de 4 actividades (no publicada) | 0,58 (19/30) | 0,75 (21/30) |

## Robustez frente al orden de carga (30 órdenes × 30 semillas, red unificada)

| Actividad | Anterior: 900 corridas | Anterior: consenso en 30 órdenes | Nueva: 900 corridas | Nueva: consenso en 30 órdenes |
|---|---|---|---|---|
| 7 actividades de estabilidad completa | 100 % | 100 % | 100 % | 100 % |
| análisis territorial + cooperativas | 66,9 % | 90 % | 50,0 % | 100 % |
| comercio exterior + cooperativas (no está en la Tabla 4) | 33,1 % | 10 % | 50,0 % | 0 % |

Con el orden fijo, las 30 permutaciones de carga dan exactamente el mismo
resultado: la variación que queda es solo la de la semilla. También coinciden
la base de desarrollo (otro orden físico, con la demostración cargada), el
archivo sin orden guardado y el archivo con orden.

## Si se despliega, la ponencia tendría que cambiar

- Sección 5 y Tabla 3: «sube de 82 % a 96 % (mínimo de 50 % a 88 %)» pasa a «de 85 % a 94 % (mínimo de 50 % a 88 %)».
- Sección 5: la frase de robustez («la octava en el 67 %») pasa a «la octava en la mitad de las semillas y en el consenso de los 30 órdenes».
- Sección 5: «territorio», compartido por 7 personas de **cuatro** áreas, pasa a **cinco**.
- La Tabla 4 no cambia.
