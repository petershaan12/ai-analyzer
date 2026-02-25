import csv
import io
from models.schemas import InvoiceRow

_HEADERS = ["customer_id", "name", "code", "itemname", "amount"]

def rows_to_csv_bytes(rows: list[InvoiceRow]) -> bytes:
    return rows_to_csv_string(rows).encode("utf-8")

def rows_to_csv_string(rows: list[InvoiceRow]) -> str:
    """Returns a full CSV string (header + data rows)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_HEADERS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row.model_dump())
    return buf.getvalue()
