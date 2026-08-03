"""reports_public/index.json 維護邏輯測試（對應 T4-2：純靜態網站要靠索引檔知道有哪些日期可選）。"""

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.daily_pipeline as pipeline


@pytest.fixture
def tmp_index(monkeypatch):
    d = tempfile.mkdtemp()
    index_path = Path(d) / "reports_public" / "index.json"
    monkeypatch.setattr(pipeline, "PUBLIC_INDEX_PATH", index_path)
    yield index_path
    shutil.rmtree(d, ignore_errors=True)


def test_first_call_creates_index_with_one_date(tmp_index):
    pipeline._update_public_index("2026-08-03")
    assert pipeline._load_json(tmp_index, None) == ["2026-08-03"]


def test_repeated_dates_do_not_duplicate(tmp_index):
    pipeline._update_public_index("2026-08-03")
    pipeline._update_public_index("2026-08-03")
    assert pipeline._load_json(tmp_index, None) == ["2026-08-03"]


def test_index_stays_sorted_regardless_of_call_order(tmp_index):
    pipeline._update_public_index("2026-08-05")
    pipeline._update_public_index("2026-08-03")
    pipeline._update_public_index("2026-08-04")
    assert pipeline._load_json(tmp_index, None) == ["2026-08-03", "2026-08-04", "2026-08-05"]
