# Usage:
#   First run (starts round 1, draws first batch per category):
#     python sample_reproducibility_sequential.py
#
#   After labeling the flagged rows (fill in Manual_True_Label), re-run the
#   SAME command. It will report the current Wilson CI per category and
#   either say "stop" or draw the next batch.
#
# Optional flags:
#   --confidence 0.95 --margin-error 0.05 --proportion 0.5   (used ONLY to compute
#       the Cochran ceiling, i.e. the max n we'd ever sample for a category)
#   --margin-target 0.10   (the CI half-width that triggers "stop" -- can be looser
#       than --margin-error, which is why this is a separate flag)
#   --batch-size 15
#   --seed 42

import argparse
import math
from pathlib import Path

import pandas as pd

INPUTS_PATH = Path(__file__).resolve().parent.parent / "publications" / "scopus_export_Jul_22_2026_query1.csv"
OUTPUT_PATH = INPUTS_PATH.with_stem(INPUTS_PATH.stem + "_reproducibility_check")

STATUS_COLUMN = "Reproducibility_Status"
CATEGORIES = ["REPRODUCIBLE", "PARTIALLY_REPRODUCIBLE", "NOT_REPRODUCIBLE"]

FLAG_COLUMN = "Assessment_Decision_Check"
FLAG_VALUE = "RANDOMLY_CHECKED"
TRUE_LABEL_COLUMN = "Assessment_Decision_Check_Human_Review"   # you fill this in by hand after reading each PDF
BATCH_COLUMN = "Check_Batch"              # which round a row was drawn in

SEED = 42
Z_SCORES = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}


def cochran_ceiling(population: int, confidence: float, margin_error: float, proportion: float) -> int:
    """Cochran's formula + FPC -- used here as an UPPER BOUND on how many we'll ever sample."""
    z = Z_SCORES[confidence]
    n0 = (z**2 * proportion * (1 - proportion)) / margin_error**2
    n = n0 / (1 + (n0 - 1) / population)
    return min(population, math.ceil(n))


def wilson_interval_fpc(correct: int, n: int, population: int, confidence: float) -> tuple[float, float, float]:
    """Wilson score interval for a proportion, with finite population correction on the half-width."""
    z = Z_SCORES[confidence]
    p_hat = correct / n

    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    half_width = (z * math.sqrt((p_hat * (1 - p_hat) / n) + (z**2 / (4 * n**2)))) / denom

    fpc = math.sqrt((population - n) / (population - 1)) if population > n else 0.0
    half_width *= fpc

    return center, max(0.0, center - half_width), min(1.0, center + half_width)


def process_category(df: pd.DataFrame, category: str, batch_size: int, margin_target: float,
                      ceiling: int, confidence: float, seed: int) -> pd.DataFrame:
    status = df[STATUS_COLUMN].astype(str).str.strip().str.upper()
    pool = df[status == category]
    population = len(pool)

    if population == 0:
        print(f"  {category}: no rows found, skipping.")
        return df

    checked = pool[pool[FLAG_COLUMN] == FLAG_VALUE]
    labeled = checked[checked[TRUE_LABEL_COLUMN].notna()]
    n = len(labeled)

    if n > 0:
        correct = (labeled[TRUE_LABEL_COLUMN].astype(str).str.strip().str.upper() == category).sum()
        center, lo, hi = wilson_interval_fpc(correct, n, population, confidence)
        half_width = (hi - lo) / 2
        print(f"  {category}: n={n}/{population} labeled, precision={center:.1%}, "
              f"{confidence:.0%} CI=[{lo:.1%}, {hi:.1%}] (±{half_width:.1%})")

        if half_width <= margin_target:
            print(f"    -> STOP: CI half-width within target (±{margin_target:.0%}).")
            return df

        if n >= ceiling:
            print(f"    -> STOP: reached Cochran ceiling (n={ceiling}) without hitting target margin. "
                  f"Report the achieved CI as-is.")
            return df
    else:
        print(f"  {category}: population={population}, Cochran ceiling={ceiling} (no samples labeled yet)")

    # Draw next batch from whatever hasn't been flagged yet, capped so we never exceed the ceiling
    remaining_pool = pool[pool[FLAG_COLUMN] != FLAG_VALUE]
    room_left = ceiling - n
    take = min(batch_size, room_left, len(remaining_pool))

    if take <= 0 or remaining_pool.empty:
        print(f"    -> STOP: no more room under the ceiling, or no unsampled items left.")
        return df

    next_batch = remaining_pool.sample(n=take, random_state=seed)
    prior_round = checked[BATCH_COLUMN].max()
    round_num = 1 if pd.isna(prior_round) else int(prior_round) + 1

    df.loc[df["t_ID"].isin(next_batch["t_ID"]), FLAG_COLUMN] = FLAG_VALUE
    df.loc[df["t_ID"].isin(next_batch["t_ID"]), BATCH_COLUMN] = round_num
    print(f"    -> Drew batch {round_num}: {take} new item(s) to label "
          f"({n + take}/{population} total flagged so far, ceiling={ceiling}).")

    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Sequential/adaptive sampling: draws a small batch per category, and on each "
            "re-run reports the current Wilson CI (with FPC) and either stops or draws another "
            "batch, capped at the Cochran-derived ceiling."
        )
    )
    parser.add_argument("--confidence", type=float, default=0.95, choices=sorted(Z_SCORES))
    parser.add_argument("--margin-error", type=float, default=0.05, help="Used only to compute the Cochran ceiling.")
    parser.add_argument("--proportion", type=float, default=0.5, help="Used only to compute the Cochran ceiling.")
    parser.add_argument("--margin-target", type=float, default=0.10, help="CI half-width that triggers stopping.")
    parser.add_argument("--batch-size", type=int, default=15)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    # Resume from the working file if it exists (has our tracking columns); otherwise start fresh from the raw export.
    source_path = OUTPUT_PATH if OUTPUT_PATH.exists() else INPUTS_PATH
    print(f"Reading from: {source_path.resolve()}")

    df = pd.read_csv(source_path, sep=";")
    df.columns = df.columns.str.strip()

    if FLAG_COLUMN not in df.columns:
        df[FLAG_COLUMN] = pd.NA
    if TRUE_LABEL_COLUMN not in df.columns:
        df[TRUE_LABEL_COLUMN] = pd.NA
    if BATCH_COLUMN not in df.columns:
        df[BATCH_COLUMN] = pd.NA

    print("Sequential sampling status (Wilson CI + FPC, Cochran ceiling):")
    for category in CATEGORIES:
        status = df[STATUS_COLUMN].astype(str).str.strip().str.upper()
        population = (status == category).sum()
        if population == 0:
            print(f"  {category}: no rows found, skipping.")
            continue
        ceiling = cochran_ceiling(population, args.confidence, args.margin_error, args.proportion)
        df = process_category(df, category, args.batch_size, args.margin_target, ceiling, args.confidence, args.seed)

    df.to_csv(OUTPUT_PATH, sep=";", index=False)
    flagged = df[df[FLAG_COLUMN] == FLAG_VALUE]
    labeled = flagged[flagged[TRUE_LABEL_COLUMN].notna()]
    print(f"\nTotal flagged so far: {len(flagged)} ({len(labeled)} labeled). Wrote {OUTPUT_PATH.resolve()}")