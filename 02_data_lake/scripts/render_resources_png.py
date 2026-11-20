#!/usr/bin/env python3
"""Gera um PNG da infraestrutura criada pelo Terraform, sem bibliotecas externas."""
import argparse
import os
import struct
import zlib
from datetime import datetime

W, H = 1600, 1000
WHITE = (255, 255, 255)
INK = (31, 41, 55)
BLUE = (37, 99, 235)
ORANGE = (234, 88, 12)
GREEN = (22, 163, 74)
PURPLE = (126, 34, 206)
GRAY = (75, 85, 99)
LIGHT_BLUE = (219, 234, 254)
LIGHT_ORANGE = (255, 237, 213)
LIGHT_GREEN = (220, 252, 231)
LIGHT_PURPLE = (243, 232, 255)
LIGHT_GRAY = (243, 244, 246)

# Glifos 5x7 para as etiquetas do diagrama.
FONT = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "/": ["00001", "00010", "00100", "01000", "10000", "00000", "00000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "00110", "00110"],
    " ": ["00000"] * 7,
}


class Canvas:
    def __init__(self):
        self.pixels = bytearray(WHITE * (W * H))

    def pixel(self, x, y, color):
        if 0 <= x < W and 0 <= y < H:
            i = (y * W + x) * 3
            self.pixels[i:i + 3] = bytes(color)

    def rect(self, x, y, w, h, fill, border=INK):
        for py in range(y, y + h):
            for px in range(x, x + w):
                self.pixel(px, py, fill)
        for px in range(x, x + w):
            self.pixel(px, y, border)
            self.pixel(px, y + h - 1, border)
        for py in range(y, y + h):
            self.pixel(x, py, border)
            self.pixel(x + w - 1, py, border)

    def line(self, x1, y1, x2, y2, color=GRAY, width=3):
        steps = max(abs(x2 - x1), abs(y2 - y1), 1)
        for n in range(steps + 1):
            x = round(x1 + (x2 - x1) * n / steps)
            y = round(y1 + (y2 - y1) * n / steps)
            for dx in range(-width // 2, width // 2 + 1):
                for dy in range(-width // 2, width // 2 + 1):
                    self.pixel(x + dx, y + dy, color)

    def arrow(self, x1, y1, x2, y2, color=GRAY):
        self.line(x1, y1, x2, y2, color)
        if abs(x2 - x1) >= abs(y2 - y1):
            direction = 1 if x2 > x1 else -1
            self.line(x2, y2, x2 - 12 * direction, y2 - 8, color)
            self.line(x2, y2, x2 - 12 * direction, y2 + 8, color)
        else:
            direction = 1 if y2 > y1 else -1
            self.line(x2, y2, x2 - 8, y2 - 12 * direction, color)
            self.line(x2, y2, x2 + 8, y2 - 12 * direction, color)

    def text(self, x, y, message, color=INK, scale=2):
        for char in message.upper():
            glyph = FONT.get(char, FONT[" "])
            for row, pattern in enumerate(glyph):
                for col, bit in enumerate(pattern):
                    if bit == "1":
                        for sx in range(scale):
                            for sy in range(scale):
                                self.pixel(x + col * scale + sx, y + row * scale + sy, color)
            x += 6 * scale

    def centered(self, cx, y, message, color=INK, scale=2):
        self.text(cx - len(message) * 3 * scale, y, message, color, scale)

    def save_png(self, path):
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

        rows = b"".join(b"\x00" + self.pixels[y * W * 3:(y + 1) * W * 3] for y in range(H))
        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as output:
            output.write(png)


def node(canvas, x, y, w, h, title, subtitle, fill, accent):
    canvas.rect(x, y, w, h, fill, accent)
    canvas.centered(x + w // 2, y + 22, title, INK, 3)
    for index, line in enumerate(subtitle):
        canvas.centered(x + w // 2, y + 68 + index * 22, line, GRAY, 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--workgroup", required=True)
    parser.add_argument("--workflow", required=True)
    args = parser.parse_args()

    c = Canvas()
    c.centered(W // 2, 30, "RECURSOS TERRAFORM - AULA 24", INK, 4)
    c.centered(W // 2, 76, f"PROJETO {args.project}   GERADO {datetime.now().strftime('%Y-%m-%d %H:%M')}", GRAY, 2)

    # Entrada protegida e desacoplada: o cliente recebe 202 antes do processamento.
    node(c, 45, 155, 205, 115, "COGNITO", ["JWT", "AUTORIZACAO"], LIGHT_PURPLE, PURPLE)
    node(c, 300, 155, 205, 115, "API GATEWAY", ["POST INGESTIONS", "GET RESULTS"], LIGHT_BLUE, BLUE)
    node(c, 555, 155, 205, 115, "LAMBDA API", ["VALIDA", "RETORNA 202"], LIGHT_GREEN, GREEN)
    node(c, 810, 155, 205, 115, "SQS", ["BATCH 10", "DLQ 3 ERROS"], LIGHT_PURPLE, PURPLE)
    node(c, 1065, 155, 205, 115, "LAMBDA BRONZE", ["IDEMPOTENCIA", "DYNAMODB"], LIGHT_GREEN, GREEN)
    node(c, 1320, 155, 220, 115, "S3 BRONZE", ["ARQUIVOS", "ORIGINAIS"], LIGHT_ORANGE, ORANGE)
    c.arrow(250, 212, 300, 212, PURPLE)
    c.arrow(505, 212, 555, 212, BLUE)
    c.arrow(760, 212, 810, 212, GREEN)
    c.arrow(1015, 212, 1065, 212, PURPLE)
    c.arrow(1270, 212, 1320, 212, GREEN)

    node(c, 115, 390, 250, 125, "GLUE WORKFLOW", ["SILVER SUCCEEDED", "INICIA GOLD"], LIGHT_PURPLE, PURPLE)
    node(c, 470, 390, 220, 125, "GLUE SILVER", ["LIMPEZA E", "PARQUET"], LIGHT_BLUE, BLUE)
    node(c, 780, 390, 220, 125, "S3 SILVER", ["DADOS", "TRATADOS"], LIGHT_ORANGE, ORANGE)
    node(c, 1090, 390, 220, 125, "GLUE GOLD", ["INDICADORES", "AGREGADOS"], LIGHT_BLUE, BLUE)
    node(c, 1370, 390, 170, 125, "S3 GOLD", ["INDICADORES", "PARQUET"], LIGHT_ORANGE, ORANGE)
    c.arrow(1430, 270, 240, 390, PURPLE)
    c.arrow(365, 452, 470, 452, PURPLE)
    c.arrow(690, 452, 780, 452, BLUE)
    c.arrow(1000, 452, 1090, 452, ORANGE)
    c.arrow(1310, 452, 1370, 452, BLUE)

    node(c, 105, 620, 235, 125, "S3 RESULTS", ["SCRIPTS", "MANIFESTOS E SQL"], LIGHT_ORANGE, ORANGE)
    node(c, 440, 620, 240, 125, "GLUE CATALOG", [args.database, "TABELAS EXTERNAS"], LIGHT_GREEN, GREEN)
    node(c, 780, 620, 230, 125, "ATHENA", [args.workgroup, "CONSULTAS SQL"], LIGHT_GREEN, GREEN)
    node(c, 1110, 620, 200, 125, "EVENTBRIDGE", ["FALHA DE JOB", "EVENTO"], LIGHT_PURPLE, PURPLE)
    node(c, 1380, 620, 160, 125, "SNS", ["ALERTA", "E MAIL"], LIGHT_PURPLE, PURPLE)
    c.arrow(340, 682, 440, 682, ORANGE)
    c.arrow(680, 682, 780, 682, GREEN)
    c.arrow(1455, 515, 895, 620, GREEN)
    c.arrow(1200, 515, 1210, 620, PURPLE)
    c.arrow(1310, 682, 1380, 682, PURPLE)

    c.rect(80, 815, 1460, 95, LIGHT_GRAY, GRAY)
    c.centered(W // 2, 838, "FLUXO DE PRODUCAO", INK, 3)
    c.centered(W // 2, 880, "API -> FILA -> BRONZE -> WORKFLOW -> SILVER -> GOLD -> ATHENA", GRAY, 2)
    c.centered(W // 2, 940, "PNG GERADO AUTOMATICAMENTE AO FINAL DE CADA TERRAFORM APPLY", GRAY, 2)
    c.save_png(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
