# Odoo 20 Engineering Log

## 2026-11-25 — Reserved quantity in Stock report

- Module: `ff_smart_inventory_count`, version `20.0.1.0.36`.
- Finding: the standard Odoo 20 Stock report shows `qty_available` and `free_qty`; it has no reserved quantity column. Odoo defines free quantity as on-hand less reserved.
- Change: added a non-stored `product.product.reserved_qty` computed from the standard quantities and inherited `stock.product_product_stock_tree` to add a visible, optional column and total.
- Context: the computed field follows the stock quantity context dependencies for location, warehouse, dates, lot, package, owner, company, and storable state.
- Safety: no quant, move, reservation, or inventory record is created or changed; Odoo core remains untouched.
- Verification/deployment: upgraded training database `al_yamen_test` successfully; module reports `20.0.1.0.36` and `installed`; HTTP responds on the training service; the Arabic Stock report UI shows the new `الكمية المحجوزة` column between free quantity and unit cost. The visible sample rows have zero reserved because on-hand equals free quantity. No reservation or stock transaction was created for this UI smoke check.
- Backup: database and matching filestore were saved under `/var/backups/odoo/stock_report_reserved_qty_20261125/` before upgrade.
- Scope: production database `al_yamen` was not changed.
