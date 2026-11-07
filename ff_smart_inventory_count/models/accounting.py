from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    inventory_count_journal_id = fields.Many2one(
        "account.journal", string="Inventory Count Journal", check_company=True,
        domain="[('type', '=', 'general')]",
        help="General journal used for accounting entries created by approved inventory count variances.",
    )
    inventory_count_damage_account_id = fields.Many2one(
        "account.account", string="Damaged Products Account", check_company=True,
        domain="[('deprecated', '=', False)]",
        help="Debit or credit account used when the variance reason is damaged products.",
    )
    inventory_count_employee_loss_account_id = fields.Many2one(
        "account.account", string="Employee Loss Account", check_company=True,
        domain="[('deprecated', '=', False)]",
        help="Debit or credit account used when the variance reason is employee loss.",
    )
    inventory_count_cogs_account_id = fields.Many2one(
        "account.account", string="Inventory Count COGS Account", check_company=True,
        domain="[('deprecated', '=', False)]",
        help="Debit or credit account used when the variance is recognized as cost of goods sold.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    inventory_count_journal_id = fields.Many2one(
        related="company_id.inventory_count_journal_id", readonly=False,
    )
    inventory_count_damage_account_id = fields.Many2one(
        related="company_id.inventory_count_damage_account_id", readonly=False,
    )
    inventory_count_employee_loss_account_id = fields.Many2one(
        related="company_id.inventory_count_employee_loss_account_id", readonly=False,
    )
    inventory_count_cogs_account_id = fields.Many2one(
        related="company_id.inventory_count_cogs_account_id", readonly=False,
    )
