from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import PDFSearchTool
from ...tools.custom_tool import publication_availability_tool
from ...models import FilterOutput, DataReproOutput, MethodReproOutput, AvailabilityOutput, ReproducibilityAssessment
from pathlib import Path

LSM_DOMAIN_INSTRUCTIONS = str(Path(__file__).resolve().parent / "skills" / "lsm_domain_instructions")

@CrewBase
class ReproCheckerCrew:
    """ReproChecker Crew"""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path

    @agent
    def paper_analyzer(self) -> Agent:
        return Agent(
            config=self.agents_config["paper_analyzer"],
            skills=[LSM_DOMAIN_INSTRUCTIONS],
            tools=[PDFSearchTool(pdf=self.pdf_path)],
        )

    @agent
    def availability_web_scraper(self) -> Agent:
        return Agent(
            config=self.agents_config["availability_web_scraper"],  # type: ignore[index]
            tools=[publication_availability_tool()],
        )

    @agent
    def report_elaborator(self) -> Agent:
        return Agent(
            config=self.agents_config["report_elaborator"],  # type: ignore[index]
        )

    @task
    def filter_landslide_mapping_paper(self) -> Task:
        return Task(
            config=self.tasks_config["filter_landslide_mapping_paper"],  # type: ignore[index]
            output_pydantic=FilterOutput,
        )

    @task
    def check_data_reproducibility(self) -> Task:
        return Task(
            config=self.tasks_config["check_data_reproducibility"],
            context=[self.filter_landslide_mapping_paper()],
            output_pydantic=DataReproOutput,
        )

    @task
    def check_method_reproducibility(self) -> Task:
        return Task(
            config=self.tasks_config["check_method_reproducibility"],
            context=[self.filter_landslide_mapping_paper()],
            output_pydantic=MethodReproOutput,
        )

    @task
    def check_artifact_availability(self) -> Task:
        return Task(
            config=self.tasks_config["check_artifact_availability"],
            async_execution=True,
            context=[self.filter_landslide_mapping_paper()],
            output_pydantic=AvailabilityOutput,
        )

    @task
    def compile_final_report(self) -> Task:
        return Task(
            config=self.tasks_config["compile_final_report"],  # type: ignore[index]
            context=[
                self.check_data_reproducibility(),
                self.check_method_reproducibility(),
                self.check_artifact_availability(),
            ],
            output_pydantic=ReproducibilityAssessment,
        )

    @crew
    def filter_crew(self) -> Crew:
        """Crew that only decides whether the paper qualifies for assessment."""
        return Crew(
            agents=[self.paper_analyzer()],
            tasks=[self.filter_landslide_mapping_paper()],
            process=Process.sequential,
            verbose=True,
        )

    @crew
    def repro_crew(self) -> Crew:
        """Crew that runs the three reproducibility checks in parallel, then compiles the report.

        Only meant to be kicked off after filter_crew has run and returned INCLUDE.
        """
        return Crew(
            agents=self.agents,
            tasks=[
                self.check_data_reproducibility(),
                self.check_method_reproducibility(),
                self.check_artifact_availability(),
                self.compile_final_report(),
            ],
            process=Process.sequential,
            verbose=True,
        )


if __name__ == "__main__":
    crew = ReproCheckerCrew(pdf_path="")
    crew.filter_crew().kickoff()