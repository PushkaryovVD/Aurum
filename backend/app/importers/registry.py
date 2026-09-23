"""The set of bank adapters the app knows about.

Order matters only when two adapters claim the same extension — the first one
whose supports() matches is offered the file.
"""
from app.importers.base import StatementImporter
from app.importers.freedom_bank import FreedomBankPdfImporter
from app.importers.kaspi import KaspiPdfImporter
from app.importers.tradernet import TradernetImporter

IMPORTERS: tuple[StatementImporter, ...] = (
    TradernetImporter(),
    KaspiPdfImporter(),
    FreedomBankPdfImporter(),
)

#: Every extension the import endpoint will accept, for the error message and
#: the file picker.
SUPPORTED_EXTENSIONS: tuple[str, ...] = tuple(
    sorted({extension for importer in IMPORTERS for extension in importer.extensions})
)


def resolve_importers(file_name: str) -> tuple[StatementImporter, ...]:
    """All adapters that claim the extension.

    More than one bank uses PDF, so content recognition belongs in each
    adapter's parse() method rather than in the registry.
    """
    return tuple(importer for importer in IMPORTERS if importer.supports(file_name))
