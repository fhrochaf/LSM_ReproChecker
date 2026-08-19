from crewai.flow import Flow, listen, start, router, or_
import pandas as pd
import json
import argparse

from flow_reproassesslsm_st1.crews.reprochecker_crew.reprochecker_crew import ReproCheckerCrew, MULTI_RUN_COUNT
from flow_reproassesslsm_st1.models import (
    ReproCheckState,
    ReproducibilityReport,
)
from flow_reproassesslsm_st1.config import INPUTS_PATH, OUTPUT_DIR
from flow_reproassesslsm_st1.utils import (
    _ensure_str_columns,
    _get_row,
    _row_has_prefilled_availability,
    _availability_from_row,
    merge_entries,
)

REPORT_TAIL_NAME = "_report_gemini3_1_flash_lite"


class ReproCheckFlow(Flow[ReproCheckState]):

    @start()
    def load_inputs(self, crewai_trigger_payload: dict = None):       
        print("Loading inputs")

        if crewai_trigger_payload:
            self.state.publication_id = crewai_trigger_payload.get("publication_id", 0)
            self.state.pdf_file = crewai_trigger_payload.get("pdf_file", "")
            self.state.doi = crewai_trigger_payload.get("doi", "")
            self.state.abstract = crewai_trigger_payload.get("abstract", "")
            self.state.use_full_text_tool = crewai_trigger_payload.get(
                "use_full_text_tool", False
            )
            print(f"Using trigger payload: {crewai_trigger_payload}")

        if not self.state.pdf_file or not self.state.doi or not self.state.abstract:
            raise ValueError("'pdf_file', 'doi', and 'abstract' must all be provided.")

        print(f"PDF pdf_file: {self.state.pdf_file}")
        print(f"DOI: {self.state.doi}")
        print(f"Use full-text PDF tool: {self.state.use_full_text_tool}")

        try:
            self._crew = ReproCheckerCrew(
                pdf_file=self.state.pdf_file,
                use_full_text_tool=self.state.use_full_text_tool,
            )
        except Exception as e:
            print(f"Error loading inputs: {e}")
            raise e

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
        print(f"Paper included, running reproducibility checks (x{MULTI_RUN_COUNT} runs, reconciled) on: {self.state.pdf_file}")
        inputs = {"doi_url": f"https://doi.org/{self.state.doi}"}
        self._crew.repro_crew_multi_check().kickoff(inputs=inputs)

        data_runs = [t.output.pydantic.datasets for t in self._crew._data_runs]
        method_runs = [t.output.pydantic.methods for t in self._crew._method_runs]
        consolidated_datasets = merge_entries(data_runs)
        consolidated_methods = merge_entries(method_runs)
        avail_output = self._crew.check_artifact_availability().output.pydantic

        self._crew.consolidated_report_crew().kickoff(inputs={
            "consolidated_datasets": json.dumps([d.model_dump() for d in consolidated_datasets]),
            "consolidated_methods": json.dumps([m.model_dump() for m in consolidated_methods]),
            "availability_summary": avail_output.model_dump_json(indent=2),
        })

        assessment_output = self._crew.compile_final_report_from_consolidated().output.pydantic

        self.state.final_report = ReproducibilityReport(
            datasets=consolidated_datasets,
            methods=consolidated_methods,
            availability=avail_output,
            reproducibility_status=assessment_output.reproducibility_status,
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
            "Reproducibility_Status",
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

        df.loc[mask, "Reproducibility_Status"] = report.reproducibility_status
        df.loc[mask, "Reproducibility_Assessment"] = report.reproducibility_assessment

        df.to_csv(INPUTS_PATH, sep=';', index=False)

    @listen("prefilled")
    def run_repro_check_from_csv(self):
        print(f"Paper included, running reproducibility checks (x{MULTI_RUN_COUNT} runs, reconciled; availability pre-filled from CSV) on: {self.state.pdf_file}")
        avail_output = self.state.prefilled_availability

        self._crew.repro_crew_multi_check_from_csv().kickoff(inputs={})

        data_runs = [t.output.pydantic.datasets for t in self._crew._data_runs]
        method_runs = [t.output.pydantic.methods for t in self._crew._method_runs]
        consolidated_datasets = merge_entries(data_runs)
        consolidated_methods = merge_entries(method_runs)

        self._crew.consolidated_report_crew().kickoff(inputs={
            "consolidated_datasets": json.dumps([d.model_dump() for d in consolidated_datasets]),
            "consolidated_methods": json.dumps([m.model_dump() for m in consolidated_methods]),
            "availability_summary": avail_output.model_dump_json(indent=2),
        })

        assessment_output = self._crew.compile_final_report_from_consolidated().output.pydantic

        self.state.final_report = ReproducibilityReport(
            datasets=consolidated_datasets,
            methods=consolidated_methods,
            availability=avail_output,
            reproducibility_status=assessment_output.reproducibility_status,
            reproducibility_assessment=assessment_output.reproducibility_assessment
        )

        df = pd.read_csv(INPUTS_PATH, sep=';')
        df.columns = df.columns.str.strip()
        _ensure_str_columns(df, ["Datasets", "Methods", "Reproducibility_Status", "Reproducibility_Assessment"])

        mask = df["EID"].astype(str).str.strip() == str(self.state.publication_id).strip()
        if not mask.any():
            print(f"Warning: EID {self.state.publication_id} not found in {INPUTS_PATH}, findings not recorded.")
            return

        report = self.state.final_report

        df.loc[mask, "Datasets"] = json.dumps([d.model_dump() for d in report.datasets])
        df.loc[mask, "Methods"] = json.dumps([m.model_dump() for m in report.methods])
        df.loc[mask, "Reproducibility_Status"] = report.reproducibility_status
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

def kickoff(max_papers=None, check_paper_only=None, wait_seconds=None, max_retries=None, use_full_text_tool=None):
    import os
    import sys
    import time

    # `uv run kickoff` invokes this function directly
    # CLI flags are parsed here from sys.argv. Explicit function args (e.g. when
    # kickoff() is called programmatically) still take precedence over them.
    parser = argparse.ArgumentParser(description="Run reproducibility flow.")
    parser.add_argument("--max-papers", type=int, default=None, help="Max number of papers to process")
    parser.add_argument("--check-paper-only", type=str, default=None, help="Check only a specific paper (EID)")
    parser.add_argument("--wait-seconds", type=int, default=60, help="Seconds to wait before retrying a failed EID")
    parser.add_argument("--max-retries", type=int, default=2, help="Max retry attempts per EID before giving up")
    parser.add_argument(
        "--use-full-text-tool",
        action="store_true",
        help="Give paper_analyzer the full extracted PDF text instead of PDFSearchTool (RAG retrieval).",
    )
    args, _ = parser.parse_known_args(sys.argv[1:])

    if max_papers is None:
        max_papers = args.max_papers
    if check_paper_only is None:
        check_paper_only = args.check_paper_only
    if wait_seconds is None:
        wait_seconds = args.wait_seconds
    if max_retries is None:
        max_retries = args.max_retries
    if use_full_text_tool is None:
        use_full_text_tool = args.use_full_text_tool

    try:
        df = pd.read_csv(INPUTS_PATH, sep=';')
    except Exception as e:
        print(f"Error reading CSV: {e}")
        raise   

    if check_paper_only:
        df = df[df["EID"] == check_paper_only]

    for _, row in df.iterrows():

        # Check if a reproducibility report isn't already available
        if os.path.exists(OUTPUT_DIR / f"{row['EID']}{REPORT_TAIL_NAME}.json"):
            print(f"Reproducibility report already available for EID={row['EID']}")
            continue

        # Skip excluded papers entirely:
        if row["Filter_Decision"] == "EXCLUDE" or row["Human_Filter_Decision"] == "EXCLUDE" or row["Webpage_Access_Status"] == "NOT_ACCESSIBLE":
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
            "use_full_text_tool": use_full_text_tool,
        }

        print(f"--- Running ReproCheckFlow for EID={publication_id} ---")
        
        attempt = 0
        papers_processed = 0
        while True:
            try:
                repro_check_flow = ReproCheckFlow()
                repro_check_flow.kickoff(inputs=inputs)
                papers_processed += 1
                if max_papers is not None and papers_processed >= max_papers:
                    print(f"Processed {papers_processed} papers. Stopping.")
                    return
                break
            except Exception as e:
                attempt += 1
                print(f"Error processing EID={publication_id}: {e}")
                if max_retries is not None and attempt > max_retries:
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
    kickoff()