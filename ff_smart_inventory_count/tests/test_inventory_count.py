from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSmartInventoryCount(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(su=True)
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.location = cls.warehouse.lot_stock_id
        cls.product = cls.env["product.product"].create({
            "name": "Smart Count Test Product",
            "is_storable": True,
            "standard_price": 10.0,
        })

    def _session(self, assignments=None):
        session = self.env["ff.inventory.count.session"].create({
            "warehouse_id": self.warehouse.id,
            "location_ids": [(6, 0, [self.location.id])],
        })
        for user, location in assignments or [(self.env.user, self.location)]:
            self.env["ff.inventory.count.assignment"].create({
                "session_id": session.id,
                "assigned_user_id": user.id,
                "location_id": location.id,
            })
        return session

    def test_start_creates_one_sheet_per_location_assignment(self):
        second_location = self.env["stock.location"].create({
            "name": "Smart Count Secondary Location",
            "location_id": self.warehouse.view_location_id.id,
            "usage": "internal",
            "company_id": self.warehouse.company_id.id,
        })
        session = self._session([
            (self.env.user, self.location),
            (self.env.user, second_location),
        ])
        session.action_start()
        self.assertEqual(session.sheet_ids.mapped("location_id"), self.location | second_location)
        self.assertEqual(len(session.sheet_ids), 2)

    def test_unassigned_location_blocks_start(self):
        session = self.env["ff.inventory.count.session"].create({
            "warehouse_id": self.warehouse.id,
            "location_ids": [(6, 0, [self.location.id])],
        })
        with self.assertRaises(ValidationError):
            session.action_start()

    def test_lines_require_counting_sheet(self):
        session = self._session()
        session.action_start()
        sheet = session.sheet_ids
        with self.assertRaises(ValidationError):
            self.env["ff.inventory.count.line"].create({
                "sheet_id": sheet.id,
                "product_id": self.product.id,
                "counted_qty": 1.0,
            })
        sheet.action_start()
        line = self.env["ff.inventory.count.line"].create({
            "sheet_id": sheet.id,
            "product_id": self.product.id,
            "counted_qty": 1.0,
        })
        self.assertEqual(line.location_id, self.location)

    def test_active_session_cannot_be_deleted(self):
        session = self._session()
        session.action_start()
        with self.assertRaises(UserError):
            session.unlink()

    def test_location_assignment_is_immutable_after_start(self):
        session = self._session()
        assignment = session.assignment_ids
        session.action_start()
        with self.assertRaises(UserError):
            assignment.write({"location_id": self.warehouse.view_location_id.id})
        with self.assertRaises(UserError):
            assignment.unlink()

    def test_manual_stock_quant_inventory_write_is_blocked(self):
        quant = self.env["stock.quant"].create({
            "product_id": self.product.id,
            "location_id": self.location.id,
        })
        with self.assertRaises(UserError):
            quant.with_context(inventory_mode=True).write({"inventory_quantity": 1.0})

    def test_count_user_cannot_read_another_users_sheet(self):
        count_group = self.env.ref("ff_smart_inventory_count.group_count_user")
        user_a = self.env["res.users"].create({
            "name": "Smart Count User A",
            "login": "smart-count-a@example.test",
            "group_ids": [(6, 0, [count_group.id])],
        })
        user_b = self.env["res.users"].create({
            "name": "Smart Count User B",
            "login": "smart-count-b@example.test",
            "group_ids": [(6, 0, [count_group.id])],
        })
        session = self._session([(user_a, self.location), (user_b, self.location)])
        session.action_start()
        sheet_a = session.sheet_ids.filtered(lambda sheet: sheet.assigned_user_id == user_a)
        sheet_b = session.sheet_ids.filtered(lambda sheet: sheet.assigned_user_id == user_b)
        visible_to_a = self.env["ff.inventory.count.sheet"].with_user(user_a).search(
            [("id", "in", (sheet_a | sheet_b).ids)]
        )
        self.assertEqual(visible_to_a, sheet_a)

    def test_consolidation_keeps_lot_and_package_identity(self):
        self.product.tracking = "lot"
        lot = self.env["stock.lot"].create({
            "name": "SMART-LOT-001",
            "product_id": self.product.id,
            "company_id": self.warehouse.company_id.id,
        })
        package = self.env["stock.package"].create({"name": "SMART-PACK-001"})
        session = self._session()
        session.action_start()
        sheet = session.sheet_ids
        sheet.action_start()
        self.env["ff.inventory.count.line"].create({
            "sheet_id": sheet.id,
            "product_id": self.product.id,
            "lot_id": lot.id,
            "package_id": package.id,
            "counted_qty": 2.0,
        })
        sheet.action_submit()
        session.action_consolidate()
        result = session.consolidated_line_ids
        self.assertEqual(len(result), 1)
        self.assertEqual(result.lot_id, lot)
        self.assertEqual(result.package_id, package)

    def test_missing_account_configuration_fails_before_stock_change(self):
        company = self.warehouse.company_id
        company.write({
            "inventory_count_journal_id": False,
            "inventory_count_damage_account_id": False,
            "inventory_count_employee_loss_account_id": False,
            "inventory_count_cogs_account_id": False,
        })
        session = self._session()
        line = self.env["ff.inventory.count.consolidated.line"].create({
            "session_id": session.id,
            "product_id": self.product.id,
            "location_id": self.location.id,
            "product_uom_id": self.product.uom_id.id,
            "theoretical_qty": 1.0,
            "counted_qty": 0.0,
            "reconciliation_status": "adjust",
            "variance_reason": "cogs",
        })
        with self.assertRaises(ValidationError):
            line.apply_adjustment()
        self.assertFalse(line.applied)
        self.assertFalse(line.account_move_id)

    def test_variance_application_posts_accounting_move(self):
        journal = self.env["account.journal"].search([
            ("company_id", "=", self.warehouse.company_id.id), ("type", "=", "general")
        ], limit=1)
        valuation_account = self.env["account.account"].search([
            ("account_type", "=", "asset_current"),
        ], limit=1)
        variance_account = self.env["account.account"].search([
            ("account_type", "=", "expense"),
        ], limit=1)
        self.assertTrue(journal and valuation_account and variance_account)
        company = self.warehouse.company_id
        company.write({
            "inventory_count_journal_id": journal.id,
            "inventory_count_cogs_account_id": variance_account.id,
        })
        category = self.env["product.category"].create({
            "name": "Smart Count Valuation Category",
            "property_stock_valuation_account_id": valuation_account.id,
        })
        self.product.categ_id = category
        session = self._session()
        line = self.env["ff.inventory.count.consolidated.line"].create({
            "session_id": session.id,
            "product_id": self.product.id,
            "location_id": self.location.id,
            "product_uom_id": self.product.uom_id.id,
            "theoretical_qty": 1.0,
            "counted_qty": 0.0,
            "reconciliation_status": "adjust",
            "variance_reason": "cogs",
        })
        line.apply_adjustment()
        self.assertTrue(line.applied)
        self.assertEqual(line.account_move_id.state, "posted")
