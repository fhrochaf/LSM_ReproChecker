import json

import pandas as pd

from flow_reproassesslsm_st1.models import AvailabilityOutput, DatasetEntry, MethodEntry

# Webpage_* columns filled in by run_repro_check / already present in the
# inputs CSV. If the required ones are present for a row, artifact
# availability checking is skipped and those values are reused instead.
REQUIRED_AVAILABILITY_FIELDS = [
    "Webpage_Access_Status",
    "Webpage_Data_Status",
    "Webpage_Code_Status",
]

# Some rows were prefilled from an older/manual process whose JSON shape and
# status vocabulary differ from what the current pipeline writes: entries may
# come wrapped as {"datasets": [...]} / {"methods": [...]} instead of a bare
# array, and use a richer status vocabulary instead of MENTIONED/NOT_MENTIONED.
_DATASET_STATUS_ALIASES = {
    "AVAILABLE": "MENTIONED",
    "PARTIALLY_AVAILABLE": "MENTIONED",
    "NOT_AVAILABLE": "NOT_MENTIONED",
}
_METHOD_CODE_STATUS_ALIASES = {
    "FOUND": "MENTIONED",
    "NOT_FOUND": "NOT_MENTIONED",
    "N/A": "NOT_MENTIONED",
}


def _ensure_str_columns(df: pd.DataFrame, columns: list[str]) -> None:
    """Force the given columns to object dtype (creating them if absent).

    Columns that are all-blank in the CSV get inferred as float64 (NaN) on
    read; assigning a string into them via .loc then raises LossySetitemError
    instead of silently upcasting, so we normalize the dtype up front.
    """
    for col in columns:
        if col not in df.columns:
            df[col] = pd.Series([pd.NA] * len(df), index=df.index, dtype="object")
        elif df[col].dtype != object:
            df[col] = df[col].astype(object)


def _get_row(df: pd.DataFrame, publication_id: str) -> pd.Series | None:
    mask = df["EID"].astype(str).str.strip() == str(publication_id).strip()
    if not mask.any():
        return None
    return df.loc[mask].iloc[0]


def _row_has_prefilled_availability(df: pd.DataFrame, row: pd.Series) -> bool:
    if not all(field in df.columns for field in REQUIRED_AVAILABILITY_FIELDS):
        return False

    if row.get(REQUIRED_AVAILABILITY_FIELDS[0]).strip() != "ACCESSIBLE":
        return False
    else:
        return any(pd.notna(row.get(field)) and str(row.get(field)).strip() for field in REQUIRED_AVAILABILITY_FIELDS[1:])


def _parse_json_list(value, wrapper_key: str) -> list[dict]:
    if value is None or pd.isna(value) or not str(value).strip():
        return []
    parsed = json.loads(value)
    if isinstance(parsed, dict):
        parsed = parsed.get(wrapper_key, [])
    return parsed


def _coerce_dataset_entry(d: dict) -> DatasetEntry:
    status = d.get("status")
    return DatasetEntry(**{**d, "status": _DATASET_STATUS_ALIASES.get(status, status)})


def _coerce_method_entry(c: dict) -> MethodEntry:
    """Coerce a method dict into MethodEntry, translating both the current
    shape (name/method_type/source/link/status/verbatim) and the legacy
    shape (name/method_type/summary/code_status/code_link/reused_citation)
    written by older/manual prefills.
    """
    status = c.get("status", c.get("code_status"))
    return MethodEntry(
        name=c.get("name"),
        method_type=c.get("method_type"),
        source=c.get("source", c.get("reused_citation")),
        link=c.get("link", c.get("code_link")),
        status=_METHOD_CODE_STATUS_ALIASES.get(status, status),
        verbatim=c.get("verbatim"),
    )


def _availability_from_row(row: pd.Series) -> AvailabilityOutput:
    author_statement = row.get("Webpage_Author_Statement")
    return AvailabilityOutput(
        access_status=str(row["Webpage_Access_Status"]).strip(),
        data_status=str(row["Webpage_Data_Status"]).strip(),
        data_links=[_coerce_dataset_entry(d) for d in _parse_json_list(row.get("Webpage_Data_Links"), "datasets")],
        code_status=str(row["Webpage_Code_Status"]).strip(),
        code_links=[_coerce_method_entry(c) for c in _parse_json_list(row.get("Webpage_Code_Links"), "methods")],
        author_statement=str(author_statement).strip() if pd.notna(author_statement) and str(author_statement).strip() else None,
    )
