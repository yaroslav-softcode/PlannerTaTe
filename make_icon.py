# -*- coding: utf-8 -*-
"""Рисует значок приложения PlannerTaTe.ico: плитка в фирменных цветах и мини-граф (три узла).

Запуск: Python312 (в нём PIL) из папки проекта. Файл кладётся рядом с backend.py.
"""
from PIL import Image, ImageDraw

S = 1024
C1 = (129, 104, 255)      # «Ma» — #8168ff
C2 = (34, 158, 217)       # «Te» — #229ed9
im = Image.new("RGBA", (S, S), (0, 0, 0, 0))

# фон: скруглённый квадрат с диагональным градиентом
grad = Image.new("RGBA", (S, S))
gd = grad.load()
for y in range(S):
    for x in range(0, S, 4):                     # шаг 4 px — быстрее, градиент гладкий
        t = (x + y) / (2 * S - 2)
        col = (int(C1[0] + (C2[0] - C1[0]) * t),
               int(C1[1] + (C2[1] - C1[1]) * t),
               int(C1[2] + (C2[2] - C1[2]) * t), 255)
        for dx in range(4):
            if x + dx < S:
                gd[x + dx, y] = col

mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=255)
im.paste(grad, (0, 0), mask)

d = ImageDraw.Draw(im)
# мини-граф: те же три узла, что и в планировщике
nodes = [(S * 0.28, S * 0.30), (S * 0.72, S * 0.44), (S * 0.46, S * 0.74)]
w = int(S * 0.035)
for a, b in ((0, 1), (1, 2), (2, 0)):
    d.line([nodes[a], nodes[b]], fill=(255, 255, 255, 190), width=w)
r = int(S * 0.085)
for cx, cy in nodes:
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 255))

im.save("PlannerTaTe.ico", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("значок готов: PlannerTaTe.ico")
