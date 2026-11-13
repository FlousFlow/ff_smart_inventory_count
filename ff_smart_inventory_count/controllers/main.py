import csv
import io

from odoo import http
from odoo.http import request
from odoo.http.stream import content_disposition


class InventoryCountTemplateController(http.Controller):

    @http.route(
        "/ff_smart_inventory_count/sheet/<int:sheet_id>/template",
        type="http",
        auth="user",
    )
    def download_template(self, sheet_id):
        sheet = request.env["ff.inventory.count.sheet"].browse(sheet_id).exists()
        if not sheet:
            return request.not_found()
        try:
            sheet.check_access_rights("read")
            sheet.check_access_rule("read")
        except Exception:
            return request.not_found()
        if sheet.state != "in_progress":
            return request.not_found()

        quants = request.env["stock.quant"].sudo().search([
            ("location_id", "child_of", sheet.location_id.id),
            ("company_id", "=", sheet.company_id.id),
            ("quantity", "!=", 0),
        ], order="location_id, product_id, lot_id, package_id, owner_id")
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow([
            "Product/External ID", "Product", "Internal Reference", "Barcode",
            "Location", "Lot", "Package", "On Hand", "Counted Qty",
        ])
        external_ids = quants.mapped("product_id").get_external_id()
        for quant in quants:
            writer.writerow([
                external_ids.get(quant.product_id.id, ""),
                quant.product_id.display_name,
                quant.product_id.default_code or "",
                quant.product_id.barcode or "",
                quant.location_id.complete_name,
                quant.lot_id.name or "",
                quant.package_id.name or "",
                quant.quantity,
                "",
            ])
        filename = f"{sheet.name}_count_template.csv"
        return request.make_response(
            output.getvalue().encode("utf-8-sig"),
            headers=[
                ("Content-Type", "text/csv; charset=utf-8"),
                ("Content-Disposition", content_disposition(filename)),
            ],
        )
