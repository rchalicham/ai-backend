import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.receipt_grammar import (
    GrammarRoleType,
    ReceiptGrammarCompiler,
    payment_slip_grammar,
    retail_receipt_grammar,
)


def test_payment_slip_grammar_accepts_zero_item_structure_by_definition():
    grammar = payment_slip_grammar()
    compilation = ReceiptGrammarCompiler().compile(grammar)

    assert compilation.valid
    assert grammar.metadata.receipt_family == "payment-slip"
    assert all(section.section_id != "items" for section in grammar.sections)
    assert all(role.role_type is not GrammarRoleType.ITEM for role in grammar.roles)
    assert {item.expectation_id for item in grammar.expectations} == {
        "merchant", "date", "total", "payment-method", "approval-code", "card"
    }


def test_retail_receipt_grammar_still_requires_an_item_table():
    grammar = retail_receipt_grammar()
    compilation = ReceiptGrammarCompiler().compile(grammar)

    assert compilation.valid
    item_section = next(section for section in grammar.sections if section.section_id == "items")
    item_role = next(role for role in grammar.roles if role.role_type is GrammarRoleType.ITEM)
    assert item_section.required
    assert item_section.minimum_occurrences == 1
    assert item_role.required


def test_builtin_grammars_are_sidecar_definitions_and_do_not_expose_parser_operations():
    for grammar in (payment_slip_grammar(), retail_receipt_grammar()):
        assert not hasattr(grammar, "parse")
        assert not hasattr(grammar, "extract")
        assert grammar.metadata.source == "authored"
