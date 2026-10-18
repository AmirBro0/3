"""Статическое демо интерфейса без сервера: показать дизайн команде или жюри.

  python scripts/build_preview.py                 # → preview.html, открывается в браузере
  python scripts/build_preview.py --fragment      # → фрагмент без <html>, для публикации как артефакт

В демо нет анализа: показывается пример отчёта, а загрузка своего видео имитируется.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import VERSION  # noqa: E402
from app.page import fragment, render_page  # noqa: E402
from app.rules.catalog import catalog_payload  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=ROOT / "preview.html")
    p.add_argument("--fragment", action="store_true")
    a = p.parse_args()
    boot = {
        "backend": False,
        "version": VERSION,
        "catalog": catalog_payload(),
        "limits": {"deadline_sec": 240, "max_upload_mb": 500},
    }
    html = fragment(boot) if a.fragment else render_page(boot)
    a.out.write_text(html, encoding="utf-8")
    print(f"{a.out} ({len(html) // 1024} КБ)")


if __name__ == "__main__":
    main()
