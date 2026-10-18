"""Проверка API так, как его вызывает жюри (раздел 10 ТЗ).

  python scripts/smoke_test.py --url http://localhost:8000 --key <ключ> --file video.mov
  python scripts/smoke_test.py --url https://oko.example.kz --key <ключ> --file video.mov --parallel 5

Что проверяется:
  * запрос без ключа и с неверным ключом → 401;
  * POST /api/v1/analyze → job_id;
  * опрос GET /api/v1/jobs/{id} до done/failed, укладываемся ли в 300 с;
  * схема ответа: поля и типы, verdict согласован с violations, 1–3 кадра JPEG в base64,
    таймкоды неотрицательные, в description есть ссылка на пункт или статью.
--parallel N отправляет N копий одновременно: так жюри может прогонять тестовые видео.
"""
from __future__ import annotations

import argparse
import base64
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

LIMIT_SEC = 300


def check_schema(d: dict) -> list[str]:
    problems: list[str] = []
    for key, typ in (("job_id", str), ("status", str), ("verdict", str), ("violations", list)):
        if not isinstance(d.get(key), typ):
            problems.append(f"поле {key!r} отсутствует или не {typ.__name__}")
    if problems:
        return problems
    if d["status"] != "done":
        problems.append(f"status={d['status']!r}, ожидался 'done'")
    if d["verdict"] not in ("violation", "no_violation"):
        problems.append(f"verdict={d['verdict']!r} — допустимы только violation / no_violation")
    if (d["verdict"] == "violation") != bool(d["violations"]):
        problems.append("verdict не согласован со списком violations")
    for i, v in enumerate(d["violations"], 1):
        p = f"нарушение {i}:"
        if not isinstance(v.get("type"), str) or not v["type"].strip():
            problems.append(f"{p} пустой type")
        if not isinstance(v.get("timecode_sec"), (int, float)) or v["timecode_sec"] < 0:
            problems.append(f"{p} timecode_sec не число ≥ 0")
        desc = v.get("description")
        if not isinstance(desc, str) or not desc.strip():
            problems.append(f"{p} пустой description")
        elif "п." not in desc and "ст." not in desc:
            problems.append(f"{p} в description нет ссылки на пункт/статью (критерий 4)")
        frames = v.get("evidence_frames")
        if not isinstance(frames, list) or not 1 <= len(frames) <= 3:
            problems.append(f"{p} evidence_frames должно быть 1–3 кадра")
            continue
        for k, f in enumerate(frames, 1):
            if not isinstance(f.get("timestamp_sec"), (int, float)) or f["timestamp_sec"] < 0:
                problems.append(f"{p} кадр {k}: timestamp_sec не число ≥ 0")
            try:
                raw = base64.b64decode(f.get("image_base64", ""), validate=True)
                if raw[:2] != b"\xff\xd8":
                    problems.append(f"{p} кадр {k}: это не JPEG")
            except (ValueError, TypeError):
                problems.append(f"{p} кадр {k}: image_base64 не декодируется")
    return problems


def run_one(url: str, key: str, path: Path, tag: str) -> dict:
    t0 = time.monotonic()
    with path.open("rb") as fh:
        r = requests.post(f"{url}/api/v1/analyze", headers={"X-API-Key": key},
                          files={"file": (path.name, fh, "video/quicktime")}, timeout=120)
    if r.status_code != 200 or "job_id" not in r.json():
        return {"tag": tag, "ok": False, "error": f"POST {r.status_code}: {r.text[:200]}", "sec": time.monotonic() - t0}
    job_id = r.json()["job_id"]
    while True:
        g = requests.get(f"{url}/api/v1/jobs/{job_id}", headers={"X-API-Key": key}, timeout=60)
        d = g.json()
        if d.get("status") in ("done", "failed"):
            break
        if time.monotonic() - t0 > LIMIT_SEC + 30:
            return {"tag": tag, "ok": False, "error": "нет ответа дольше 5 минут", "sec": time.monotonic() - t0}
        time.sleep(2)
    sec = time.monotonic() - t0
    problems = check_schema(d) if d.get("status") == "done" else [f"failed: {d.get('error')}"]
    if sec > LIMIT_SEC:
        problems.append(f"ответ за {sec:.0f} с — дольше лимита 300 с")
    return {"tag": tag, "ok": not problems, "problems": problems, "sec": sec, "job_id": job_id,
            "verdict": d.get("verdict"), "violations": [(v["type"], v["timecode_sec"]) for v in d.get("violations", [])]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--file", type=Path, required=True)
    ap.add_argument("--parallel", type=int, default=1)
    a = ap.parse_args()
    url = a.url.rstrip("/")
    failed = 0

    for headers, name in (({}, "без ключа"), ({"X-API-Key": "wrong-key"}, "с неверным ключом")):
        with a.file.open("rb") as fh:
            r = requests.post(f"{url}/api/v1/analyze", headers=headers, files={"file": (a.file.name, fh)}, timeout=60)
        ok = r.status_code == 401
        failed += not ok
        print(f"{'OK  ' if ok else 'FAIL'} запрос {name} → {r.status_code}")

    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        results = list(pool.map(lambda i: run_one(url, a.key, a.file, f"#{i + 1}"), range(a.parallel)))
    for res in results:
        failed += not res["ok"]
        print(f"{'OK  ' if res['ok'] else 'FAIL'} {res['tag']} {res['sec']:.1f} с, verdict={res.get('verdict')}, "
              f"нарушения={res.get('violations')}")
        for p in res.get("problems", []) + ([res["error"]] if "error" in res else []):
            print(f"       · {p}")
    times = sorted(r["sec"] for r in results)
    if len(times) > 1:
        p95 = times[min(len(times) - 1, int(len(times) * 0.95))]
        print(f"Время ответа: медиана {times[len(times) // 2]:.1f} с, p95 {p95:.1f} с, максимум {times[-1]:.1f} с "
              f"(лимит жюри {LIMIT_SEC} с)")
    print("Итог:", "всё в порядке" if not failed else f"проблем: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
