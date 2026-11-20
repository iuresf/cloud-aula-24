#!/usr/bin/env python3
"""Contrato minimo dos arquivos Bronze, executado localmente e no CI."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "dados"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_csv(path, required):
    with path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source, delimiter=";"))
    require(rows, f"{path}: arquivo vazio")
    require(set(required).issubset(rows[0]), f"{path}: colunas obrigatorias ausentes")


def validate_jsonl(path, required):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(rows, f"{path}: arquivo vazio")
    require(all(set(required).issubset(row) for row in rows), f"{path}: campos obrigatorios ausentes")


def main():
    validate_csv(ROOT / "inicial/pedidos/lote_001.csv", ["id", "dia", "valor", "status", "canal"])
    validate_jsonl(ROOT / "inicial/pagamentos/lote_001.jsonl", ["pedido_id", "resultado", "atualizado_em"])
    validate_jsonl(ROOT / "inicial/eventos/lote_001.jsonl", ["evento_id", "sessao", "evento", "pedido_id", "dia", "canal"])
    validate_jsonl(ROOT / "delta/pagamentos/lote_002.jsonl", ["pedido_id", "resultado", "atualizado_em"])
    print("Contratos Bronze validados.")


if __name__ == "__main__":
    main()
