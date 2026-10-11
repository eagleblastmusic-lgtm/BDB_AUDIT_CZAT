"""PRODUCT-V1 activation boundary; no caller setting grants NF02 authority."""
from .core.errors import ValidationError

NF02_BLOCK_CODE = "PRODUCT_V1_EXTERNAL_INGESTION_BLOCKED"
NF02_BLOCK_DETAIL = (
    "NF02 OPEN: brak niezależnie autoryzowanego producenta i kwalifikowanej "
    "aktywacji. Zachowaj ZIP poza historią. Przygotowanie paczek, lokalne "
    "kontrole i raport częściowy są dostępne; E1-E6 nie jest ukończone."
)
EXTERNAL_RESULT_KINDS = frozenset({"lane_result_admission_evidence", "bdb_audit_lane_result"})


def require_external_ingestion_authority() -> None:
    """Fail before raw retention, tickets, transactions, or completion writes."""
    raise ValidationError(NF02_BLOCK_CODE, NF02_BLOCK_DETAIL)
