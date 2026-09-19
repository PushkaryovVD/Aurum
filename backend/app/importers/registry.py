"""The set of bank adapters the app knows about.

Order matters only when two adapters claim the same extension — the first one
whose supports() matches is offered the file.
"""
from app.importers.base import StatementImporter
from app.importers.tradernet import TradernetImporter

IMPORTERS: tuple[StatementImporter, ...] = (TradernetImporter(),)

#: Every extension the import endpoint will accept, for the error message and
#: the file picker.
SUPPORTED_EXTENSIONS: tuple[str, ...] = tuple(
    sorted({extension for importer in IMPORTERS for extension in importer.extensions})
)


def resolve_importer(file_name: str) -> StatementImporter | None:
    """The adapter that claims this file, by extension — or None when the app
    has no adapter for it at all (a different message from "this adapter
    couldn't read your file")."""
    return next((importer for importer in IMPORTERS if importer.supports(file_name)), None)
