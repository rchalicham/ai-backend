import base64
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.donut_receipt_service import DonutReceiptService


def test_donut_service_decodes_plain_and_data_url_base64():
    service = DonutReceiptService()
    payload = base64.b64encode(b"image-bytes").decode("ascii")

    assert service.decode_base64_image(payload) == b"image-bytes"
    assert service.decode_base64_image(f"data:image/jpeg;base64,{payload}") == b"image-bytes"


def test_donut_service_normalizes_cord_receipt_json():
    service = DonutReceiptService()

    normalized = service._normalize_cord_json({
        "store_name": "LOWE'S",
        "date": "05/18/2026",
        "menu": [
            {"nm": "MULCH BAG", "cnt": "2", "price": "7.00"},
            {"nm": "WASHERS", "cnt": "3", "price": "3.75"},
        ],
        "sub_total": {
            "subtotal_price": "10.75",
            "tax_price": "0.86",
        },
        "total": {
            "total_price": "11.61",
        },
    })

    assert normalized["merchant"] == "LOWE'S"
    assert normalized["date"] == "05/18/2026"
    assert [(item["name"], item["qty"], item["amount"]) for item in normalized["items"]] == [
        ("MULCH BAG", "2", "7.00"),
        ("WASHERS", "3", "3.75"),
    ]
    assert normalized["subtotal"] == "10.75"
    assert normalized["tax"] == "0.86"
    assert normalized["total"] == "11.61"
