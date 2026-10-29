"""Sugerencias de algunas personas en los tres ordenes, por bloque.

Lee los archivos que genera medir_sugerencias.py (uno por orden) y no llama a
modelos ni a la base.
Uso: python3 scripts/informe_personas.py <prefijo_archivos> <email> [<email> ...]
  ej.: python3 scripts/informe_personas.py verificacion/demo_bloques demo.vivo.carla@rizoma.local
       (lee verificacion/demo_bloques_rareza.json, _cruces.json y _azar.json)
"""
import json
import sys

ORDENES = ("rareza", "cruces", "azar")
TITULOS = {"comun": "Temas en común", "puente": "Caminos puente", "otros": "Otros perfiles (sin camino en el grafo)"}


def main():
    base, emails = sys.argv[1], sys.argv[2:]
    datos = {o: json.load(open(f"{base}_{o}.json", encoding="utf-8")) for o in ORDENES}
    for email in emails:
        print(f"\n### {email} — {len(datos['rareza']['por_persona'][email])} sugerencias")
        for o in ORDENES:
            semilla = datos[o]["parametros"].get("semilla")
            print(f"\n  [{o}{f' · semilla {semilla}' if o == 'azar' else ''}]")
            for b, titulo in TITULOS.items():
                items = [s for s in datos[o]["por_persona"][email] if s.get("bloque") == b]
                print(f"    {titulo} ({len(items)})")
                for s in items[:5] if b != "otros" else items:
                    print(f"      {s['posicion']}. {s['nombre']} — {s['dato']}" if b != "otros" else f"      · {s['nombre']}")


if __name__ == "__main__":
    main()
