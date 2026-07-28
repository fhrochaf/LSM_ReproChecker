from crewai.flow import Flow, listen, start, router
import pandas as pd
import json

from flow_reproassesslsm_st1.crews.reprochecker_crew.reprochecker_crew import ReproCheckerCrew
from flow_reproassesslsm_st1.models import ReproCheckState, ReproducibilityReport, FilterOutput
from flow_reproassesslsm_st1.config import INPUTS_PATH, OUTPUT_DIR


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

        self._crew = ReproCheckerCrew(pdf_file=self.state.pdf_file)

    @listen(load_inputs)
    def filter_paper(self):
        print(f"Filtering paper (abstract-only): {self.state.pdf_file}")
        filter_result = self._crew.filter_crew().kickoff(
            inputs={"abstract": self.state.abstract}
        )

        self.state.filter_decision = filter_result.pydantic.decision
        self.state.filter_reason = filter_result.pydantic.reason

        df = pd.read_csv(INPUTS_PATH, sep=';')
        df.columns = df.columns.str.strip()

        mask = df["EID"].astype(str).str.strip() == str(self.state.publication_id).strip()
        if not mask.any():
            print(f"Warning: EID {self.state.publication_id} not found in {INPUTS_PATH}, decision not recorded.")
            return

        df.loc[mask, "Filter_Decision"] = self.state.filter_decision
        df.loc[mask, "Filter_Reason"] = self.state.filter_reason
        df.to_csv(INPUTS_PATH, sep=';', index=False)

        return filter_result.pydantic.decision  # passed into the router

    @router(filter_paper)
    def route_on_filter(self, decision):
        return "included" if decision == "INCLUDE" else "excluded"

    @listen("excluded")
    def write_exclusion(self):
        print(f"Paper excluded: {self.state.filter_reason}")
        self.state.final_report = FilterOutput(
            decision=self.state.filter_decision,
            reason=self.state.filter_reason,
        )

    @listen("included")
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
        df.loc[mask, "Webpage_Data_Links"] = ", ".join(avail.data_links) if avail.data_links else ""
        df.loc[mask, "Webpage_Code_Status"] = avail.code_status
        df.loc[mask, "Webpage_Code_Links"] = ", ".join(avail.code_links) if avail.code_links else ""
        df.loc[mask, "Webpage_Author_Statement"] = avail.author_statement or ""

        df.loc[mask, "Reproducibility_Assessment"] = report.reproducibility_assessment

        df.to_csv(INPUTS_PATH, sep=';', index=False)
     
    @listen(run_repro_check)
    def save_report(self):
        try:
            print("Saving report")
            output_file = OUTPUT_DIR / f"{self.state.publication_id}_repro_report.json"
            
            report = self.state.final_report.model_dump_json(indent=2)
            
            with open(output_file, "w") as f:
                f.write(report)
            print(f"Report saved to {output_file}")
        except Exception as e:
            print(f"Error saving report: {e}.\nFinal report:\n{self.state.final_report}")

def kickoff():
    
    try:
        df = pd.read_csv(INPUTS_PATH, sep=';')
    except Exception as e:
        print(f"Error reading CSV: {e}")
        raise
    
    ### TEMP CODE #######
    publication_id = "2-s2.0-85130393221"
    row = df.loc[df["EID"].astype(str).str.strip() == publication_id].squeeze()

    doi = str(row["DOI"]).strip()
    abstract = str(row["Abstract"]).strip()

    inputs = {
        "publication_id": publication_id,
        "pdf_file": f"{publication_id}.pdf",
        "doi": doi,
        "abstract": abstract,
    }

    print(f"--- Running ReproCheckFlow for EID={publication_id} ---")
    repro_check_flow = ReproCheckFlow()
    try:
        repro_check_flow.kickoff(inputs=inputs)
    except Exception as e:
        print(f"Error processing EID={publication_id}: {e}")
    ### TEMP CODE #######


    # for _, row in df.iterrows():
    #     eid = str(row["EID"]).strip()
    #     doi = str(row["DOI"]).strip()
    #     abstract = str(row["Abstract"]).strip()

    #     inputs = {
    #         "publication_id": eid,
    #         "pdf_file": f"{eid}.pdf",
    #         "doi": doi,
    #         "abstract": abstract,
    #     }

    #     print(f"--- Running ReproCheckFlow for EID={eid} ---")
    #     repro_check_flow = ReproCheckFlow()
    #     try:
    #         repro_check_flow.kickoff(inputs=inputs)
    #     except Exception as e:
    #         print(f"Error processing EID={eid}: {e}")


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