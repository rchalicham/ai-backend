from __future__ import annotations

from .models import ContextEntity, DocumentReference


class DocumentLinker:
    def link(
        self,
        current_document: DocumentReference,
        entities: tuple[ContextEntity, ...],
    ) -> tuple[DocumentReference, ...]:
        related: dict[str, DocumentReference] = {}
        for entity in entities:
            references = entity.document_references
            if any(item.document_id == current_document.document_id for item in references):
                for reference in references:
                    if reference.document_id != current_document.document_id:
                        related[reference.document_id] = reference
        return tuple(related[key] for key in sorted(related))

