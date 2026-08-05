from __future__ import annotations

from dataclasses import replace
from threading import RLock
from typing import Protocol, runtime_checkable

from .models import ReceiptIntelligenceSnapshot


@runtime_checkable
class SnapshotRepositoryProtocol(Protocol):
    def save(self, snapshot: ReceiptIntelligenceSnapshot) -> ReceiptIntelligenceSnapshot: ...
    def latest(self, receipt_id: str) -> ReceiptIntelligenceSnapshot | None: ...
    def get(self, snapshot_id: str) -> ReceiptIntelligenceSnapshot | None: ...
    def history(self, receipt_id: str) -> tuple[ReceiptIntelligenceSnapshot, ...]: ...
    def archive(self, snapshot_id: str) -> ReceiptIntelligenceSnapshot: ...
    def delete(self, snapshot_id: str) -> bool: ...


class InMemorySnapshotRepository:
    """Thread-safe immutable append-only repository; useful for tests and local runs."""

    def __init__(self) -> None:
        self._by_receipt: dict[str, list[ReceiptIntelligenceSnapshot]] = {}
        self._by_id: dict[str, ReceiptIntelligenceSnapshot] = {}
        self._lock = RLock()

    def save(self, snapshot: ReceiptIntelligenceSnapshot) -> ReceiptIntelligenceSnapshot:
        with self._lock:
            if snapshot.header.snapshot_id in self._by_id:
                raise ValueError("snapshot_is_immutable")
            history = self._by_receipt.setdefault(snapshot.header.receipt_id, [])
            if any(item.header.version.number == snapshot.header.version.number for item in history):
                raise ValueError("snapshot_version_already_exists")
            history.append(snapshot)
            history.sort(key=lambda item: item.header.version.number)
            self._by_id[snapshot.header.snapshot_id] = snapshot
            return snapshot

    def latest(self, receipt_id: str) -> ReceiptIntelligenceSnapshot | None:
        values = [item for item in self.history(receipt_id) if item.header.version.status == "active"]
        return values[-1] if values else None

    def get(self, snapshot_id: str) -> ReceiptIntelligenceSnapshot | None:
        return self._by_id.get(snapshot_id)

    def history(self, receipt_id: str) -> tuple[ReceiptIntelligenceSnapshot, ...]:
        return tuple(self._by_receipt.get(receipt_id, ()))

    def archive(self, snapshot_id: str) -> ReceiptIntelligenceSnapshot:
        with self._lock:
            current = self._by_id.get(snapshot_id)
            if current is None:
                raise KeyError("snapshot_not_found")
            archived = replace(current, header=replace(
                current.header,
                version=replace(current.header.version, status="archived"),
            ), summary=replace(current.summary, status="archived"))
            self._replace(current, archived)
            return archived

    def delete(self, snapshot_id: str) -> bool:
        with self._lock:
            current = self._by_id.pop(snapshot_id, None)
            if current is None:
                return False
            self._by_receipt[current.header.receipt_id] = [
                item for item in self._by_receipt[current.header.receipt_id]
                if item.header.snapshot_id != snapshot_id
            ]
            return True

    def _replace(self, current: ReceiptIntelligenceSnapshot, updated: ReceiptIntelligenceSnapshot) -> None:
        values = self._by_receipt[current.header.receipt_id]
        values[values.index(current)] = updated
        self._by_id[current.header.snapshot_id] = updated


class MongoSnapshotRepository:
    """Mongo persistence adapter. Documents are append-only; archive is a status transition."""

    def __init__(self, collection, serializer, loader) -> None:
        self.collection = collection
        self.serializer = serializer
        self.loader = loader
        self.collection.create_index([("header.receipt_id", 1), ("header.version.number", -1)], unique=True)
        self.collection.create_index("header.snapshot_id", unique=True)

    @classmethod
    def from_uri(cls, uri: str, database: str = "receipt_intelligence", collection: str = "snapshots"):
        from pymongo import MongoClient
        from .snapshot_loader import SnapshotLoader
        from .snapshot_serializer import SnapshotSerializer
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        return cls(client[database][collection], SnapshotSerializer(), SnapshotLoader())

    def save(self, snapshot):
        self.collection.insert_one(self.serializer.to_dict(snapshot))
        return snapshot

    def latest(self, receipt_id):
        value = self.collection.find_one({"header.receipt_id": receipt_id, "header.version.status": "active"}, sort=[("header.version.number", -1)])
        return self.loader.from_dict(value) if value else None

    def get(self, snapshot_id):
        value = self.collection.find_one({"header.snapshot_id": snapshot_id})
        return self.loader.from_dict(value) if value else None

    def history(self, receipt_id):
        return tuple(self.loader.from_dict(item) for item in self.collection.find({"header.receipt_id": receipt_id}).sort("header.version.number", 1))

    def archive(self, snapshot_id):
        self.collection.update_one({"header.snapshot_id": snapshot_id}, {"$set": {"header.version.status": "archived", "summary.status": "archived"}})
        value = self.get(snapshot_id)
        if value is None: raise KeyError("snapshot_not_found")
        return value

    def delete(self, snapshot_id):
        return self.collection.delete_one({"header.snapshot_id": snapshot_id}).deleted_count == 1

