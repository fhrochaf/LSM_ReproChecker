import re
from pathlib import Path

from crewai import Agent, Crew, Process, Task, LLM
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import PDFSearchTool
from ...tools.custom_tool import publication_availability_tool, pdf_full_text_tool
from ...tools.guardrails import make_verbatim_guardrail
from ...models import FilterOutput, DataReproOutput, MethodReproOutput, AvailabilityOutput, ReproducibilityAssessment
from ...config import LSM_DOMAIN_INSTRUCTIONS, llm_local, llm_large, PDF_DIR, EMBEDDING_CONFIG_OPENAI

MAX_RPM = 5 # Maximum requests per minute

@CrewBase
class ReproCheckerCrew:
    """ReproChecker Crew"""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, pdf_file: str, use_full_text_tool: bool = False):
        self.pdf_file = pdf_file
        # Switch for paper_analyzer's PDF tool: False = PDFSearchTool (RAG
        # retrieval over chunks), True = PDFFullTextTool (whole document
        # text handed to the agent). Read as instance state rather than a
        # paper_analyzer() argument because crewai's @crew decorator
        # auto-instantiates every @agent method with no arguments before
        # running the crew body, so a non-default argument there would
        # cause paper_analyzer to be built twice (once per tool).
        self.use_full_text_tool = use_full_text_tool

    def _pdf_collection_name(self) -> str:
        """Derive a Chroma-safe collection name unique to this PDF.

        Each paper needs its own collection: PDFSearchTool otherwise
        defaults to a single shared collection, so paper analyzed later
        in a batch run would retrieve chunks from earlier papers too.
        """
        stem = Path(self.pdf_file).stem
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", stem).strip("_-") or "pdf"
        name = f"pdf_{safe}"
        return name[:63].rstrip("_-") or "pdf_doc"

    @agent
    def abstract_screener(self) -> Agent:
        return Agent(
            config=self.agents_config["abstract_screener"],  # type: ignore[index]
            max_rpm=MAX_RPM,
            llm=llm_local
        )

    @agent
    def paper_analyzer(self) -> Agent:

        if self.use_full_text_tool:
            pdf_tool = pdf_full_text_tool(pdf_path=str(PDF_DIR / self.pdf_file))
        else:
            pdf_tool = PDFSearchTool(
                pdf=str(PDF_DIR / self.pdf_file),
                config=EMBEDDING_CONFIG_OPENAI,
                collection_name=self._pdf_collection_name(),
            )

        return Agent(
            config=self.agents_config["paper_analyzer"],
            max_rpm=MAX_RPM,
            skills=[str(LSM_DOMAIN_INSTRUCTIONS)],
            tools=[pdf_tool],
            llm=llm_large
        )

    @agent
    def availability_web_scraper(self) -> Agent:
        return Agent(
            config=self.agents_config["availability_web_scraper"],  # type: ignore[index]
            max_rpm=MAX_RPM,
            tools=[publication_availability_tool()],
            llm=llm_large
        )

    @agent
    def report_elaborator(self) -> Agent:
        return Agent(
            config=self.agents_config["report_elaborator"],  # type: ignore[index]
            max_rpm=MAX_RPM,
            llm=llm_large
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
            output_pydantic=DataReproOutput,
            guardrail=make_verbatim_guardrail(str(PDF_DIR / self.pdf_file), DataReproOutput),
        )

    @task
    def check_method_reproducibility(self) -> Task:
        return Task(
            config=self.tasks_config["check_method_reproducibility"],
            output_pydantic=MethodReproOutput,
            guardrail=make_verbatim_guardrail(str(PDF_DIR / self.pdf_file), MethodReproOutput),
        )

    @task
    def check_artifact_availability(self) -> Task:
        return Task(
            config=self.tasks_config["check_artifact_availability"],
            async_execution=True,
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

    @task
    def compile_final_report_from_availability(self) -> Task:
        """Same as compile_final_report, but sources artifact availability from
        pre-filled CSV fields (via the `availability_summary` input) instead of
        from a check_artifact_availability task run.
        """
        return Task(
            config=self.tasks_config["compile_final_report_from_availability"],
            context=[
                self.check_data_reproducibility(),
                self.check_method_reproducibility(),
            ],
            output_pydantic=ReproducibilityAssessment,
        )

    @crew
    def filter_crew(self) -> Crew:
        """Crew that only decides whether the paper qualifies, using the abstract only."""
        return Crew(
            agents=[self.abstract_screener()],
            tasks=[self.filter_landslide_mapping_paper()],
            max_rpm=MAX_RPM,
            process=Process.sequential,
            verbose=True,
        )

    @crew
    def repro_crew_from_csv(self) -> Crew:
        """Crew that runs the data and method reproducibility checks, then
        compiles the report using artifact availability info already
        pre-filled in the inputs CSV (Webpage_* columns), skipping
        check_artifact_availability entirely.
        """
        return Crew(
            agents=[self.paper_analyzer(), self.report_elaborator()],
            tasks=[
                self.check_data_reproducibility(),
                self.check_method_reproducibility(),
                self.compile_final_report_from_availability(),
            ],
            max_rpm=MAX_RPM,
            process=Process.sequential,
            verbose=True,
        )

    @crew
    def repro_crew(self) -> Crew:
        """Crew that runs the three reproducibility checks, then compiles the report.

        Only meant to be kicked off after filter_crew has run and returned INCLUDE.
        """
        return Crew(
            agents=[self.paper_analyzer(), self.availability_web_scraper(), self.report_elaborator()],
            tasks=[
                self.check_data_reproducibility(),
                self.check_method_reproducibility(),
                self.check_artifact_availability(),
                self.compile_final_report(),
            ],
            max_rpm=MAX_RPM,
            process=Process.sequential,
            verbose=True,
        )



