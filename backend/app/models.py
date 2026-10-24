"""Pydantic models: the shape of request bodies the API accepts."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

Tag = Literal["methodology", "limitation", "result", "dataset", "definition", "quote", "future_work"]
Status = Literal["to_read", "reading", "done"]
Role = Literal["viewer", "editor"]
Difficulty = Literal["beginner", "intermediate", "advanced"]
HexColor = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


# ---- auth ----
class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=6, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


# ---- papers ----
class PaperIn(BaseModel):
    title: str = Field(min_length=1)
    authors: str | None = None
    year: int | None = Field(default=None, ge=1500, le=2100)
    venue: str | None = None
    doi: str | None = None
    abstract: str | None = None
    pdf_url: str | None = None


class PaperPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    authors: str | None = None
    year: int | None = Field(default=None, ge=1500, le=2100)
    venue: str | None = None
    doi: str | None = None
    abstract: str | None = None
    pdf_url: str | None = None


class ImportIn(BaseModel):
    identifier: str = Field(min_length=3, description="A DOI, doi.org link, arXiv ID or arXiv link")


class ReadingStateIn(BaseModel):
    status: Status | None = None
    current_page: int | None = Field(default=None, ge=1)


class AttributeIn(BaseModel):
    attr_name: str = Field(min_length=1, max_length=60)
    attr_value: str = Field(min_length=1)


class PaperConceptIn(BaseModel):
    concept_id: UUID
    relation: Literal["introduces", "assumes"]


class CitationIn(BaseModel):
    cited_paper_id: UUID


# ---- highlights / notes / comments ----
class Rect(BaseModel):
    x: float
    y: float
    w: float
    h: float


class Position(BaseModel):
    rects: list[Rect]


class HighlightIn(BaseModel):
    quote: str = Field(min_length=1)
    tag: Tag | None = None
    color: str | None = HexColor
    page: int | None = Field(default=None, ge=1)
    position: Position | None = None


class HighlightPatch(BaseModel):
    tag: Tag | None = None
    color: str | None = HexColor


class NoteIn(BaseModel):
    content: str = Field(min_length=1)


class CommentIn(BaseModel):
    body: str = Field(min_length=1)
    parent_id: UUID | None = None


# ---- collections ----
class CollectionIn(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None


class MemberIn(BaseModel):
    email: EmailStr
    role: Role


# ---- concepts ----
class ConceptIn(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    difficulty: Difficulty | None = None


class PrerequisiteIn(BaseModel):
    prerequisite_id: UUID


# ---- reading / AI ----
class SessionIn(BaseModel):
    page: int | None = Field(default=None, ge=1)


class AskIn(BaseModel):
    question: str = Field(min_length=3)
