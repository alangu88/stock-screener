from __future__ import annotations

from io import StringIO

import pandas as pd

from src.screener.result import RESULT_COLUMNS


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    prepared = df.reindex(columns=list(RESULT_COLUMNS))
    buffer = StringIO()
    prepared.to_csv(buffer, index=False)
    return buffer.getvalue().encode('utf-8')
