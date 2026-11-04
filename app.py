"""
Ponto de entrada da aplicação.

    python3 app.py               # abre http://127.0.0.1:8000 no navegador
    python3 app.py --porta 8080 --sem-navegador
"""

import argparse
import threading
import webbrowser

from fluxo.servidor import iniciar


def main():
    p = argparse.ArgumentParser(description="Planejador de evacuação por fluxo máximo (Ford-Fulkerson)")
    p.add_argument("--porta", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--sem-navegador", action="store_true")
    a = p.parse_args()
    srv = iniciar(a.porta, a.host)
    url = f"http://{a.host}:{a.porta}/"
    print(f"Servidor em {url}  (Ctrl+C para encerrar)")
    if not a.sem_navegador:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado")


if __name__ == "__main__":
    main()
