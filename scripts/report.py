"""Run with python -m scripts.report --as-of YYYY-MM-DD --output reports/performance.csv."""
import argparse
from datetime import date
from pathlib import Path

from farm.analytics import batch_metrics
from farm.db import make_engine, settings
from farm.services import read_data


def main():
    parser = argparse.ArgumentParser(description="Export cumulative fish farm KPIs.")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--output", type=Path, default=Path("reports/performance.csv"))
    args = parser.parse_args()
    _, url = settings()
    engine = make_engine(url)
    _, batches, logs = read_data(engine)
    result = batch_metrics(batches, logs, args.as_of)
    for col in ("batch", "species"):
        result[col] = result[col].map(lambda x: "'" + x if x.lstrip().startswith(("=", "+", "-", "@")) else x)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(f"Exported {len(result)} batches to {args.output}")


if __name__ == "__main__":
    main()
