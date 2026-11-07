Flous Flow Smart Inventory Count
================================

This Odoo 20 Community module provides controlled physical inventory counting
with location-based assignments, employee count sheets, supervisor review, and
approved inventory adjustments.

Workflow
--------

1. Create a count session and select the warehouse.
2. Assign each internal location to one or more counting users.
3. Start the session; Odoo creates one sheet per assignment.
4. Count products manually or import count lines while a sheet is in Counting.
5. Submit sheets and consolidate the submitted results.
6. Select a reason for every non-zero variance and approve it.
7. The module posts the configured journal entry and applies the quantity
   through Odoo's inventory adjustment engine.

Accounting setup
----------------

Configure the inventory count journal and the three variance accounts in
Inventory ‣ Configuration ‣ Settings. Each product category included in an
adjustment must have a Stock Valuation Account. The module does not silently
post an adjustment when this configuration is incomplete.

Security
--------

Counting users can work only on sheets assigned to them. Supervisors control
session assignments, consolidation, approval, and accounting application.
Manual inventory quantity adjustments are blocked outside the approved Smart
Inventory Count workflow.
