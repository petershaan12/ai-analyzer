import logging
from sqlalchemy.orm import Session
from sqlalchemy import text
from models.schemas import InvoiceRow

logger = logging.getLogger(__name__)

class InvoiceRepository:
    @staticmethod
    def get_vmware_category_ids(db: Session) -> list[int]:
        rows = db.execute(
            text("""
                WITH RECURSIVE vmware_categories AS (
                    SELECT id, parent FROM product_category WHERE LOWER(name) LIKE '%vmware%'
                    UNION ALL
                    SELECT pc.id, pc.parent FROM product_category pc
                    INNER JOIN vmware_categories vc ON pc.parent = vc.id
                )
                SELECT id FROM vmware_categories
            """)
        ).fetchall()
        ids = [r[0] for r in rows]
        logger.info("[DB] vmware category_ids = %s", ids)
        return ids

    @staticmethod
    def get_product_ids_by_categories(db: Session, category_ids: list[int]) -> list[int]:
        if not category_ids:
            return []
        rows = db.execute(
            text("SELECT DISTINCT id FROM product WHERE product_category_id IN :cat_ids"),
            {"cat_ids": tuple(category_ids)},
        ).fetchall()
        ids = [r[0] for r in rows]
        logger.info("[DB] product_ids for categories %s = %s", category_ids, ids)
        return ids

    @staticmethod
    def get_invoice_rows_by_period(
        db: Session, 
        product_ids: list[int],
        billing_month: str,
        billing_year: str,
    ) -> list[InvoiceRow]:
        if not product_ids:
            return []

        month_part = billing_month.split("-")[1]
        rows = db.execute(
            text("""
                SELECT
                    inv.customer_id,
                    cust.name           AS name,
                    prod.code           AS code,
                    prod.name           AS itemname,
                    ii.amount           AS amount
                FROM invoice_item ii
                JOIN invoice  inv  ON inv.inv_no        = ii.inv_no
                JOIN product  prod ON prod.id           = ii.product_id
                JOIN customer cust ON cust.id           = inv.customer_id
                WHERE ii.product_id IN :product_list
                  AND YEAR(FROM_UNIXTIME(inv.inv_date))  = :yr
                  AND MONTH(FROM_UNIXTIME(inv.inv_date)) = :mo
                ORDER BY inv.customer_id, prod.code
                """
            ),
            {
                "product_list": tuple(product_ids),
                "yr": int(billing_year),
                "mo": int(month_part),
            },
        ).fetchall()

        result = [
            InvoiceRow(
                customer_id=str(r.customer_id),
                name=r.name or "N/A",
                code=r.code or "",
                itemname=r.itemname or "",
                amount=float(r.amount or 0),
            )
            for r in rows
        ]
        logger.info("[DB] Invoice rows fetched = %d for %s-%s", len(result), billing_year, month_part)
        return result
