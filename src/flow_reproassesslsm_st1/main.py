from openai import max_retries
from asyncio import timeouts
from crewai.flow import Flow, listen, start, router, or_
import pandas as pd
import json
import argparse

from flow_reproassesslsm_st1.crews.reprochecker_crew.reprochecker_crew import ReproCheckerCrew
from flow_reproassesslsm_st1.models import (
    ReproCheckState,
    ReproducibilityReport,
    FilterOutput,
    AvailabilityOutput,
    DatasetEntry,
    MethodEntry,
)
from flow_reproassesslsm_st1.config import INPUTS_PATH, OUTPUT_DIR

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

REPORT_TAIL_NAME = "_repro_report_llama4_scout"

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
    code_status = c.get("code_status")
    return MethodEntry(**{**c, "code_status": _METHOD_CODE_STATUS_ALIASES.get(code_status, code_status)})


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


class ReproCheckFlow(Flow[ReproCheckState]):

    @start()
    def load_inputs(self, crewai_trigger_payload: dict = None):       
        print("Loading inputs")

        if crewai_trigger_payload:
            self.state.publication_id = crewai_trigger_payload.get("publication_id", 0)
            self.state.pdf_file = crewai_trigger_payload.get("pdf_file", "")
            self.state.doi = crewai_trigger_payload.get("doi", "")
            self.state.abstract = crewai_trigger_payload.get("abstract", "")
            print(f"Using trigger payload: {crewai_trigger_payload}")

        if not self.state.pdf_file or not self.state.doi or not self.state.abstract:
            raise ValueError("'pdf_file', 'doi', and 'abstract' must all be provided.")

        print(f"PDF pdf_file: {self.state.pdf_file}")
        print(f"DOI: {self.state.doi}")

        try:
            self._crew = ReproCheckerCrew(pdf_file=self.state.pdf_file)
        except Exception as e:
            print(f"Error loading inputs: {e}")

    @listen(load_inputs)
    def filter_paper(self):
        df = pd.read_csv(INPUTS_PATH, sep=';')
        df.columns = df.columns.str.strip()
        _ensure_str_columns(df, ["Filter_Decision", "Filter_Reason"])

        mask = df["EID"].astype(str).str.strip() == str(self.state.publication_id).strip()
        if not mask.any():
            print(f"Warning: EID {self.state.publication_id} not found in {INPUTS_PATH}, decision not recorded.")
            return

        value = df.loc[mask, "Filter_Decision"].iloc[0]
        if pd.isna(value) or str(value).strip() not in ["INCLUDE", "EXCLUDE"]:
            print(f"Filtering paper (abstract-only): {self.state.pdf_file}")
            filter_result = self._crew.filter_crew().kickoff(
                inputs={"abstract": self.state.abstract}
            )
            self.state.filter_decision = filter_result.pydantic.decision
            self.state.filter_reason = filter_result.pydantic.reason

            df.loc[mask, "Filter_Decision"] = self.state.filter_decision
            df.loc[mask, "Filter_Reason"] = self.state.filter_reason
            df.to_csv(INPUTS_PATH, sep=';', index=False)

            return filter_result.pydantic.decision  # passed into the router
        else:
            print(f"Filter decision already recorded for EID={self.state.publication_id}, skipping.")
            self.state.filter_decision = df.loc[mask, "Filter_Decision"].iloc[0].strip()
            self.state.filter_reason = df.loc[mask, "Filter_Reason"].iloc[0].strip()
            return self.state.filter_decision

    @router(filter_paper)
    def route_on_filter(self, decision):
        return "included" if decision == "INCLUDE" else "excluded"

    @listen("excluded")
    def skip_paper(self):
        print(f"Paper skipped: {self.state.filter_reason}")
        # self.state.final_report = FilterOutput(
        #     decision=self.state.filter_decision,
        #     reason=self.state.filter_reason,
        # )

    @listen("included")
    def check_prefilled_availability(self):
        df = pd.read_csv(INPUTS_PATH, sep=';')
        df.columns = df.columns.str.strip()
        row = _get_row(df, self.state.publication_id)

        if row is not None and _row_has_prefilled_availability(df, row):
            print(f"Prefilled availability found for EID={self.state.publication_id}, skipping artifact availability check.")
            self.state.prefilled_availability = _availability_from_row(row)
            return "prefilled"

        print(f"No prefilled availability for EID={self.state.publication_id}, running full artifact availability check.")
        return "not_prefilled"

    @router(check_prefilled_availability)
    def route_on_availability(self, decision):
        return decision

    @listen("not_prefilled")
    def run_repro_check(self):
        print(f"Paper included, running reproducibility checks on: {self.state.pdf_file}")
        inputs = {"doi_url": f"https://doi.org/{self.state.doi}"}
        self._crew.repro_crew().kickoff(inputs=inputs)

        data_output = self._crew.check_data_reproducibility().output.pydantic
        method_output = self._crew.check_method_reproducibility().output.pydantic
        avail_output = self._crew.check_artifact_availability().output.pydantic
        assessment_output = self._crew.compile_final_report().output.pydantic

        self.state.final_report = ReproducibilityReport(
            datasets=data_output.datasets,
            methods=method_output.methods,
            availability=avail_output,
            reproducibility_assessment=assessment_output.reproducibility_assessment,
        )

        df = pd.read_csv(INPUTS_PATH, sep=';')
        df.columns = df.columns.str.strip()
        _ensure_str_columns(df, [
            "Datasets",
            "Methods",
            "Webpage_Access_Status",
            "Webpage_Data_Status",
            "Webpage_Data_Links",
            "Webpage_Code_Status",
            "Webpage_Code_Links",
            "Webpage_Author_Statement",
            "Reproducibility_Assessment",
        ])

        mask = df["EID"].astype(str).str.strip() == str(self.state.publication_id).strip()
        if not mask.any():
            print(f"Warning: EID {self.state.publication_id} not found in {INPUTS_PATH}, findings not recorded.")
            return

        report = self.state.final_report
        avail = report.availability

        df.loc[mask, "Datasets"] = json.dumps([d.model_dump() for d in report.datasets])
        df.loc[mask, "Methods"] = json.dumps([m.model_dump() for m in report.methods])

        df.loc[mask, "Webpage_Access_Status"] = avail.access_status
        df.loc[mask, "Webpage_Data_Status"] = avail.data_status
        df.loc[mask, "Webpage_Data_Links"] = json.dumps([d.model_dump() for d in avail.data_links]) if avail.data_links else ""
        df.loc[mask, "Webpage_Code_Status"] = avail.code_status
        df.loc[mask, "Webpage_Code_Links"] = json.dumps([c.model_dump() for c in avail.code_links]) if avail.code_links else ""
        df.loc[mask, "Webpage_Author_Statement"] = avail.author_statement or ""

        df.loc[mask, "Reproducibility_Assessment"] = report.reproducibility_assessment

        df.to_csv(INPUTS_PATH, sep=';', index=False)

    @listen("prefilled")
    def run_repro_check_from_csv(self):
        print(f"Paper included, running reproducibility checks (availability pre-filled from CSV) on: {self.state.pdf_file}")
        avail_output = self.state.prefilled_availability
        inputs = {"availability_summary": avail_output.model_dump_json(indent=2)}
        self._crew.repro_crew_from_csv().kickoff(inputs=inputs)

        data_output = self._crew.check_data_reproducibility().output.pydantic
        method_output = self._crew.check_method_reproducibility().output.pydantic
        assessment_output = self._crew.compile_final_report_from_availability().output.pydantic

        self.state.final_report = ReproducibilityReport(
            datasets=data_output.datasets,
            methods=method_output.methods,
            availability=avail_output,
            reproducibility_assessment=assessment_output.reproducibility_assessment,
        )

        df = pd.read_csv(INPUTS_PATH, sep=';')
        df.columns = df.columns.str.strip()
        _ensure_str_columns(df, ["Datasets", "Methods", "Reproducibility_Assessment"])

        mask = df["EID"].astype(str).str.strip() == str(self.state.publication_id).strip()
        if not mask.any():
            print(f"Warning: EID {self.state.publication_id} not found in {INPUTS_PATH}, findings not recorded.")
            return

        report = self.state.final_report

        df.loc[mask, "Datasets"] = json.dumps([d.model_dump() for d in report.datasets])
        df.loc[mask, "Methods"] = json.dumps([m.model_dump() for m in report.methods])
        df.loc[mask, "Reproducibility_Assessment"] = report.reproducibility_assessment

        df.to_csv(INPUTS_PATH, sep=';', index=False)

    @listen(or_(run_repro_check, run_repro_check_from_csv))
    def save_report(self):
        try:
            print("Saving report")
            output_file = OUTPUT_DIR / f"{self.state.publication_id}{REPORT_TAIL_NAME}.json"
            
            report = self.state.final_report.model_dump_json(indent=2)
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"Report saved to {output_file}")
        except Exception as e:
            print(f"Error saving report: {e}.\nFinal report:\n{self.state.final_report}")

def kickoff(wait_seconds=60, max_retries=2):
    import os
    import time

    try:
        df = pd.read_csv(INPUTS_PATH, sep=';')
    except Exception as e:
        print(f"Error reading CSV: {e}")
        raise   
        
    for _, row in df.iterrows():

        # Check if a reproducibility report isn't already available
        if os.path.exists(OUTPUT_DIR / f"{row['EID']}{REPORT_TAIL_NAME}.json"):
            print(f"Reproducibility report already available for EID={row['EID']}")
            continue

        # Skip excluded papers entirely:
        if row["Filter_Decision"] == "EXCLUDE" or row["Human_Filter_Decision"] == "EXCLUDE":
            print(f"Skipping EID={row['EID']} (excluded)")
            continue

        publication_id = str(row["EID"]).strip()
        doi = str(row["DOI"]).strip()
        abstract = str(row["Abstract"]).strip()

        inputs = {
            "publication_id": publication_id,
            "pdf_file": f"{publication_id}.pdf",
            "doi": doi,
            "abstract": abstract,
        }

        print(f"--- Running ReproCheckFlow for EID={publication_id} ---")
        
        attempt = 0
        while True:
            try:
                repro_check_flow = ReproCheckFlow()
                repro_check_flow.kickoff(inputs=inputs)
            except Exception as e:
                attempt += 1
                print(f"Error processing EID={publication_id}: {e}")
                if attempt > max_retries:
                    print(f"Giving up on EID={publication_id} after {attempt} attempt(s)")
                    break
                print(f"Retrying EID={publication_id} in {wait_seconds}s (attempt {attempt}/{max_retries})...")
                time.sleep(wait_seconds)

def plot():
    repro_check_flow = ReproCheckFlow()
    repro_check_flow.plot()


def run_with_trigger():
    """Run the flow with a single trigger payload (e.g. one row's worth of data)."""
    import json
    import sys

    if len(sys.argv) < 2:
        raise Exception("No trigger payload provided. Please provide JSON payload as argument.")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("Invalid JSON payload provided as argument")

    repro_check_flow = ReproCheckFlow()

    try:
        result = repro_check_flow.kickoff({"crewai_trigger_payload": trigger_payload})
        return result
    except Exception as e:
        raise Exception(f"An error occurred while running the flow with trigger: {e}")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Run reproducibility flow.")
    parser.add_argument("--wait-seconds", type=int, default=60, help="Seconds to wait before retrying a failed EID")
    parser.add_argument("--max-retries", type=int, default=2, help="Max retry attempts per EID before giving up")
    args = parser.parse_args()

    kickoff(wait_seconds=args.wait_seconds, max_retries=args.max_retries)