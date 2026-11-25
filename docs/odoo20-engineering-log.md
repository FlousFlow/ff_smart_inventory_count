# Odoo 20 Engineering Log

## 2026-11-25 — Reserved quantity in Stock report

- Module: `ff_smart_inventory_count`, version `20.0.1.0.36`.
- Finding: the standard Odoo 20 Stock report shows `qty_available` and `free_qty`; it has no reserved quantity column. Odoo defines free quantity as on-hand less reserved.
- Change: added a non-stored `product.product.reserved_qty` computed from the standard quantities and inherited `stock.product_product_stock_tree` to add a visible, optional column and total.
- Context: the computed field follows the stock quantity context dependencies for location, warehouse, dates, lot, package, owner, company, and storable state.
- Safety: no quant, move, reservation, or inventory record is created or changed; Odoo core remains untouched.
- Verification/deployment: pending training database upgrade and UI smoke check.
