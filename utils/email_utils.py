import smtplib
import logging
import markdown
import os
from datetime import datetime
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from core.config import get_settings
from models.schemas import AnalysisResult

logger = logging.getLogger(__name__)
settings = get_settings()

def _generate_html_table(headers: list, data: list) -> str:
    """Generates a clean HTML table from a list of dicts."""
    if not data:
        return "<p style='color: #718096; font-style: italic;'>No data available.</p>"
    
    html = "<table><thead><tr>"
    for h in headers:
        html += f"<th>{h}</th>"
    html += "</tr></thead><tbody>"
    
    for row in data:
        html += "<tr>"
        # We assume values are in order of headers or we map them
        # Let's map dynamically based on values but for our case we know the keys
        for val in row.values():
            html += f"<td>{val}</td>"
        html += "</tr>"
    
    html += "</tbody></table>"
    return html

def send_invoice_processed_email(recipient_email: str, filename: str, analysis: AnalysisResult = None, csv_content: str = None):
    """
    Sends a professional corporate HTML email notification with structured tables.
    """
    if not recipient_email or not analysis:
        logger.warning("Recipient or analysis missing, skipping email.")
        return
        
    try:
        msg = EmailMessage()
        msg['Subject'] = f"Invoice Report: {filename} ({analysis.status})"
        msg['From'] = settings.smtp_sender
        msg['To'] = recipient_email

        # Prepare Logo CID
        logo_cid = make_msgid()
        logo_path = Path("public/logo_cbn.png")
        
        status_text = "PASSED" if analysis.status == "MATCH" else "REVIEW REQUIRED"
        status_color = "#2d3748"

        # 1. Summary Table
        summary_data = [
            {"label": "Total Penjualan ke Customer (CSV)", "value": f"Rp {analysis.database_total:,.2f}"},
            {"label": "Total Biaya ke Vendor (Invoice)", "value": f"Rp {analysis.pdf_total:,.2f}"},
            {"label": "Selisih (Gross Margin)", "value": f"Rp {analysis.difference:,.2f}"},
            {"label": "Margin Kotor", "value": f"{(analysis.difference/analysis.database_total*100 if analysis.database_total else 0):.1f}%"}
        ]
        summary_table = _generate_html_table(["Komponen", "Nilai (Rp)"], summary_data)

        # 2. Customer Table (Formatted)
        formatted_customers = []
        for row in (analysis.customer_breakdown or []):
            formatted_row = row.copy()
            if 'amount' in formatted_row:
                val = formatted_row['amount']
                formatted_row['amount'] = f"Rp {float(val):,.2f}" if val is not None else "Rp 0.00"
            formatted_customers.append(formatted_row)

        customer_table = _generate_html_table(
            ["No", "Customer", "Nilai Tagihan (Rp)", "%"],
            formatted_customers
        ) if analysis.customer_breakdown else "<p>No customer data.</p>"

        # 3. Product Table (Formatted)
        formatted_products = []
        for row in (analysis.product_breakdown or []):
            formatted_row = row.copy()
            if 'amount' in formatted_row:
                val = formatted_row['amount']
                formatted_row['amount'] = f"Rp {float(val):,.2f}" if val is not None else "Rp 0.00"
            formatted_products.append(formatted_row)

        product_table = _generate_html_table(
            ["Kode", "Produk", "Nilai (Rp)", "%"],
            formatted_products
        ) if analysis.product_breakdown else "<p>No product data.</p>"

        # 4. Recommendations Table
        rec_table = _generate_html_table(
            ["Isu", "Rekomendasi"],
            analysis.recommendations
        ) if analysis.recommendations else "<p>No recommendations.</p>"

        # AI Commentary (Markdown to HTML)
        commentary_html = markdown.markdown(analysis.analysis, extensions=['nl2br']) if analysis.analysis else ""

        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; line-height: 1.6; margin: 0; padding: 0; background-color: #ffffff; }}
                .container {{ max-width: 750px; margin: 20px auto; padding: 30px; border: 1px solid #e2e8f0; }}
                .header {{ border-bottom: 2px solid #2d3748; padding-bottom: 15px; margin-bottom: 25px; }}
                .logo {{ height: 45px; }}
                .section-title {{ font-size: 16px; font-weight: bold; color: #2d3748; margin-top: 30px; margin-bottom: 10px; border-left: 4px solid #c53030; padding-left: 10px; }}
                .status-box {{ padding: 15px; background-color: #f7fafc; border: 1px solid #edf2f7; margin: 20px 0; border-radius: 4px; }}
                .report-content {{ font-size: 14px; color: #4a5568; }}
                table {{ border-collapse: collapse; width: 100%; margin: 15px 0; font-size: 13px; border: 1px solid #e2e8f0; }}
                th, td {{ border: 1px solid #e2e8f0; padding: 12px; text-align: left; }}
                th {{ background-color: #f8fafc; font-weight: bold; color: #4a5568; text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em; }}
                tr:nth-child(even) {{ background-color: #fbfcfd; }}
                .footer {{ margin-top: 50px; padding-top: 20px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #a0aec0; text-align: center; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <img src="cid:{logo_cid[1:-1]}" alt="CBN Logo" class="logo">
                </div>
                
                <h2 style="font-size: 20px; color: #2d3748; margin-bottom: 5px;">Invoice Reconciliation Report</h2>
                <p style="color: #718096; margin-top: 0;">Period Analysis for <strong>{filename}</strong></p>
                
                <div class="status-box">
                    <strong>Reconciliation Status:</strong> <span style="color: {status_color}; font-weight: bold;">{status_text}</span>
                </div>

                <div class="section-title">📊 RINGKASAN ANGKA (SEBELUM PPN)</div>
                {summary_table}

                <div class="section-title">📈 BREAKDOWN PER CUSTOMER</div>
                {customer_table}

                <div class="section-title">🖥️ BREAKDOWN PER PRODUK VMWARE</div>
                {product_table}

                <div class="section-title">🔍 INTERPRETASI & ANALISIS</div>
                <div class="report-content">
                    {commentary_html}
                </div>

                <div class="section-title">⚠️ CATATAN & REKOMENDASI</div>
                {rec_table}

                <p style="margin-top: 30px; font-size: 14px;">Detailed audit data is attached as a CSV file for your records.</p>
                
                <div class="footer">
                    &copy; {datetime.now().year} Ai Analyze Audit System | Confidential Corporate Communication
                </div>
            </div>
        </body>
        </html>
        """
        
        msg.set_content(f"Invoice Report for {filename}. Status: {status_text}")
        msg.add_alternative(html_content, subtype='html')

        # Attach Logo
        if logo_path.exists():
            with open(logo_path, 'rb') as img:
                msg.get_payload()[1].add_related(
                    img.read(),
                    maintype='image',
                    subtype='png',
                    cid=logo_cid
                )

        if csv_content:
            report_filename = filename.rsplit('.', 1)[0] + "_audit.csv"
            # Add UTF-8 BOM AND sep=, for Excel compatibility
            csv_with_bom = "\ufeffsep=,\n" + csv_content
            msg.add_attachment(
                csv_with_bom.encode('utf-8'),
                maintype='text',
                subtype='csv',
                filename=report_filename
            )

        # SMTP Connection
        if settings.smtp_secure:
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port)
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)
            server.starttls()
            
        server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)
        server.quit()
        logger.info(f"Successfully sent structured corporate email to {recipient_email}")
        
    except Exception as e:
        logger.exception(f"Failed to send email to {recipient_email}")
