import re
from pathlib import Path

from crewai import Agent, Crew, Process, Task, LLM
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import PDFSearchTool, TavilySearchTool
from pydantic import BaseModel
from ...tools.custom_tool import publication_availability_tool, pdf_full_text_tool
from ...tools.guardrails import make_verbatim_guardrail
from ...models import (
    FilterOutput,
    PaperAnalysisOutput,
    AvailabilityOutput,
    DatasetAvailabilityResearchOutput,
    ReproducibilityAssessment,
)
from ...config import LSM_DOMAIN_INSTRUCTIONS, llm_local, llm_large, PDF_DIR, EMBEDDING_CONFIG_OPENAI

MAX_RPM = 5 # Maximum requests per minute

@CrewBase
class ReproCheckerCrew:
    """ReproChecker Crew"""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(
        self,
        pdf_file: str,
        use_full_text_tool: bool = False,
        with_human_intervention: bool = False,
        guardrail_max_retries: int = 3,
        multi_run_count: int = 1,
    ):
        self.pdf_file = pdf_file
        # Switch for paper_analyzer's PDF tool: False = PDFSearchTool (RAG
        # retrieval over chunks), True = PDFFullTextTool (whole document
        # text handed to the agent). Read as instance state rather than a
        # paper_analyzer() argument because crewai's @crew decorator
        # auto-instantiates every @agent method with no arguments before
        # running the crew body, so a non-default argument there would
        # cause paper_analyzer to be built twice (once per tool).
        self.use_full_text_tool = use_full_text_tool
        # When True, every Task pauses in the terminal after the agent
        # produces its answer (crewai's native Task(human_input=True) loop),
        # so a reviewer can send it back for another pass before the crew
        # moves on.
        self.with_human_intervention = with_human_intervention
        # Populated by repro_crew_multi_check()/repro_crew_multi_check_from_csv();
        # read by the Flow afterwards to pull all MULTI_RUN_COUNT outputs for
        # merge_entries().
        self.guardrail_max_retries = guardrail_max_retries
        # Overrides the module-level MULTI_RUN_COUNT default for this crew's
        # _repeat_task() calls. Note utils.merge_entries defaults to
        # min_votes=2, so a multi_run_count of 1 means no cluster can ever
        # reach quorum and every dataset/method gets dropped.
        self.multi_run_count = multi_run_count
        self._analysis_runs: list[Task] = []

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
    def dataset_availability_researcher(self) -> Agent:
        return Agent(
            config=self.agents_config["dataset_availability_researcher"],  # type: ignore[index]
            max_rpm=MAX_RPM,
            tools=[TavilySearchTool()],
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
            human_input=self.with_human_intervention,
        )

    @task
    def check_artifact_availability(self) -> Task:
        return Task(
            config=self.tasks_config["check_artifact_availability"],
            # human_input blocks on terminal input, which can't safely
            # overlap with an async task running concurrently with the
            # rest of the crew — run it synchronously while a reviewer is
            # attached.
            async_execution=not self.with_human_intervention,
            output_pydantic=AvailabilityOutput,
            human_input=self.with_human_intervention,
        )

    @task
    def research_dataset_availability(self) -> Task:
        return Task(
            config=self.tasks_config["research_dataset_availability"],
            output_pydantic=DatasetAvailabilityResearchOutput,
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
                guardrail_max_retries=self.guardrail_max_retries,
                human_input=self.with_human_intervention,
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
            human_input=self.with_human_intervention,
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
        """Runs analyze_paper self.multi_run_count times, skipping the
        artifact-availability agent/task entirely — availability is already
        known from the CSV prefill (see availability_summary).
        """
        self._analysis_runs = self._repeat_task("analyze_paper", PaperAnalysisOutput, self.multi_run_count)
        return Crew(
            agents=[self.paper_analyzer()],
            tasks=[*self._analysis_runs],
            max_rpm=MAX_RPM,
            process=Process.sequential,
            verbose=True,
        )

    @crew
    def repro_crew_multi_check(self) -> Crew:
        """Runs analyze_paper self.multi_run_count times (plus a single
        artifact availability check), storing the per-run tasks on
        self._analysis_runs. The Flow pulls all N outputs from those and
        reconciles them via utils.merge_entries, then kicks off
        consolidated_report_crew separately — this crew does not compile a
        final report itself.
        """
        self._analysis_runs = self._repeat_task("analyze_paper", PaperAnalysisOutput, self.multi_run_count)
        return Crew(
            agents=[self.paper_analyzer(), self.availability_web_scraper()],
            tasks=[*self._analysis_runs, self.check_artifact_availability()],
            max_rpm=MAX_RPM,
            process=Process.sequential,
            verbose=True,
        )

    @crew
    def dataset_research_crew(self) -> Crew:
        """Runs only when the Flow finds datasets not yet covered by
        skills/dataset_availability_reference.json (see
        utils.missing_dataset_names). Takes a `missing_datasets` input and
        produces DatasetAvailabilityResearchOutput entries, which the Flow
        appends to that file before (re-)running consolidated_report_crew."""
        return Crew(
            agents=[self.dataset_availability_researcher()],
            tasks=[self.research_dataset_availability()],
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