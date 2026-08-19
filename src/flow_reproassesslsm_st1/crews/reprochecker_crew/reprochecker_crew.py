import re
from pathlib import Path

from crewai import Agent, Crew, Process, Task, LLM
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import PDFSearchTool
from pydantic import BaseModel
from ...tools.custom_tool import publication_availability_tool, pdf_full_text_tool
from ...tools.guardrails import make_verbatim_guardrail
from ...models import FilterOutput, DataReproOutput, MethodReproOutput, AvailabilityOutput, ReproducibilityAssessment
from ...config import LSM_DOMAIN_INSTRUCTIONS, llm_local, llm_large, PDF_DIR, EMBEDDING_CONFIG_OPENAI

MAX_RPM = 5 # Maximum requests per minute
MULTI_RUN_COUNT = 3 # independent runs to reconcile via majority vote, see utils.merge_entries

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
        # Populated by repro_crew_multi_check()/repro_crew_multi_check_from_csv();
        # read by the Flow afterwards to pull all MULTI_RUN_COUNT outputs for
        # merge_entries().
        self._data_runs: list[Task] = []
        self._method_runs: list[Task] = []

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
    def check_artifact_availability(self) -> Task:
        return Task(
            config=self.tasks_config["check_artifact_availability"],
            async_execution=True,
            output_pydantic=AvailabilityOutput,
        )

    def _repeat_task(self, task_name: str, output_model: type[BaseModel], n: int) -> list[Task]:
        """Build n independent Task instances from the same tasks.yaml config.

        @task-decorated methods are memoized (crewai.project.memoize), so
        calling a decorated task method repeatedly returns the same cached
        Task. Multi-run consolidation needs n distinct executions, so these
        are built directly from the tasks.yaml config instead of going
        through a decorated method.

        """
        return [
            Task(
                config=self.tasks_config[task_name],
                output_pydantic=output_model,
                guardrail=make_verbatim_guardrail(str(PDF_DIR / self.pdf_file), output_model),
            )
            for _ in range(n)
        ]

    @task
    def compile_final_report_from_consolidated(self) -> Task:
        """Compiles the final report from Python-merged (multi-run) dataset/
        method findings (see utils.merge_entries) plus an availability_summary
        input. The Flow always has an AvailabilityOutput by this point —
        either from a live check_artifact_availability run or from the CSV
        prefill — and serializes whichever one to availability_summary, so
        this single task covers both paths.
        """
        return Task(
            config=self.tasks_config["compile_final_report_from_consolidated"],
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
    def repro_crew_multi_check_from_csv(self) -> Crew:
        """Runs check_data_reproducibility and check_method_reproducibility
        MULTI_RUN_COUNT times each, skipping the artifact-availability
        agent/task entirely — availability is already known from the CSV
        prefill (see availability_summary).
        """
        self._data_runs = self._repeat_task("check_data_reproducibility", DataReproOutput, MULTI_RUN_COUNT)
        self._method_runs = self._repeat_task("check_method_reproducibility", MethodReproOutput, MULTI_RUN_COUNT)
        return Crew(
            agents=[self.paper_analyzer()],
            tasks=[*self._data_runs, *self._method_runs],
            max_rpm=MAX_RPM,
            process=Process.sequential,
            verbose=True,
        )

    @crew
    def repro_crew_multi_check(self) -> Crew:
        """Runs check_data_reproducibility and check_method_reproducibility
        MULTI_RUN_COUNT times each (plus a single artifact availability
        check), storing the per-run tasks on self._data_runs/
        self._method_runs. The Flow pulls all N outputs from those and
        reconciles them via utils.merge_entries, then kicks off
        consolidated_report_crew separately — this crew does not compile a
        final report itself.
        """
        self._data_runs = self._repeat_task("check_data_reproducibility", DataReproOutput, MULTI_RUN_COUNT)
        self._method_runs = self._repeat_task("check_method_reproducibility", MethodReproOutput, MULTI_RUN_COUNT)
        return Crew(
            agents=[self.paper_analyzer(), self.availability_web_scraper()],
            tasks=[*self._data_runs, *self._method_runs, self.check_artifact_availability()],
            max_rpm=MAX_RPM,
            process=Process.sequential,
            verbose=True,
        )

    @crew
    def consolidated_report_crew(self) -> Crew:
        """Second-stage crew, shared by both the live-scrape and
        prefilled-availability paths: compiles the final report from the
        Flow's merged dataset/method findings plus an availability_summary
        input (see compile_final_report_from_consolidated)."""
        return Crew(
            agents=[self.report_elaborator()],
            tasks=[self.compile_final_report_from_consolidated()],
            max_rpm=MAX_RPM,
            process=Process.sequential,
            verbose=True,
        )
