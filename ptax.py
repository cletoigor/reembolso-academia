#!/usr/bin/env python3
"""Cotacao PTAX de venda (USD/BRL) do Banco Central.

Mesma fonte usada pela /nf-mensal, para as duas automacoes nao divergirem.
O BCB nao publica em fim de semana e feriado, entao anda para tras ate achar
o ultimo dia util com cotacao.

  python3 ptax.py            # a partir de hoje
  python3 ptax.py 2026-08-06 # a partir de uma data
"""

import json
import sys
from datetime import date, datetime, timedelta

import requests  # urllib falha no SSL deste Python 3.8 (sem certificados instalados)

URL = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoDolarDia(dataCotacao=@dataCotacao)"
    "?@dataCotacao='{mmddyyyy}'&$top=1&$format=json"
)
MAX_DIAS = 7


def cotacao(inicio=None, max_dias=MAX_DIAS):
    """Retorna (data_iso, cotacao_venda) do ultimo dia util com PTAX."""
    dia = inicio or date.today()
    for _ in range(max_dias):
        r = requests.get(URL.format(mmddyyyy=dia.strftime("%m-%d-%Y")), timeout=20)
        r.raise_for_status()
        valores = r.json().get("value") or []
        if valores:
            return dia.isoformat(), float(valores[0]["cotacaoVenda"])
        dia -= timedelta(days=1)
    raise RuntimeError(f"sem PTAX nos {max_dias} dias ate {(inicio or date.today())}")


def main():
    inicio = (datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
              if len(sys.argv) > 1 else None)
    try:
        data, venda = cotacao(inicio)
    except Exception as e:
        print(json.dumps({"erro": str(e)}, ensure_ascii=False))
        return 1
    print(json.dumps({"data": data, "cotacao_venda": venda}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
