# Usage: python scripts/sample_excluded_for_check.py -n 20 --seed 42

import argparse
from pathlib import Path

import pandas as pd

# Defined locally (rather than imported from flow_reproassesslsm_st1.config) to avoid
# that module's side-effecting crewai/LLM initialization, which this script doesn't need.
INPUTS_PATH = Path(__file__).resolve().parent.parent / "publications" / "scopus_export_Jul_22_2026_query1.csv"

FLAG_COLUMN = "Filter_Decision_Excluded_Check"
FLAG_VALUE = "RANDOMLY_CHECKED"


def sample_excluded(df: pd.DataFrame, n: int, seed: int | None) -> pd.DataFrame:
    excluded = df[df["Filter_Decision"].astype(str).str.strip().str.upper() == "EXCLUDE"]

    if n > len(excluded):
        raise ValueError(f"Requested n={n} but only {len(excluded)} EXCLUDE rows are available.")

    sampled_ids = excluded["t_ID"].sample(n=n, random_state=seed)

    if FLAG_COLUMN not in df.columns:
        df[FLAG_COLUMN] = pd.NA

    df.loc[df["t_ID"].isin(sampled_ids), FLAG_COLUMN] = FLAG_VALUE
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Randomly flag a subsample of EXCLUDEd papers for manual re-check.")
    parser.add_argument("-n", type=int, required=True, help="Number of EXCLUDE rows to flag.")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible sampling.")
    parser.add_argument("--in-place", action="store_true", help="Overwrite the source CSV instead of writing a copy.")
    args = parser.parse_args()

    print(f"INPUTS_PATH = {INPUTS_PATH.resolve()}")

    df = pd.read_csv(INPUTS_PATH, sep=";")
    df.columns = df.columns.str.strip()

    df = sample_excluded(df, n=args.n, seed=args.seed)

    out_path = INPUTS_PATH if args.in_place else INPUTS_PATH.with_stem(INPUTS_PATH.stem + "_excluded_check")
    df.to_csv(out_path, sep=";", index=False)

    flagged = df[df[FLAG_COLUMN] == FLAG_VALUE]
    print(f"Flagged {len(flagged)} rows as '{FLAG_VALUE}'. Wrote {out_path.resolve()}")