Flous Flow Smart Inventory Count
================================

This Odoo 20 Community module provides controlled physical inventory counting
with location-based assignments, employee count sheets, supervisor review, and
approved inventory adjustments.

Workflow
--------

1. Create a count session, select the warehouse, and choose either selected
   locations or the whole warehouse.
2. Select one counting user for a quick first-count setup, or assign each
   internal location to one or more counting users manually.
3. Start the session; Odoo creates one sheet per assignment.
4. Count products manually or import count lines while a sheet is in Counting.
5. Submit sheets and consolidate the submitted results.
6. Select a reason for every non-zero variance and approve it.
7. The module posts the configured journal entry and applies the quantity
   through Odoo's inventory adjustment engine.

Set a default variance reason on the session to fill only lines without a
reason. A line with a manually selected reason is preserved.

Accounting setup
----------------

Configure the inventory count journal and the variance accounts in
Inventory ‣ Configuration ‣ Settings. Each product category included in an
adjustment must have a Stock Valuation Account. The module does not silently
post an adjustment when this configuration is incomplete.

Security
--------

Counting users can work only on sheets assigned to them. Supervisors control
session assignments, consolidation, approval, and accounting application.
Manual inventory quantity adjustments are blocked outside the approved Smart
Inventory Count workflow.
