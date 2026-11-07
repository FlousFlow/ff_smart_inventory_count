from odoo import _, models
from odoo.exceptions import UserError


class StockQuant(models.Model):
    """Make the Smart Inventory Count workflow the only manual adjustment path."""

    _inherit = "stock.quant"

    def _smart_count_adjustment_allowed(self):
        return bool(self.env.context.get("ff_smart_inventory_count_apply"))

    def _check_smart_count_adjustment(self):
        if not self._smart_count_adjustment_allowed():
            raise UserError(
                _(
                    "Manual inventory adjustments are disabled. "
                    "Use Smart Inventory Count sessions and supervisor approval."
                )
            )

    def create(self, vals_list):
        if self.env.context.get("inventory_mode") and not self._smart_count_adjustment_allowed():
            if any("inventory_quantity" in vals or "inventory_quantity_auto_apply" in vals for vals in vals_list):
                self._check_smart_count_adjustment()
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get("inventory_mode") and not self._smart_count_adjustment_allowed():
            inventory_fields = {
                "inventory_quantity",
                "inventory_quantity_auto_apply",
                "inventory_quantity_set",
                "inventory_date",
            }
            if inventory_fields.intersection(vals):
                self._check_smart_count_adjustment()
        return super().write(vals)

    def action_apply_inventory(self, date=None):
        self._check_smart_count_adjustment()
        return super().action_apply_inventory(date=date)

    def _apply_inventory(self, date=None):
        self._check_smart_count_adjustment()
        return super()._apply_inventory(date=date)
