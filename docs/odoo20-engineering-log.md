# Odoo 20 Engineering Log

## 2026-11-25 — Reserved quantity in Stock report

- Module: `ff_smart_inventory_count`, version `20.0.1.0.36`.
- Finding: the standard Odoo 20 Stock report shows `qty_available` and `free_qty`; it has no reserved quantity column. Odoo defines free quantity as on-hand less reserved.
- Change: added a non-stored `product.product.reserved_qty` computed from the standard quantities and inherited `stock.product_product_stock_tree` to add a visible, optional column and total.
- Context: the computed field follows the stock quantity context dependencies for location, warehouse, dates, lot, package, owner, company, and storable state.
- Safety: no quant, move, reservation, or inventory record is created or changed; Odoo core remains untouched.
- Verification/deployment: upgraded training database `al_yamen_test` successfully; module reports `20.0.1.0.36` and `installed`; the Arabic Stock report UI shows the new `الكمية المحجوزة` column between free quantity and unit cost.
- Reservation proof: created standard outgoing picking `مدينه - التام/OUT/00002` for 3 units of product `921001`; it remains in Assigned state and has not been validated. The report displays On Hand `496`, Free to Use `493`, Reserved `3`; the source-location quant reports `500` on hand and `3` reserved. This test reservation remains open in training so the user can inspect it.
- Backup: database and matching filestore were saved under `/var/backups/odoo/stock_report_reserved_qty_20261125/` before upgrade.
- Scope: production database `al_yamen` was not changed.
