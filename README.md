# Rizoma

**Emergen las conexiones.** Rizoma es un prototipo para generar redes: conecta personas por lo que cada una sabe, lo que quiere aprender y lo que le interesa, aunque el vínculo pase por otra persona. Muestra con quién conviene conversar y por qué.

- Presentación: https://rizoma.entornodepruebas.com.ar/presentacion
- Video (3 min): https://youtu.be/TYQVg7U9KsE

## Cómo funciona

1. **Cada persona carga su currículum o su trayectoria.** Antes de que un modelo de lenguaje lo lea, ve una copia sin nombre, correo, teléfonos, documentos, direcciones ni enlaces, y la puede corregir (`services/privacy_service.py`).
2. **Se arma un grafo bipartito persona–tema** con tres relaciones: lo que sabe, lo que quiere aprender y lo que le interesa. Los temas se normalizan en un vocabulario controlado de dos niveles, así dos personas que dicen lo mismo con palabras distintas se encuentran.
3. **La red sugiere con quién conversar.** El orden lo calcula el grafo, no el modelo:
   - pesa la **rareza** de los temas, no la cercanía (un tema que declaran dos personas de dieciséis dice más que uno que declaran casi todas);
   - busca **complementariedad**, no parecido (quién ofrece lo que otra persona quiere aprender);
   - sigue **caminos indirectos**: personas que no comparten ningún tema pero se conectan a través de un tercero.

   El modelo de lenguaje solo redacta la explicación de una sugerencia, y solo cuando alguien la pide.

## Para qué puede servir

1. **Con quién conversar**: sugerencias explicadas, con el camino que las justifica.
2. **Actividades emergentes**: cruces de temas de áreas distintas que nadie reúne todavía.
3. **Los puentes de la red**: quién une áreas que, sin esa persona, quedarían desconectadas.
4. **Probar antes de decidir**: simulador de qué cambiaría si se suma alguien, sin guardar nada.
5. **Recursos en común**: cada persona pone a disposición lo que tiene (datos, un espacio, tiempo, una persona que quiere colaborar); quien lo necesita avisa «me sirve, para…» y a las dos semanas las dos partes cuentan si sirvió.

## Privacidad por diseño

- Copia seudonimizada del CV antes de cualquier llamada a un modelo; no se guarda el archivo.
- Cada persona decide qué ven los demás: nombre abreviado por defecto, bio, institución, aparecer o no en sugerencias y búsquedas (`services/visibilidad.py`).
- Conjuntos separados (prueba, demostración, red general): nadie recibe sugerencias de otro conjunto.
- Aviso de privacidad versionado con constancia de lectura (`static/privacidad.html`, `services/privacy_notice.py`).
- Derechos de acceso y supresión (`scripts/privacidad_exportar.py`, `scripts/privacidad_suprimir.py`).

## Tecnología

- Python 3.9+, [FastAPI](https://fastapi.tiangolo.com/), SQLAlchemy.
- PostgreSQL con [pgvector](https://github.com/pgvector/pgvector) y `pgcrypto`.
- NetworkX para el análisis de la red.
- Modelos de lenguaje y de *embeddings* por API (OpenAI y Anthropic), configurables.
- Interfaz en HTML, CSS y JavaScript sin framework (`static/`).

## Instalación local

```bash
# 1. Base de datos (PostgreSQL con pgvector)
createdb rizoma
psql -d rizoma -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pgcrypto;"

# 2. Dependencias
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# 3. Configuración
cp .env.example .env    # completar DATABASE_URL, SECRET_KEY y, si se usan, las claves de los modelos

# 4. Tablas: se crean al iniciar; después aplicar los ajustes de sql/ en orden
uvicorn main:app --host 127.0.0.1 --port 8000
for f in sql/*.sql; do psql -d rizoma -f "$f"; done
```

Perfiles ficticios para probar: `scripts/conjunto_demo.py` y `scripts/recursos_demo.py` (solo cuentas `demo.*@rizoma.local`).

## Pruebas

```bash
python -m pytest -q tests
```

## Estructura

| Carpeta | Qué hay |
| --- | --- |
| `routers/` | API (autenticación, perfiles, red, recursos, privacidad…) |
| `services/` | Lógica del grafo, visibilidad, privacidad, recursos |
| `scripts/` | Análisis de la red, medición de sugerencias, datos de demostración |
| `sql/` | Ajustes de la base, en orden de fecha |
| `static/` | Interfaz, aviso de privacidad y presentación |
| `conjunto_prueba_ponencia/`, `verificacion/` | Conjunto ficticio y resultados de la evaluación del orden |
| `ops/` | Registro de tratamientos, riesgos y procedimientos de privacidad |
| `tests/` | Pruebas automáticas |

## Estado

Prototipo de investigación. Las sugerencias son hipótesis para conversar, no decisiones: validarlas exige personas reales evaluando los vínculos a ciegas. Todos los perfiles incluidos en este repositorio son ficticios.

## Autoría y licencia

Maximiliano Ariel Pérez, Ana Belén Gómez Reyes y Enrique Álvarez.

Código bajo licencia [MIT](LICENSE). Las tipografías de `static/fonts/` tienen sus propias licencias (SIL Open Font License), incluidas en esa carpeta.
