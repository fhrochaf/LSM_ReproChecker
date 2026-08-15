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

class DataReproOutput(BaseModel):
    datasets: list[DatasetEntry] = Field(
        description=(
            "A JSON array of dataset objects."
            "Must be an actual array (e.g. [{...}, {...}]), never a JSON string containing an array."
        )
    )

class MethodEntry(BaseModel):
    name: str = Field(description="Short name/label for the method, around 10-20 words")
    method_type: Literal["MANUAL", "SOFTWARE", "CUSTOM_CODE", "REUSED"]
    summary: str  # one or two sentences, not a paragraph
    code_status: Literal["MENTIONED", "NOT_MENTIONED"]
    code_link: str | None
    reused_citation: str | None

class MethodReproOutput(BaseModel):
    methods: list[MethodEntry] = Field(
        description=(
            "A JSON array of method objects, one per distinct mapping method."
            "Must be an actual array (e.g. [{...}, {...}]), never a JSON string containing an array."
        )
    )

class AvailabilityOutput(BaseModel):
    access_status: Literal["ACCESSIBLE", "NOT_ACCESSIBLE"]
    data_status: Literal["MENTIONED", "NOT_MENTIONED"]
    data_links: list[DatasetEntry]
    code_status: Literal["MENTIONED", "NOT_MENTIONED"]
    code_links: list[MethodEntry]
    author_statement: str | None

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
    filter_decision: str = ""
    filter_reason: str = ""
    prefilled_availability: object = None
    final_report: object = None
