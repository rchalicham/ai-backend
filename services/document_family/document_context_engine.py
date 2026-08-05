from __future__ import annotations

from services.receipt_classification import ReceiptClassification
from services.receipt_dom import ReceiptDocument
from services.receipt_structure import ReceiptPhysicalStructure

from .address_candidate_engine import AddressCandidateEngine
from .diagnostics import DocumentFamilyDiagnostics
from .entity_resolution import EntityResolutionEngine
from .family_activation import DocumentFamilyActivationEngine
from .family_registry import DocumentFamilyRegistry
from .key_value_engine import KeyValueRelationshipEngine
from .key_value_validator import KeyValueRelationshipValidator
from .merchant_candidate_engine import MerchantCandidateEngine
from .models import DocumentFamilyContext
from .payment_candidate_engine import PaymentCandidateEngine
from .semantic_zones import SemanticZoneEngine


class DocumentContextEngine:
    def __init__(self, registry: DocumentFamilyRegistry | None = None) -> None:
        self.registry = registry or DocumentFamilyRegistry()
        self.activation = DocumentFamilyActivationEngine(self.registry)
        self.zones = SemanticZoneEngine()
        self.key_values = KeyValueRelationshipEngine()
        self.key_value_validator = KeyValueRelationshipValidator()
        self.merchants = MerchantCandidateEngine()
        self.payments = PaymentCandidateEngine()
        self.addresses = AddressCandidateEngine()
        self.entities = EntityResolutionEngine()

    def build(self, document: ReceiptDocument, structure: ReceiptPhysicalStructure,
              classification: ReceiptClassification | None, merchant_knowledge=None,
              grammar_context=None, enterprise_knowledge=None) -> DocumentFamilyContext:
        activation = self.activation.activate(document, structure, classification, merchant_knowledge, grammar_context, enterprise_knowledge)
        profile = self.registry.profile(activation.family)
        zones = self.zones.build(document, profile.expected_zones)
        relationships = self.key_value_validator.validate(self.key_values.reconstruct(document, zones, profile.key_value_labels))
        merchants = self.merchants.rank(document, zones, merchant_knowledge)
        payments = self.payments.resolve(document, zones, relationships)
        addresses = self.addresses.resolve(document, zones, merchant_knowledge)
        entities = self.entities.resolve(document, zones, relationships, merchants, payments, addresses)
        return DocumentFamilyContext(
            document_id=document.id, activation=activation, profile=profile,
            semantic_zones=zones, entity_candidates=entities,
            merchant_candidates=merchants, payment_candidates=payments,
            address_candidates=addresses, key_value_relationships=relationships,
            activated_grammar=profile.grammar_id,
            activated_constraints=profile.constraint_set_id,
            activated_rules=profile.entity_resolution_rules,
            diagnostics=DocumentFamilyDiagnostics.sidecar(),
        )

    def safe_build(self, document, structure, classification, **kwargs):
        if document is None or structure is None:
            return None
        try:
            return self.build(document, structure, classification, **kwargs)
        except Exception:
            return None
