"""Arma el sitio estático para GitHub Pages en _site/ (modo P2P, sin servidor).

    python tools/build_pages.py
    python -m http.server 8080 -d _site     # para probarlo en local

- copia client/ y los módulos de server/ que corren en Pyodide (todos menos main.py);
- en index.html cambia /static/ por rutas relativas, agrega p2p.js y la versión
  (huella de todos los archivos) para que el navegador no use un JS viejo.
"""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
SERVER_ONLY = {"main.py"}  # necesita FastAPI: no va al navegador


def main() -> None:
    client = sorted(f for f in (ROOT / "client").iterdir() if f.is_file())
    server = sorted(f for f in (ROOT / "server").glob("*.py") if f.name not in SERVER_ONLY)

    h = hashlib.sha1()
    for f in client + server:
        h.update(f.name.encode())
        h.update(f.read_bytes())
    version = h.hexdigest()[:10]

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "server").mkdir(parents=True)
    for f in client:
        shutil.copy2(f, OUT / f.name)
    for f in server:
        shutil.copy2(f, OUT / "server" / f.name)
    (OUT / "server" / "manifest.json").write_text(json.dumps([f.name for f in server]), encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")  # que Pages sirva los archivos tal cual

    index = OUT / "index.html"
    html = index.read_text(encoding="utf-8")
    old = '<script src="/static/game.js"></script>'
    assert old in html, "index.html cambió: actualizá build_pages.py"
    html = html.replace(old, f'<script src="p2p.js?v={version}"></script>\n'
                             f'<script src="game.js?v={version}"></script>')
    html = html.replace("<head>", f'<head>\n<meta name="client-version" content="{version}">', 1)
    index.write_text(html, encoding="utf-8")
    print(f"Sitio en {OUT.relative_to(ROOT)}/ (v {version})")


if __name__ == "__main__":
    main()
