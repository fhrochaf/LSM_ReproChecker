from pydantic import BaseModel, Field
from typing import Literal

class FilterOutput(BaseModel):
    decision: Literal["INCLUDE", "EXCLUDE"]
    reason: str = Field(description="two sentences stating why the publication is included or excluded from the reproducibility assessment")

class DatasetEntry(BaseModel):
    name: str = Field(description="Short dataset name or type, around 20 words")
    source: str | None = Field(default=None, description="Provider or organization name")
    link: str | None = Field(default=None, description="A single URL")
    status: Literal["MENTIONED", "NOT_MENTIONED"]
    verbatim: str | None = Field(default=None, description="Exact excerpt from the text where the source/link was found")

class MethodEntry(BaseModel):
    name: str = Field(description="Short name/label for the method, around 10-20 words")
    method_type: Literal["MANUAL", "SOFTWARE", "CUSTOM_CODE", "REUSED"]
    summary: str | None = Field(default=None, description="Summary of the method's architecture and components, a few sentences. Left null for web-scraped code-artifact entries (e.g. AvailabilityOutput.code_links), which aren't expected to restate it.")
    source: str | None = Field(default=None, description="Origin named for the method: citation if REUSED, provider/vendor if SOFTWARE or CUSTOM_CODE")
    link: str | None = Field(default=None, description="A single retrieval URL for the method's implementation, preferred over source when available")
    status: Literal["MENTIONED", "NOT_MENTIONED"]
    verbatim: str | None = Field(default=None, description="Exact excerpt from the text where the source/link was found")

class PaperAnalysisOutput(BaseModel):
    datasets: list[DatasetEntry] = Field(
        description=(
            "A JSON array of dataset objects."
            "Must be an actual array (e.g. [{...}, {...}]), never a JSON string containing an array."
        )
    )
    methods: list[MethodEntry] = Field(
        description=(
            "A JSON array holding the paper's own novel landslide mapping/detection method "
            "(normally a single entry)."
            "Must be an actual array (e.g. [{...}]), never a JSON string containing an array."
        )
    )

class AvailabilityOutput(BaseModel):
    access_status: Literal["ACCESSIBLE", "NOT_ACCESSIBLE"]
    data_status: Literal["MENTIONED", "NOT_MENTIONED"]
    data_links: list[DatasetEntry]
    code_status: Literal["MENTIONED", "NOT_MENTIONED"]
    code_links: list[MethodEntry]
    author_statement: str | None

class DatasetAvailabilityEntry(BaseModel):
    name: str = Field(description="The dataset's name, as given to the researcher")
    summary: str = Field(description="One-sentence description of what the dataset is and who produces/maintains it")
    availability: Literal["PUBLIC_FREE", "PUBLIC_REG", "COMMERCIAL", "RESTRICTED", "VARIES"]
    availability_notes: str = Field(description="The specific provider(s)/portal(s) through which the dataset can be obtained")
    source_url: str | None = Field(default=None, description="A URL supporting this availability judgment, or null if none found")

class DatasetAvailabilityResearchOutput(BaseModel):
    entries: list[DatasetAvailabilityEntry] = Field(
        description=(
            "A JSON array with one entry per researched dataset."
            "Must be an actual array (e.g. [{...}, {...}]), never a JSON string containing an array."
        )
    )

class ReproducibilityAssessment(BaseModel):
    reproducibility_status: Literal["REPRODUCIBLE", "PARTIALLY_REPRODUCIBLE", "NOT_REPRODUCIBLE"]
    reproducibility_assessment: str  # one or two sentences, max ~100 words

class ReproducibilityReport(BaseModel):
    datasets: list[DatasetEntry]
    methods: list[MethodEntry]
    availability: AvailabilityOutput
    reproducibility_status: Literal["REPRODUCIBLE", "PARTIALLY_REPRODUCIBLE", "NOT_REPRODUCIBLE"]
    reproducibility_assessment: str  # one or two sentences, max ~100 words

class ReproCheckState(BaseModel):
    publication_id: str = ""
    pdf_file: str = ""
    doi: str = ""
    abstract: str = ""
    use_full_text_tool: bool = False
    with_human_intervention: bool = False
    guardrail_max_retries: int = 3
    multi_run_count: int = 3
    filter_decision: str = ""
    filter_reason: str = ""
    prefilled_availability: object = None
    final_report: object = None
