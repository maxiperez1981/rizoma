from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def test_presentacion_tiene_ruta_propia():
    main = (RAIZ / "main.py").read_text(encoding="utf-8")
    assert "@app.get(\"/presentacion\"" in main
    assert main.index("@app.get(\"/presentacion\"") < main.index("def spa_fallback")


def test_presentacion_usa_imagenes_existentes():
    import re
    html = (RAIZ / "static" / "presentacion.html").read_text(encoding="utf-8")
    imagenes = re.findall(r"/static/(img/presentacion/[\w.-]+)", html)
    assert imagenes
    for ruta in imagenes:
        assert (RAIZ / "static" / ruta).is_file(), ruta
    assert not re.search(r"\bproducto\b", html.lower())   # «reproductor» no cuenta
