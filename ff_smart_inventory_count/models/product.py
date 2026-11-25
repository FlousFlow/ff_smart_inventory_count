from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    reserved_qty = fields.Float(
        string="Reserved Quantity",
        compute="_compute_reserved_qty",
        digits="Product Unit",
        compute_sudo=False,
        help="Quantity on hand minus quantity free to use, using the active stock report context.",
    )

    @api.depends("qty_available", "free_qty")
    @api.depends_context(
        "lot_id",
        "owner_id",
        "package_id",
        "from_date",
        "to_date",
        "location",
        "warehouse_id",
        "allowed_company_ids",
        "is_storable",
    )
    def _compute_reserved_qty(self):
        for product in self:
            product.reserved_qty = product.qty_available - product.free_qty
