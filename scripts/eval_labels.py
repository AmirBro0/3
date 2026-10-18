"""Оценка на размеченном датасете: точность вердикта и ошибка таймкода.

  python scripts/eval_labels.py --videos ./dataset --labels open_labels.xlsx --local
  python scripts/eval_labels.py --videos ./dataset --labels open_labels.xlsx --url http://localhost:8000 --key <ключ>

--local гоняет пайплайн прямо в процессе (быстро, без сервера); --url — через API, как жюри.
Видео и строки разметки сопоставляются по номеру в имени: «X-1» (латиница) и «Х-1»
(кириллица) из open_labels.xlsx — это одно и то же видео 1.
Считает: accuracy вердикта, precision/recall по «нарушению», ошибку таймкода для верно
найденных нарушений и время обработки (лимит жюри — 300 с).
"""
from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

VIDEO_EXT = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".qt"}


def number_of(name: str) -> int | None:
    m = re.findall(r"\d+", Path(name).stem)
    return int(m[-1]) if m else None


def parse_time(raw) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).lower()
    minutes = re.search(r"(\d+)\s*мин", s)
    seconds = re.search(r"(\d+(?:[.,]\d+)?)\s*сек", s)
    if not minutes and not seconds:
        nums = re.findall(r"\d+(?:[.,]\d+)?", s)
        return float(nums[0].replace(",", ".")) if nums else None
    return (int(minutes.group(1)) * 60 if minutes else 0) + (float(seconds.group(1).replace(",", ".")) if seconds else 0)


def load_labels(path: Path) -> dict[int, dict]:
    import openpyxl

    ws = openpyxl.load_workbook(path, read_only=True).active
    labels: dict[int, dict] = {}
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0 or not row or not row[0]:
            continue
        num = number_of(str(row[0]))
        if num is None:
            print(f"! строка {i + 1}: нет номера в имени {row[0]!r}")
            continue
        verdict = "violation" if "без" not in str(row[2]).lower() else "no_violation"
        labels[num] = {"name": str(row[0]), "verdict": verdict, "t": parse_time(row[1])}
    return labels


def analyze_local(path: Path) -> dict:
    from app.config import get_settings
    from app.pipeline.analyzer import analyze

    s = get_settings()
    r = analyze(path, s, time.monotonic() + s.deadline_sec)
    return {"verdict": r.verdict, "violations": [{"type": f.rule.title, "timecode_sec": f.timecode} for f in r.findings]}


def analyze_api(path: Path, url: str, key: str) -> dict:
    import requests

    with path.open("rb") as fh:
        r = requests.post(f"{url}/api/v1/analyze", headers={"X-API-Key": key},
                          files={"file": (path.name, fh, "video/quicktime")}, timeout=300)
    r.raise_for_status()
    job_id = r.json()["job_id"]
    while True:
        d = requests.get(f"{url}/api/v1/jobs/{job_id}", headers={"X-API-Key": key}, timeout=60).json()
        if d.get("status") in ("done", "failed"):
            return d
        time.sleep(2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--videos", type=Path, required=True)
    ap.add_argument("--labels", type=Path, required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--local", action="store_true")
    mode.add_argument("--url")
    ap.add_argument("--key", default="")
    ap.add_argument("--tolerance", type=float, default=2.0, help="допуск таймкода, с")
    ap.add_argument("--out", type=Path, default=Path("eval_results.csv"))
    a = ap.parse_args()

    labels = load_labels(a.labels)
    files: dict[int, Path] = {}
    for p in sorted(a.videos.rglob("*")):
        if p.suffix.lower() in VIDEO_EXT and (n := number_of(p.name)) is not None:
            if n in files:
                print(f"! номер {n} у двух файлов: {files[n].name} и {p.name}")
            files[n] = p
    missing = sorted(set(labels) - set(files))
    if missing:
        print(f"! нет видео для разметки: {missing}")
    extra = sorted(set(files) - set(labels))
    if extra:
        print(f"! видео без разметки: {extra}")

    rows, tp, fp, fn, tn, errors, times = [], 0, 0, 0, 0, [], []
    for num in sorted(set(labels) & set(files)):
        lab, path = labels[num], files[num]
        t0 = time.monotonic()
        try:
            res = analyze_local(path) if a.local else analyze_api(path, a.url.rstrip("/"), a.key)
        except Exception as exc:  # noqa: BLE001
            print(f"{lab['name']:>6}  ОШИБКА {exc}")
            res = {"verdict": "error", "violations": []}
        sec = time.monotonic() - t0
        times.append(sec)
        pred = res.get("verdict")
        tcs = [v["timecode_sec"] for v in res.get("violations", [])]
        err = None
        if lab["verdict"] == "violation" and pred == "violation":
            tp += 1
            if lab["t"] is not None and tcs:
                err = min(abs(t - lab["t"]) for t in tcs)
                errors.append(err)
        elif lab["verdict"] == "violation":
            fn += 1
        elif pred == "violation":
            fp += 1
        else:
            tn += 1
        mark = "✓" if pred == lab["verdict"] else "✗"
        print(f"{lab['name']:>6} {mark} разметка={lab['verdict']:<12} модель={pred:<12} "
              f"t={lab['t']} → {tcs[:3]} {'' if err is None else f'Δ={err:.1f}с'} [{sec:.1f} с]")
        rows.append({"video": lab["name"], "file": path.name, "label": lab["verdict"], "label_t": lab["t"],
                     "pred": pred, "pred_t": ";".join(f"{t:.2f}" for t in tcs),
                     "types": ";".join(v["type"] for v in res.get("violations", [])),
                     "dt": "" if err is None else round(err, 2), "sec": round(sec, 1)})

    n = tp + fp + fn + tn
    if not n:
        print("Нет пар «видео + разметка».")
        return 1
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    print("\n── Итог ─────────────────────────────")
    print(f"Видео: {n}   accuracy вердикта: {(tp + tn) / n:.1%}")
    print(f"Нарушения: precision {prec:.1%}, recall {rec:.1%}   (TP {tp}, FP {fp}, FN {fn}, TN {tn})")
    if errors:
        within = sum(e <= a.tolerance for e in errors)
        print(f"Таймкод: медианная ошибка {statistics.median(errors):.1f} с, в пределах ±{a.tolerance:g} с — "
              f"{within}/{len(errors)}")
    print(f"Время: среднее {statistics.mean(times):.1f} с, максимум {max(times):.1f} с (лимит жюри 300 с)")
    with a.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Подробно по каждому видео: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
