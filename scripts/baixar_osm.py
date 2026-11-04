"""
Baixa a malha viária de uma cidade pela Overpass API (OpenStreetMap) para data/raw/.

Uso:  python3 scripts/baixar_osm.py brumadinho
      python3 scripts/baixar_osm.py minha_cidade --bbox -20.21 -44.23 -20.11 -44.15

Os dados já baixados estão versionados em data/raw/, então este script só é
necessário para atualizar os dados ou adicionar novas cidades.
Dados © OpenStreetMap contributors, licença ODbL.
"""

import argparse
import os
import time
import urllib.parse
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVIDORES = ["https://overpass-api.de/api/interpreter",
              "https://overpass.kumi.systems/api/interpreter"]
BBOX_CONHECIDAS = {
    "brumadinho": (-20.213, -44.228, -20.117, -44.157),
    "petropolis": (-22.540, -43.214, -22.479, -43.148),
    "mariana": (-20.400, -43.440, -20.350, -43.390),
}
CONSULTA = ('[out:json][timeout:120];'
            'way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street)(_link)?$"]'
            '({s},{w},{n},{e});out body;>;out skel qt;')


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cidade")
    p.add_argument("--bbox", nargs=4, type=float, metavar=("SUL", "OESTE", "NORTE", "LESTE"))
    a = p.parse_args()
    bbox = a.bbox or BBOX_CONHECIDAS.get(a.cidade)
    if not bbox:
        p.error("cidade desconhecida: informe --bbox")
    q = CONSULTA.format(s=bbox[0], w=bbox[1], n=bbox[2], e=bbox[3])
    dados = urllib.parse.urlencode({"data": q}).encode()
    espera = 5
    for tentativa in range(6):
        url = SERVIDORES[tentativa % len(SERVIDORES)]
        try:
            req = urllib.request.Request(url, data=dados, headers={"User-Agent": "fluxo-evacuacao/1.0 (trabalho academico)"})
            with urllib.request.urlopen(req, timeout=180) as r:
                corpo = r.read()
            if not corpo.lstrip().startswith(b"{"):
                raise RuntimeError("resposta não é JSON (servidor ocupado)")
            destino = os.path.join(RAIZ, "data", "raw", f"{a.cidade}.json")
            with open(destino, "wb") as f:
                f.write(corpo)
            print(f"salvo em {destino} ({len(corpo)//1024} KiB)")
            return
        except Exception as ex:  # noqa: BLE001
            print(f"tentativa {tentativa + 1} falhou em {url}: {ex}; aguardando {espera}s")
            time.sleep(espera)
            espera *= 2
    raise SystemExit("não foi possível baixar os dados")


if __name__ == "__main__":
    main()
