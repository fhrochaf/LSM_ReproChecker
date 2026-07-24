from pathlib import Path

from pydantic import BaseModel

from crewai.flow import Flow, listen, start, router

from flow_reproassesslsm_st1.crews.reprochecker_crew.reprochecker_crew import ReproCheckerCrew
from flow_reproassesslsm_st1.models import ReproCheckState, ReproducibilityReport, FilterOutput

INPUTS_PATH = Path("publications") / "inputs.json"
OUTPUT_DIR = Path("output")

class ReproCheckFlow(Flow[ReproCheckState]):

    @start()
    def load_inputs(self, crewai_trigger_payload: dict = None):
        print("Loading inputs")

        if crewai_trigger_payload:
            self.state.publication_id = crewai_trigger_payload.get("publication_id", 0)
            self.state.pdf_path = crewai_trigger_payload.get("pdf_path", "")
            self.state.doi = crewai_trigger_payload.get("doi", "")
            print(f"Using trigger payload: {crewai_trigger_payload}")

        if not self.state.pdf_path or not self.state.doi:
            raise ValueError("Both 'pdf_path' and 'doi' must be provided.")

        print(f"PDF path: {self.state.pdf_path}")
        print(f"DOI: {self.state.doi}")

        self._crew = ReproCheckerCrew(pdf_path=self.state.pdf_path)

    @listen(load_inputs)
    def filter_paper(self):
        print(f"Filtering paper: {self.state.pdf_path}")
        filter_result = self._crew.filter_crew().kickoff()

        self.state.filter_decision = filter_result.pydantic.decision
        self.state.filter_reason = filter_result.pydantic.reason

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
        print(f"Paper included, running reproducibility checks on: {self.state.pdf_path}")
        inputs = {"doi_url": f"https://doi.org/{self.state.doi}"}
        result = self._crew.repro_crew().kickoff(inputs=inputs)

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


    @listen(run_repro_check)
    def save_report(self):
        try:
            print("Saving report")
            OUTPUT_DIR.mkdir(exist_ok=True)
            output_file = OUTPUT_DIR / f"{self.state.publication_id}_repro_report.json"
            with open(output_file, "w") as f:
                f.write(self.state.final_report.model_dump_json(indent=2))
            print(f"Report saved to {output_file}")
        except Exception as e:
            print(f"Error saving report: {e}.\nFinal report:\n{self.state.final_report}")


import json

def kickoff():
    try:
        with open(INPUTS_PATH) as f:
            inputs = json.load(f)
    except FileNotFoundError:
        raise Exception(f"Input file {INPUTS_PATH} not found. Please provide inputs.json with 'pdf_path' and 'doi'.")

    repro_check_flow = ReproCheckFlow()
    repro_check_flow.kickoff(inputs=inputs)


def plot():
    repro_check_flow = ReproCheckFlow()
    repro_check_flow.plot()


def run_with_trigger():
    """
    Run the flow with trigger payload.
    """
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