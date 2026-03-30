from typing import Literal

from pydantic import BaseModel, Field


class IndexRequest(BaseModel):
    document_id: str
    entity_id: str
    file_url: str | None = None
    text: str
    metadata: dict = Field(default_factory=dict)


class CreateRelationshipRequest(BaseModel):
    from_id: str
    from_type: Literal["Entity", "Document"]
    to_id: str
    to_type: Literal["Entity", "Document"]
    relationship_type: Literal["HAS_DOCUMENT", "BELONGS_TO", "OWNS", "USED_IN_EVENT"]


class AskRequest(BaseModel):
    question: str
    entity_id: str
    top_k: int = 5


class TemplateSuggestRequest(BaseModel):
    template_name: str
    description: str | None = None
    domain_id: str | None = None
    domain_type: str | None = None
