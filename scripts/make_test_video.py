"""Синтетические .mov для проверки сервиса без датасета.

  python scripts/make_test_video.py --out data/test_clean.mov
  python scripts/make_test_video.py --out data/test_covered.mov --cover 5:8
  python scripts/make_test_video.py --out data/test_partial.mov --cover 4:7 --partial

Вид сверху: стол кассира, лоток, двигающиеся «люди». --cover закрывает объектив на
заданном отрезке (секунды «от:до») — его должен найти детектор obstruction (V13).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np

W, H, FPS = 1280, 720, 30


def background(rng: np.random.Generator) -> np.ndarray:
    img = np.zeros((H, W, 3), np.uint8)
    tile = 64
    for y in range(0, H, tile):
        for x in range(0, W, tile):
            shade = 150 + int(rng.integers(-12, 12)) + (8 if (x // tile + y // tile) % 2 else 0)
            img[y:y + tile, x:x + tile] = (shade, shade + 4, shade + 8)
    noise = rng.normal(0, 6, img.shape)
    img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    cv2.rectangle(img, (120, 260), (1160, 360), (52, 92, 140), -1)        # стол
    cv2.rectangle(img, (120, 260), (1160, 268), (90, 140, 190), -1)
    cv2.rectangle(img, (120, 360), (1160, 372), (215, 205, 160), -1)      # стекло
    cv2.rectangle(img, (590, 340), (690, 390), (150, 150, 150), -1)       # лоток
    cv2.rectangle(img, (900, 280), (980, 330), (70, 70, 70), -1)          # счётчик банкнот
    for i in range(5):
        cv2.rectangle(img, (300 + i * 14, 300), (350 + i * 14, 322), (60, 140, 70), -1)  # пачки
    return img


def person(img: np.ndarray, cx: int, cy: int, coat: tuple[int, int, int]) -> None:
    cv2.ellipse(img, (cx, cy), (70, 34), 0, 0, 360, coat, -1)
    cv2.circle(img, (cx, cy - 4), 26, (40, 52, 70), -1)
    cv2.circle(img, (cx + 8, cy - 10), 7, (90, 110, 130), -1)


def frame_at(base: np.ndarray, t: float, cover: tuple[float, float] | None, partial: bool) -> np.ndarray:
    img = base.copy()
    person(img, 640 + int(60 * np.sin(t * 0.9)), 180 + int(10 * np.sin(t * 2.1)), (150, 80, 40))   # кассир
    person(img, 620 + int(140 * np.sin(t * 0.35)), 520 + int(30 * np.cos(t * 0.8)), (60, 50, 160))  # клиент
    hand = (700 + int(40 * np.sin(t * 3)), 330 + int(15 * np.cos(t * 2.5)))
    cv2.circle(img, hand, 14, (120, 150, 200), -1)
    if cover and cover[0] <= t < cover[1]:
        if partial:
            mask = np.zeros((H, W), np.uint8)
            cv2.ellipse(mask, (W // 2 - 80, H // 2), (int(W * 0.62), int(H * 0.72)), 0, 0, 360, 255, -1)
            dark = cv2.GaussianBlur((img * 0.12).astype(np.uint8), (0, 0), 25)
            img = np.where(mask[..., None] > 0, dark, img)
        else:
            img = cv2.GaussianBlur((img * 0.1).astype(np.uint8), (0, 0), 30)
    return img


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seconds", type=float, default=14.0)
    p.add_argument("--cover", help="отрезок перекрытия камеры, например 5:8")
    p.add_argument("--partial", action="store_true", help="перекрыть не весь кадр, а ~80%%")
    p.add_argument("--seed", type=int, default=7)
    a = p.parse_args()

    cover = tuple(float(x) for x in a.cover.split(":")) if a.cover else None
    base = background(np.random.default_rng(a.seed))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    n = int(a.seconds * FPS)

    if shutil.which("ffmpeg"):
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
               "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
               "-crf", "23", "-movflags", "+faststart", str(a.out)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        assert proc.stdin is not None
        for i in range(n):
            proc.stdin.write(frame_at(base, i / FPS, cover, a.partial).tobytes())
        proc.stdin.close()
        proc.wait()
    else:
        writer = cv2.VideoWriter(str(a.out), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
        for i in range(n):
            writer.write(frame_at(base, i / FPS, cover, a.partial))
        writer.release()
    print(f"{a.out}  {a.seconds:.0f} с, перекрытие: {a.cover or 'нет'}{' (частичное)' if a.partial else ''}")


if __name__ == "__main__":
    main()
