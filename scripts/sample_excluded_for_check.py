# Usage: python scripts/sample_excluded_for_check.py
# Optional: --confidence 0.95 --margin-error 0.05 --proportion 0.5 --seed 42

import argparse
from pathlib import Path

import pandas as pd

from sample_reproducibility_for_check import cochran_sample_size, Z_SCORES

# Defined locally (rather than imported from flow_reproassesslsm_st1.config) to avoid
# that module's side-effecting crewai/LLM initialization, which this script doesn't need.
INPUTS_PATH = Path(__file__).resolve().parent.parent / "publications" / "scopus_export_Jul_22_2026_query1.csv"

FLAG_COLUMN = "Filter_Decision_Excluded_Check"
FLAG_VALUE = "RANDOMLY_CHECKED"

SEED = 42


def sample_excluded(df: pd.DataFrame, confidence: float, margin_error: float, proportion: float, seed: int) -> pd.DataFrame:
    excluded = df[df["Filter_Decision"].astype(str).str.strip().str.upper() == "EXCLUDE"]

    population = len(excluded)
    n = cochran_sample_size(population, confidence, margin_error, proportion)
    print(f"  EXCLUDE: population={population}, sample size={n}")

    sampled_ids = excluded["t_ID"].sample(n=n, random_state=seed)

    if FLAG_COLUMN not in df.columns:
        df[FLAG_COLUMN] = pd.NA

    df.loc[df["t_ID"].isin(sampled_ids), FLAG_COLUMN] = FLAG_VALUE
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Randomly flag a subsample of EXCLUDEd papers for manual re-check, sized via "
            "Cochran's formula with finite population correction (FPC)."
        )
    )
    parser.add_argument(
        "--confidence", type=float, default=0.95, choices=sorted(Z_SCORES), help="Confidence level (default: 0.95)."
    )
    parser.add_argument("--margin-error", type=float, default=0.05, help="Margin of error e (default: 0.05).")
    parser.add_argument(
        "--proportion", type=float, default=0.5, help="Expected proportion p, max variability at 0.5 (default: 0.5)."
    )
    parser.add_argument("--seed", type=int, default=SEED, help=f"Random seed for reproducible sampling (default: {SEED}).")
    parser.add_argument("--in-place", action="store_true", help="Overwrite the source CSV instead of writing a copy.")
    args = parser.parse_args()

    print(f"INPUTS_PATH = {INPUTS_PATH.resolve()}")

    df = pd.read_csv(INPUTS_PATH, sep=";")
    df.columns = df.columns.str.strip()

    print("Sample size (Cochran's formula + FPC):")
    df = sample_excluded(
        df, confidence=args.confidence, margin_error=args.margin_error, proportion=args.proportion, seed=args.seed
    )

    out_path = INPUTS_PATH if args.in_place else INPUTS_PATH.with_stem(INPUTS_PATH.stem + "_excluded_check")
    df.to_csv(out_path, sep=";", index=False)

    flagged = df[df[FLAG_COLUMN] == FLAG_VALUE]
    print(f"Flagged {len(flagged)} rows as '{FLAG_VALUE}'. Wrote {out_path.resolve()}")