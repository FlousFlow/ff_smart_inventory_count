from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_is_zero


class InventoryCountAssignment(models.Model):
    _name = "ff.inventory.count.assignment"
    _description = "Inventory Count Location Assignment"
    _check_company_auto = True
    _order = "location_id, assigned_user_id"

    session_id = fields.Many2one(
        "ff.inventory.count.session", required=True, ondelete="cascade", check_company=True
    )
    company_id = fields.Many2one(related="session_id.company_id", store=True, index=True)
    location_id = fields.Many2one(
        "stock.location", required=True, ondelete="restrict", check_company=True,
        domain="[('usage', '=', 'internal')]",
    )
    assigned_user_id = fields.Many2one("res.users", required=True, ondelete="restrict")

    _session_location_user_uniq = models.Constraint(
        "UNIQUE(session_id, location_id, assigned_user_id)",
        "The same user cannot be assigned to the same location twice in one session.",
    )

    @api.constrains("session_id", "location_id")
    def _check_assignment_location(self):
        for rec in self:
            if rec.location_id and rec.location_id.usage != "internal":
                raise ValidationError(_("Count assignments must use internal locations."))
            warehouse = rec.session_id.warehouse_id if rec.session_id else False
            if warehouse and rec.location_id and not self.env["stock.location"].search_count([
                ("id", "=", rec.location_id.id),
                ("id", "child_of", warehouse.view_location_id.id),
            ]):
                raise ValidationError(
                    _("Each assigned location must belong to the selected warehouse.")
                )

    def write(self, vals):
        if set(vals) & {"session_id", "location_id", "assigned_user_id"}:
            for rec in self:
                if rec.session_id.state != "draft":
                    raise UserError(
                        _("Location assignments cannot be changed after the count session starts.")
                    )
        return super().write(vals)

    def unlink(self):
        if any(rec.session_id.state != "draft" for rec in self):
            raise UserError(
                _("Location assignments cannot be deleted after the count session starts.")
            )
        return super().unlink()


class InventoryCountSession(models.Model):
    _name = "ff.inventory.count.session"
    _description = "Smart Inventory Count Session"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True
    _order = "scheduled_date desc, id desc"

    name = fields.Char(default="New", copy=False, required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    warehouse_id = fields.Many2one("stock.warehouse", required=True, check_company=True)
    location_ids = fields.Many2many("stock.location", "ff_count_location_rel",
                                    "session_id", "location_id",
                                    string="Count Locations",
                                    domain="[('usage', '=', 'internal')]")
    scheduled_date = fields.Date(default=fields.Date.context_today, required=True)
    count_start_datetime = fields.Datetime(readonly=True)
    count_end_datetime = fields.Datetime(readonly=True)
    supervisor_ids = fields.Many2many("res.users", "ff_count_supervisor_rel",
                                      "session_id", "user_id", string="Supervisors")
    assigned_user_ids = fields.Many2many("res.users", "ff_count_assignee_rel",
                                         "session_id", "user_id", string="Assigned Users")
    assignment_ids = fields.One2many(
        "ff.inventory.count.assignment", "session_id", string="Location Assignments"
    )
    count_scope = fields.Selection([("locations", "Selected Locations"), ("warehouse", "Whole Warehouse")],
                                   default="locations", required=True)
    count_type = fields.Selection([
        ("regular", "Regular Inventory Count"),
        ("opening", "Opening Inventory"),
    ], default="regular", required=True, string="Count Type")
    default_variance_reason = fields.Selection([
        ("damage", "Damaged Products"),
        ("employee_loss", "Employee Loss"),
        ("cogs", "Recognize Cost of Goods Sold"),
    ], string="Default Variance Reason")
    movement_policy = fields.Selection([("freeze", "Freeze movements during count"),
                                        ("allow", "Allow movements and review at submission")],
                                       default="allow", required=True)
    state = fields.Selection([
        ("draft", "Draft"), ("in_progress", "Counting"), ("submitted", "Submitted"),
        ("under_review", "Under Review"), ("approved", "Approved"), ("done", "Closed"),
        ("cancelled", "Cancelled"),
    ], default="draft", required=True, tracking=True)
    sheet_ids = fields.One2many("ff.inventory.count.sheet", "session_id")
    consolidated_line_ids = fields.One2many("ff.inventory.count.consolidated.line", "session_id")
    has_remaining_adjustments = fields.Boolean(compute="_compute_has_remaining_adjustments")
    notes = fields.Text()

    @api.depends("consolidated_line_ids.applied", "consolidated_line_ids.reconciliation_status")
    def _compute_has_remaining_adjustments(self):
        for rec in self:
            rec.has_remaining_adjustments = any(
                not line.applied and line.reconciliation_status in ("pending", "adjust")
                for line in rec.consolidated_line_ids
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("ff.inventory.count.session") or "New"
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get("count_type") == "opening":
            vals["default_variance_reason"] = False
        setup_fields = {
            "company_id", "warehouse_id", "count_scope", "count_type",
            "location_ids", "assigned_user_ids", "assignment_ids", "movement_policy",
        }
        if setup_fields.intersection(vals):
            for rec in self:
                if rec.state != "draft":
                    raise UserError(
                        _("Session setup cannot be changed after the count starts. Create a new session for a different warehouse, location, or assignment.")
                    )
        if "default_variance_reason" in vals:
            for rec in self:
                if rec.state in ("done", "cancelled"):
                    raise UserError(_("The default variance reason cannot be changed on a closed or cancelled session."))
                if rec.count_type == "opening":
                    vals["default_variance_reason"] = False
        result = super().write(vals)
        if "default_variance_reason" in vals and vals.get("default_variance_reason"):
            for rec in self:
                pending_lines = rec.consolidated_line_ids.filtered(
                    lambda line: line.reconciliation_status == "pending"
                    and not line.variance_reason
                    and not float_is_zero(line.variance_qty, precision_digits=6)
                )
                pending_lines.with_context(ff_inventory_count_workflow=True).write(
                    {"variance_reason": rec.default_variance_reason}
                )
        return result

    @api.onchange("count_type")
    def _onchange_count_type(self):
        if self.count_type == "opening":
            self.default_variance_reason = False

    @api.constrains("location_ids", "warehouse_id", "company_id")
    def _check_locations(self):
        for rec in self:
            if not rec.location_ids:
                continue
            invalid = rec.location_ids.filtered(lambda l: l.usage != "internal" or l.company_id not in (False, rec.company_id))
            if invalid:
                raise ValidationError(_("Count locations must be internal locations belonging to the session company."))
            if rec.warehouse_id and any(loc not in rec.warehouse_id.view_location_id.child_ids and
                                        not self.env["stock.location"].search_count([
                                            ("id", "=", loc.id), ("id", "child_of", rec.warehouse_id.view_location_id.id)
                                        ]) for loc in rec.location_ids):
                raise ValidationError(_("All count locations must belong to the selected warehouse."))

    def _require_supervisor(self):
        if not (self.env.user.has_group("ff_smart_inventory_count.group_count_manager") or
                self.env.user.has_group("stock.group_stock_manager") or self.env.is_superuser()):
            raise UserError(_("Only an inventory supervisor can perform this action."))

    def action_start(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft sessions can be started."))
            if rec.count_scope == "warehouse" and not rec.location_ids:
                if not rec.warehouse_id:
                    raise ValidationError(_("Select a warehouse before starting the count."))
                locations = self.env["stock.location"].search([
                    ("id", "child_of", rec.warehouse_id.view_location_id.id),
                    ("usage", "=", "internal"),
                    ("company_id", "in", [False, rec.company_id.id]),
                ])
                if not locations:
                    raise ValidationError(_("The selected warehouse has no internal locations to count."))
                rec.location_ids = [(6, 0, locations.ids)]
            assignments = rec.assignment_ids
            # A first count can be prepared with one counter for several
            # locations. More complex splits still require explicit rows so
            # that overlapping assignments cannot be created accidentally.
            if not assignments and rec.assigned_user_ids and len(rec.assigned_user_ids) == 1:
                assignments = self.env["ff.inventory.count.assignment"].create([
                    {"session_id": rec.id, "assigned_user_id": user.id,
                     "location_id": location.id}
                    for location in rec.location_ids
                    for user in rec.assigned_user_ids
                ])
            if not assignments:
                raise ValidationError(
                    _("Assign at least one counting user to a location before starting.")
                )
            configured_locations = rec.location_ids
            assignment_locations = assignments.mapped("location_id")
            missing_locations = configured_locations - assignment_locations
            if missing_locations:
                raise ValidationError(
                    _("Assign a counting user to every selected location before starting.")
                )
            # The assignment table is the user-facing source of truth. Keep the
            # legacy M2M field synchronized for reporting and older records.
            rec.write({"location_ids": [(6, 0, assignment_locations.ids)]})
            rec.write({"state": "in_progress", "count_start_datetime": fields.Datetime.now()})
            for assignment in assignments:
                self.env["ff.inventory.count.sheet"].create({
                    "session_id": rec.id,
                    "assigned_user_id": assignment.assigned_user_id.id,
                    "location_id": assignment.location_id.id,
                })

    def action_consolidate(self):
        self.ensure_one()
        self._require_supervisor()
        if self.state not in ("in_progress", "submitted", "under_review"):
            raise UserError(_("The session is not ready for consolidation."))
        sheets = self.sheet_ids.filtered(lambda s: s.state == "submitted")
        if not sheets:
            raise ValidationError(_("Submit at least one counting sheet first."))
        self.consolidated_line_ids.unlink()
        grouped = defaultdict(lambda: {"counted_qty": 0.0, "line_ids": []})
        for line in sheets.mapped("line_ids"):
            key = (line.product_id.id, line.location_id.id, line.lot_id.id, line.package_id.id, line.owner_id.id)
            grouped[key]["counted_qty"] += line.counted_qty
            grouped[key]["line_ids"].append(line.id)
        Quant = self.env["stock.quant"]
        product_ids = self.env["product.product"].browse([key[0] for key in grouped])
        location_ids = self.env["stock.location"].browse([key[1] for key in grouped])
        products_by_id = {product.id: product for product in product_ids}
        quants_cache = Quant._get_quants_by_products_locations(product_ids, location_ids)
        CachedQuant = Quant.with_context(quants_cache=quants_cache)
        consolidated_vals = []
        for key, values in grouped.items():
            product_id, location_id, lot_id, package_id, owner_id = key
            quant = CachedQuant._gather(products_by_id[product_id], self.env["stock.location"].browse(location_id),
                                  lot_id=self.env["stock.lot"].browse(lot_id), package_id=self.env["stock.package"].browse(package_id),
                                  owner_id=self.env["res.partner"].browse(owner_id), strict=True)
            theoretical = sum(quant.mapped("quantity"))
            product = products_by_id[product_id]
            consolidated_vals.append({
                "session_id": self.id, "product_id": product_id, "location_id": location_id,
                "lot_id": lot_id or False, "package_id": package_id or False, "owner_id": owner_id or False,
                "product_uom_id": product.uom_id.id, "theoretical_qty": theoretical,
                "counted_qty": values["counted_qty"], "count_source_line_ids": [(6, 0, values["line_ids"])],
            })
        self.env["ff.inventory.count.consolidated.line"].create(consolidated_vals)
        # Only a fully submitted assignment is allowed to identify missing
        # products. Partial counts intentionally never create zero lines.
        if self.sheet_ids and all(sheet.state == "submitted" for sheet in self.sheet_ids):
            counted_keys = set(grouped)
            quants = Quant.search([
                ("location_id", "child_of", self.location_ids.ids),
                ("quantity", "!=", 0),
                ("company_id", "=", self.company_id.id),
            ])
            missing_vals = []
            for quant in quants:
                key = (quant.product_id.id, quant.location_id.id, quant.lot_id.id,
                       quant.package_id.id, quant.owner_id.id)
                if key in counted_keys:
                    continue
                missing_vals.append({
                    "session_id": self.id, "product_id": quant.product_id.id,
                    "location_id": quant.location_id.id, "lot_id": quant.lot_id.id or False,
                    "package_id": quant.package_id.id or False, "owner_id": quant.owner_id.id or False,
                    "product_uom_id": quant.product_id.uom_id.id,
                    "theoretical_qty": quant.quantity, "counted_qty": 0.0,
                    "reconciliation_status": "pending",
                })
            if missing_vals:
                self.env["ff.inventory.count.consolidated.line"].create(missing_vals)
        self.write({"state": "under_review", "count_end_datetime": fields.Datetime.now()})

    def action_approve(self):
        self.ensure_one()
        self._require_supervisor()
        if self.state != "under_review":
            raise UserError(_("Only sessions under review can be approved."))
        if not self.consolidated_line_ids:
            raise ValidationError(_("Consolidate the submitted sheets first."))
        for line in self.consolidated_line_ids:
            # Pending variances must not silently disappear when a supervisor
            # approves the session. Zero variances are informational; every
            # non-zero variance is adjusted unless the supervisor chose Ignore.
            if line.reconciliation_status == "pending":
                if self.count_type == "opening" and not float_is_zero(line.variance_qty, precision_digits=6):
                    line.variance_reason = "opening"
                elif not line.variance_reason and self.default_variance_reason:
                    line.variance_reason = self.default_variance_reason
                if not float_is_zero(line.variance_qty, precision_digits=6) and not line.variance_reason:
                    raise ValidationError(
                        _("Select a reason for every inventory variance before approval.")
                    )
                line.reconciliation_status = (
                    "ignore" if float_is_zero(line.variance_qty, precision_digits=6)
                    else "adjust"
                )
            if line.reconciliation_status == "adjust":
                line.apply_adjustment()
        self.write({"state": "approved"})
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    def action_apply_remaining_adjustments(self):
        self.ensure_one()
        self._require_supervisor()
        if self.state not in ("approved", "done"):
            raise UserError(_("Only approved or closed sessions can apply remaining adjustments."))
        for line in self.consolidated_line_ids.filtered(lambda l: not l.applied):
            if line.reconciliation_status == "pending":
                line.reconciliation_status = (
                    "ignore" if float_is_zero(line.variance_qty, precision_digits=6)
                    else "adjust"
                )
            if line.reconciliation_status == "adjust":
                line.apply_adjustment()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    def action_close(self):
        self.ensure_one()
        self._require_supervisor()
        if self.state != "approved":
            raise UserError(_("Only approved sessions can be closed."))
        self.write({"state": "done"})

    def action_cancel(self):
        for rec in self:
            if rec.state in ("approved", "done"):
                raise UserError(_("Approved or closed sessions cannot be cancelled."))
            rec.write({"state": "cancelled"})

    def unlink(self):
        for rec in self:
            if rec.state != "draft" or rec.sheet_ids or rec.consolidated_line_ids:
                raise UserError(
                    _("A count session with activity or counted quantities cannot be deleted. Cancel it instead.")
                )
        return super().unlink()


class InventoryCountSheet(models.Model):
    _name = "ff.inventory.count.sheet"
    _description = "Employee Inventory Count Sheet"
    _check_company_auto = True
    _order = "id"

    name = fields.Char(default="New", readonly=True, copy=False)
    session_id = fields.Many2one("ff.inventory.count.session", required=True, ondelete="cascade", check_company=True)
    company_id = fields.Many2one(related="session_id.company_id", store=True, index=True)
    assigned_user_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user)
    location_id = fields.Many2one("stock.location", domain="[('usage', '=', 'internal')]")
    state = fields.Selection([("draft", "Draft"), ("in_progress", "Counting"), ("submitted", "Submitted")],
                             default="draft", required=True)
    started_at = fields.Datetime(readonly=True)
    submitted_at = fields.Datetime(readonly=True)
    line_ids = fields.One2many("ff.inventory.count.line", "sheet_id", copy=False)
    counted_product_count = fields.Integer(compute="_compute_counted_product_count")

    @api.depends("line_ids.product_id")
    def _compute_counted_product_count(self):
        for rec in self:
            rec.counted_product_count = len(rec.line_ids.mapped("product_id"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("session_id"):
                raise ValidationError(
                    _("Count sheets must be created from an inventory count session.")
                )
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("ff.inventory.count.sheet") or "New"
        return super().create(vals_list)

    def write(self, vals):
        manager = self.env.user.has_group("ff_smart_inventory_count.group_count_manager") or self.env.is_superuser()
        protected = {"session_id", "company_id", "assigned_user_id", "location_id", "name"}
        if not manager:
            if protected.intersection(vals):
                raise AccessError(_("Only an inventory supervisor can change a sheet assignment."))
            if "state" in vals:
                for rec in self:
                    target = vals["state"]
                    if target == "in_progress" and (rec.state != "draft" or rec.assigned_user_id != self.env.user):
                        raise AccessError(_("Only the assigned user can start this sheet."))
                    if target == "submitted" and (rec.state != "in_progress" or not rec.line_ids):
                        raise ValidationError(_("Start the sheet and add at least one count line."))
                    if target not in ("in_progress", "submitted"):
                        raise AccessError(_("The sheet status can only be changed through its workflow buttons."))
        return super().write(vals)

    def action_start(self):
        for rec in self:
            if rec.assigned_user_id != self.env.user and not self.env.user.has_group("ff_smart_inventory_count.group_count_manager"):
                raise UserError(_("Only the assigned user can start this sheet."))
            if rec.state == "draft":
                values = {"state": "in_progress", "started_at": fields.Datetime.now()}
                if not rec.location_id:
                    location = rec.session_id.location_ids[:1]
                    if not location:
                        raise ValidationError(
                            _("Select a count location on the inventory session before starting the sheet.")
                        )
                    values["location_id"] = location.id
                rec.write(values)

    def action_submit(self):
        for rec in self:
            if rec.assigned_user_id != self.env.user and not self.env.user.has_group("ff_smart_inventory_count.group_count_manager"):
                raise UserError(_("Only the assigned user can submit this sheet."))
            if rec.state != "in_progress" or not rec.line_ids:
                raise ValidationError(_("Start the sheet and add at least one count line."))
            rec.write({"state": "submitted", "submitted_at": fields.Datetime.now()})

    def unlink(self):
        for rec in self:
            if rec.state != "draft" or rec.line_ids or rec.session_id.state != "draft":
                raise UserError(
                    _("A count sheet with activity or counted quantities cannot be deleted.")
                )
        return super().unlink()

    def action_open_line_import(self):
        self.ensure_one()
        if self.state != "in_progress":
            raise UserError(_("Import is available while the sheet is in Counting state."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Import Count Lines"),
            "res_model": "ff.inventory.count.line",
            "view_mode": "list,form",
            "views": [(self.env.ref("ff_smart_inventory_count.view_count_line_import_tree").id, "list")],
            "domain": [("sheet_id", "=", self.id)],
            "context": {
                "default_sheet_id": self.id,
                "default_location_id": self.location_id.id,
                "search_default_sheet_id": self.id,
            },
        }


class InventoryCountLine(models.Model):
    _name = "ff.inventory.count.line"
    _description = "Physical Inventory Count Line"
    _check_company_auto = True

    sheet_id = fields.Many2one("ff.inventory.count.sheet", required=True, ondelete="cascade", check_company=True)
    company_id = fields.Many2one(related="sheet_id.company_id", store=True, index=True)
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one("product.product", required=True, check_company=True)
    location_id = fields.Many2one(
        related="sheet_id.location_id", store=True, required=True,
        check_company=True, string="Count Location",
    )
    lot_id = fields.Many2one("stock.lot", check_company=True)
    package_id = fields.Many2one("stock.package", check_company=True)
    owner_id = fields.Many2one("res.partner", check_company=True)
    product_uom_id = fields.Many2one("uom.uom", related="product_id.uom_id", store=True)
    counted_qty = fields.Float(required=True, digits="Product Unit of Measure")
    on_hand_qty = fields.Float(
        string="On Hand", compute="_compute_on_hand_qty",
        digits="Product Unit of Measure", readonly=True,
        help="Current theoretical quantity in the count location.",
    )
    counted_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    counted_by = fields.Many2one("res.users", default=lambda self: self.env.user, readonly=True)
    input_method = fields.Selection([("barcode", "Barcode"), ("manual", "Manual")], default="manual", required=True)
    barcode_reference = fields.Char(copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        """Backfill the count location for sheets created by older revisions."""
        sheets = self.env["ff.inventory.count.sheet"]
        for vals in vals_list:
            sheet = sheets.browse(vals.get("sheet_id")).exists() if vals.get("sheet_id") else sheets.browse()
            if not sheet:
                raise ValidationError(_("Count lines must be created inside an inventory count sheet."))
            if not vals.get("location_id") and vals.get("sheet_id"):
                location = sheet.location_id or sheet.session_id.location_ids[:1]
                if not location:
                    raise ValidationError(
                        _("Select a count location on the inventory session before adding lines.")
                    )
                vals["location_id"] = location.id
            if sheet.state != "in_progress":
                raise ValidationError(_("Count lines can only be added while the sheet is in Counting state."))
            if sheet.assigned_user_id != self.env.user and not self.env.user.has_group(
                "ff_smart_inventory_count.group_count_manager"
            ):
                raise AccessError(_("Only the assigned user can add count lines."))
        return super().create(vals_list)

    def write(self, vals):
        if set(vals) == {"on_hand_qty"} and self.env.context.get("ff_inventory_count_compute"):
            return super().write(vals)
        protected = {"sheet_id", "location_id", "company_id", "counted_by", "counted_at"}
        if protected.intersection(vals):
            raise AccessError(_("Count line ownership and location cannot be changed."))
        for rec in self:
            if rec.sheet_id.state != "in_progress":
                raise ValidationError(_("Count lines can only be edited while the sheet is in Counting state."))
            if rec.sheet_id.assigned_user_id != self.env.user and not self.env.user.has_group(
                "ff_smart_inventory_count.group_count_manager"
            ):
                raise AccessError(_("Only the assigned user can edit count lines."))
        return super().write(vals)

    @api.depends("product_id", "location_id")
    def _compute_on_hand_qty(self):
        Quant = self.env["stock.quant"].sudo()
        quantity_cache = {}
        for rec in self.with_context(ff_inventory_count_compute=True):
            if not rec.product_id or not rec.location_id:
                rec.on_hand_qty = 0.0
                continue
            cache_key = (rec.product_id.id, rec.location_id.id, rec.company_id.id)
            if cache_key not in quantity_cache:
                quantity_cache[cache_key] = sum(Quant.search([
                    ("product_id", "=", rec.product_id.id),
                    ("location_id", "child_of", rec.location_id.id),
                    ("company_id", "=", rec.company_id.id),
                ]).mapped("quantity"))
            rec.on_hand_qty = quantity_cache[cache_key]

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id and self.product_id.barcode:
            self.barcode_reference = self.product_id.barcode

    @api.constrains("counted_qty")
    def _check_qty(self):
        for rec in self:
            if rec.counted_qty < 0:
                raise ValidationError(_("Counted quantity cannot be negative."))

    @api.onchange("barcode_reference")
    def _onchange_barcode_reference(self):
        if self.barcode_reference:
            product = self.env["product.product"].search([("barcode", "=", self.barcode_reference)], limit=1)
            if not product:
                raise UserError(_("No product was found for barcode %s.") % self.barcode_reference)
            self.product_id = product

    def unlink(self):
        for rec in self:
            if rec.sheet_id.state != "draft" or rec.sheet_id.session_id.state != "draft":
                raise UserError(_("Counted lines cannot be deleted after counting has started."))
        return super().unlink()


class InventoryCountConsolidatedLine(models.Model):
    _name = "ff.inventory.count.consolidated.line"
    _description = "Consolidated Inventory Count Result"
    _check_company_auto = True

    session_id = fields.Many2one("ff.inventory.count.session", required=True, ondelete="cascade", check_company=True)
    company_id = fields.Many2one(related="session_id.company_id", store=True)
    product_id = fields.Many2one("product.product", required=True, check_company=True)
    location_id = fields.Many2one("stock.location", required=True, check_company=True)
    lot_id = fields.Many2one("stock.lot", check_company=True)
    package_id = fields.Many2one("stock.package", check_company=True)
    owner_id = fields.Many2one("res.partner", check_company=True)
    product_uom_id = fields.Many2one("uom.uom", required=True)
    theoretical_qty = fields.Float(digits="Product Unit of Measure", readonly=True)
    counted_qty = fields.Float(digits="Product Unit of Measure", readonly=True)
    variance_qty = fields.Float(compute="_compute_variance", store=True, digits="Product Unit of Measure")
    variance_value = fields.Monetary(compute="_compute_variance", store=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)
    count_source_line_ids = fields.Many2many(
        "ff.inventory.count.line", "ff_count_consolidated_source_rel",
        "consolidated_line_id", "count_line_id",
        string="Source Count Lines", readonly=True,
    )
    reconciliation_status = fields.Selection([("pending", "Pending"), ("ignore", "Ignore"), ("adjust", "Adjust")],
                                             default="pending", required=True)
    variance_reason = fields.Selection([
        ("opening", "Opening Inventory"),
        ("damage", "Damaged Products"),
        ("employee_loss", "Employee Loss"),
        ("cogs", "Recognize Cost of Goods Sold"),
    ], string="Variance Reason")
    applied = fields.Boolean(readonly=True, copy=False)
    account_move_id = fields.Many2one("account.move", readonly=True, copy=False)

    @api.depends("theoretical_qty", "counted_qty", "product_id", "product_id.standard_price")
    def _compute_variance(self):
        for rec in self:
            rec.variance_qty = rec.counted_qty - rec.theoretical_qty
            rec.variance_value = rec.variance_qty * rec.product_id.standard_price

    def apply_adjustment(self):
        self.ensure_one()
        if self.applied or self.reconciliation_status != "adjust":
            return
        if not self.variance_reason:
            raise ValidationError(_("Select a reason before applying an inventory variance."))
        company = self.company_id
        account_by_reason = {
            "opening": company.inventory_count_opening_account_id,
            "damage": company.inventory_count_damage_account_id,
            "employee_loss": company.inventory_count_employee_loss_account_id,
            "cogs": company.inventory_count_cogs_account_id,
        }
        reason_account = account_by_reason.get(self.variance_reason)
        category = self.product_id.categ_id.with_company(company)
        valuation_account = category.property_stock_valuation_account_id
        journal = company.inventory_count_journal_id
        amount = abs(self.variance_value)
        if not journal or not reason_account or not valuation_account:
            raise ValidationError(
                _("Configure the inventory count journal, variance account, and product stock valuation account before applying the adjustment.")
            )
        if not amount:
            raise ValidationError(
                _("The inventory variance has no accounting value because the product cost is zero.")
            )
        Quant = self.env["stock.quant"].with_context(
            inventory_mode=True, ff_smart_inventory_count_apply=True
        )
        quant = Quant._gather(self.product_id, self.location_id, lot_id=self.lot_id, package_id=self.package_id,
                              owner_id=self.owner_id, strict=True)
        if not quant:
            quant = Quant.create({"product_id": self.product_id.id, "location_id": self.location_id.id,
                                  "lot_id": self.lot_id.id or False, "package_id": self.package_id.id or False,
                                  "owner_id": self.owner_id.id or False})
        automated_valuation = (
            "property_valuation" in category._fields
            and category.property_valuation == "real_time"
        )
        inventory_loss_account = False
        if automated_valuation and "property_stock_inventory" in self.product_id._fields:
            inventory_location = self.product_id.with_company(company).property_stock_inventory
            inventory_loss_account = (
                inventory_location.valuation_account_id
                if inventory_location and "valuation_account_id" in inventory_location._fields
                else False
            )
            if not inventory_loss_account:
                raise ValidationError(
                    _("Configure the inventory loss account on the Inventory Adjustments location before applying an automated-valuation variance.")
                )
            if "accounting_date" in quant._fields:
                quant.accounting_date = self.session_id.scheduled_date
        quant.inventory_quantity = self.counted_qty
        quant.action_apply_inventory()
        if automated_valuation:
            # stock_account has already posted the valuation move. Reclassify
            # only the inventory-loss side to the selected business reason;
            # never post a second valuation-to-reason move.
            debit_account, credit_account = (
                (inventory_loss_account, reason_account)
                if self.variance_qty > 0
                else (reason_account, inventory_loss_account)
            )
        else:
            debit_account, credit_account = (
                (valuation_account, reason_account)
                if self.variance_qty > 0
                else (reason_account, valuation_account)
            )
        move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": journal.id,
            "date": self.session_id.scheduled_date,
            "ref": _("Inventory Count %s - %s") % (self.session_id.name, self.product_id.display_name),
            "line_ids": [
                (0, 0, {"name": self.product_id.display_name, "account_id": debit_account.id, "debit": amount, "credit": 0.0}),
                (0, 0, {"name": self.product_id.display_name, "account_id": credit_account.id, "debit": 0.0, "credit": amount}),
            ],
        })
        move.action_post()
        self.write({"applied": True, "account_move_id": move.id})

    def write(self, vals):
        manager = self.env.user.has_group("ff_smart_inventory_count.group_count_manager") or self.env.is_superuser()
        protected = {"session_id", "company_id", "product_id", "location_id", "lot_id", "package_id",
                     "owner_id", "product_uom_id", "theoretical_qty", "counted_qty", "variance_qty",
                     "variance_value", "currency_id", "count_source_line_ids", "applied", "account_move_id"}
        generated_fields = protected - {"applied", "account_move_id"}
        if generated_fields.intersection(vals):
            raise AccessError(_("Consolidated inventory results are system-generated and cannot be edited."))
        for rec in self:
            if rec.applied:
                raise UserError(_("An applied inventory result cannot be changed."))
            if not manager and not self.env.is_superuser():
                raise AccessError(_("Only an inventory supervisor can review inventory variances."))
            if rec.session_id.state not in ("under_review", "approved") and not manager and not (
                self.env.context.get("ff_inventory_count_workflow")
                and set(vals) <= {"variance_reason"}
            ) and not (set(vals) <= {"applied", "account_move_id"}):
                raise UserError(_("Variance reasons can only be changed during review."))
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.session_id.state in ("approved", "done") or rec.applied:
                raise UserError(_("Approved inventory results cannot be deleted."))
        return super().unlink()
