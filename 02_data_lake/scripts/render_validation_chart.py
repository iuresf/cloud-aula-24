#!/usr/bin/env python3
"""Gera o grafico PNG de comparacao entre a carga inicial e o delta."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from render_resources_png import Canvas, GRAY, GREEN, INK, LIGHT_GRAY, ORANGE, PURPLE, W


def bar(canvas, x, baseline, width, height, color, label, value):
    canvas.rect(x, baseline - height, width, height, color, color)
    canvas.centered(x + width // 2, baseline + 20, label, INK, 2)
    canvas.centered(x + width // 2, baseline - height - 28, value, INK, 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--initial-revenue", type=float, required=True)
    parser.add_argument("--initial-conversion", type=float, required=True)
    parser.add_argument("--delta-revenue", type=float, required=True)
    parser.add_argument("--delta-conversion", type=float, required=True)
    args = parser.parse_args()

    canvas = Canvas()
    canvas.centered(W // 2, 50, "VALIDACAO DO PIPELINE - AULA 24", INK, 4)
    canvas.centered(W // 2, 102, "ATHENA APOS GLUE WORKFLOW", GRAY, 2)

    # Receita: escala da amostra e explicita o valor monetario em cima da barra.
    canvas.centered(430, 180, "RECEITA EM REAIS", INK, 3)
    canvas.line(130, 580, 730, 580, GRAY, 3)
    max_revenue = max(args.initial_revenue, args.delta_revenue, 1)
    bar(canvas, 230, 580, 150, round(320 * args.initial_revenue / max_revenue), GREEN, "INICIAL", f"{args.initial_revenue:.2f}")
    bar(canvas, 500, 580, 150, round(320 * args.delta_revenue / max_revenue), ORANGE, "DELTA", f"{args.delta_revenue:.2f}")

    # Conversao: escala sempre de 0 a 100, evitando leitura enganosa entre lotes.
    canvas.centered(1170, 180, "CONVERSAO PCT", INK, 3)
    canvas.line(870, 580, 1470, 580, GRAY, 3)
    bar(canvas, 970, 580, 150, round(320 * args.initial_conversion / 100), PURPLE, "INICIAL", f"{args.initial_conversion:.1f}%")
    bar(canvas, 1240, 580, 150, round(320 * args.delta_conversion / 100), ORANGE, "DELTA", f"{args.delta_conversion:.1f}%")

    canvas.rect(130, 730, 1340, 120, LIGHT_GRAY, GRAY)
    canvas.centered(W // 2, 758, "RESULTADO CONFIRMADO", INK, 3)
    canvas.centered(W // 2, 806, "ESTORNO P1042: 129.90 PARA 0.00  |  50.0 PARA 0.0 PCT", GRAY, 2)
    canvas.centered(W // 2, 920, "FONTE: CONSULTA ATHENA REGISTRADA NAS EVIDENCIAS", GRAY, 2)
    canvas.save_png(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
