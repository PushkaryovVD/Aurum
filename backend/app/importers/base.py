"""One adapter per bank document format.

Every format quirk lives in its own module and is registered in registry.py —
never as another branch inside a shared parser, which is how one bank's
exception ends up silently applied to every other bank's file.

Adding a bank means: write a StatementImporter, register it, add a fixture.
Nothing else in the import path needs to know it exists.
"""
from abc import ABC, abstractmethod

from app.schemas.statement_import import StatementPreview


class StatementImporter(ABC):
    """Turns a bank document into rows the user reviews before anything is
    saved.

    `parse` must never touch the database. It reads bytes and reports what it
    recognised — including the rows it deliberately skipped and why — and
    nothing is written until the user confirms the preview (see
    services/statement_import_service.commit_statement).
    """

    #: Stable identifier; also the `provider` value on a preview.
    id: str
    #: Human-readable bank/product name, shown in the UI.
    label: str
    #: Lower-case extensions this adapter claims, e.g. (".xlsx",).
    extensions: tuple[str, ...]

    def supports(self, file_name: str) -> bool:
        """Whether this adapter handles the file at all — a cheap extension
        check. Whether the *content* really is this format is decided by
        parse(), which raises 422 when the document doesn't match."""
        return file_name.lower().endswith(self.extensions)

    @abstractmethod
    def parse(self, file_name: str, content: bytes) -> StatementPreview:
        """Recognise the document and return its rows, or raise HTTPException
        (422) when it isn't this format."""
        raise NotImplementedError
