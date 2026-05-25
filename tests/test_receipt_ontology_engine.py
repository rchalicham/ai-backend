import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.receipt_intelligence import ReceiptIntelligencePipeline
from services.receipt_ontology_engine import RECEIPT_ONTOLOGY_ENTITY_TYPES, ReceiptOntologyEngine
from services.receipt_section_engine import ReceiptSectionExtractionEngine


def test_receipt_ontology_emits_generalized_entities_without_merchant_templates():
    raw_text = "\n".join([
        "GENERIC MARKET",
        "100 MAIN ST",
        "2026-05-24",
        "APPLES 2 @ 1.50 3.00",
        "SUBTOTAL 3.00",
        "TAX 0.24",
        "TOTAL 3.24",
        "VISA ************2222",
        "APPROVAL 123456",
        "THANK YOU",
    ])
    semantic = ReceiptIntelligencePipeline().to_structured_json(raw_text=raw_text, lines=raw_text.splitlines())
    ontology = semantic["documentOntology"]

    assert ontology["schemaVersion"] == "receipt-ontology-v1"
    assert ontology["governance"]["merchantSpecificRules"] is False
    assert ontology["governance"]["merchantSpecificTemplates"] is False
    assert set(RECEIPT_ONTOLOGY_ENTITY_TYPES).issubset(set(ontology["entityTypes"]))
    entity_types = {entity["type"] for entity in ontology["entities"]}
    assert {"MERCHANT", "PRODUCT", "QUANTITY", "MONEY", "TOTAL", "TAX", "PAYMENT", "LAST_FOUR", "APPROVAL_CODE", "FOOTER"}.issubset(entity_types)
    assert len(ontology["lineClassifications"]) == len(raw_text.splitlines())
    assert not any(line["text"] == "NO PURCHASE NECESSARY" and line["entityType"] == "PRODUCT" for line in ontology["lineClassifications"])
    assert ontology["debug"]["entityGraphVisualization"]["nodes"]
    assert ontology["debug"]["parserStateTrace"]
    assert ontology["debug"]["confidenceOverlays"]
    assert ontology["structuralIntelligence"]["constraints"]["totalsCannotContainProducts"] is True
    assert ontology["structuralIntelligence"]["constraints"]["paymentCannotContainProducts"] is True
    assert ontology["structuralIntelligence"]["confidence"] > 0.55
    assert ontology["selfLearning"]["strategy"] == "embedding_similarity_and_semantic_clustering"
    assert ontology["selfLearning"]["qdrantPayloads"]
    assert "ontology" in semantic["graph"]


def test_low_confidence_ontology_entities_remain_unresolved():
    sections = ReceiptSectionExtractionEngine().extract(lines=[
        "TOTAL 9.99",
        "THANK YOU",
    ])
    ontology = ReceiptOntologyEngine().build(
        lines=[],
        items=[],
        facts={"total": "9.99"},
        entity_result={"fields": {}},
        section_extraction=sections,
        merchant_resolution={"merchant": "Imaginary Merchant", "confidence": 0.2, "source": "llm_guess"},
    )

    merchant = next(entity for entity in ontology["entities"] if entity["type"] == "MERCHANT")
    assert merchant["status"] == "unresolved"
    assert merchant["value"] == ""
    assert merchant["unresolvedReason"] == "merchant_below_confidence_threshold"


def test_line_entity_classifier_rejects_financial_footer_rows_as_products():
    raw_text = "\n".join([
        "SHOP HEADER",
        "MILK 1 4.50",
        "BALANCE DUE 4.50",
        "USD 4.50",
        "VISA ************9876",
        "NO PURCHASE NECESSARY",
        "DUPLICATE MILK 4.50",
    ])
    semantic = ReceiptIntelligencePipeline().to_structured_json(raw_text=raw_text, lines=raw_text.splitlines())
    classifications = {line["text"]: line for line in semantic["documentOntology"]["lineClassifications"]}

    assert classifications["MILK 1 4.50"]["entityType"] == "PRODUCT"
    assert classifications["BALANCE DUE 4.50"]["entityType"] == "TOTAL"
    assert classifications["USD 4.50"]["entityType"] == "MONEY"
    assert classifications["VISA ************9876"]["entityType"] == "LAST_FOUR"
    assert classifications["NO PURCHASE NECESSARY"]["entityType"] == "FOOTER"
    assert classifications["DUPLICATE MILK 4.50"]["entityType"] != "PRODUCT"
    assert semantic["documentOntology"]["debug"]["rejectedEntityLogs"]
    assert semantic["documentOntology"]["structuralIntelligence"]["constraints"]["impossibleProductRowsRejected"] is True
