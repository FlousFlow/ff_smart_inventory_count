# Flous Flow Smart Inventory Count

Odoo 20 Community addon for controlled physical inventory counting. It keeps
counting separate from Odoo stock until a supervisor approves a consolidated
result, then uses the standard `stock.quant` inventory adjustment engine.

The addon depends on `stock_account` so automated stock valuation moves remain
consistent with the selected inventory-variance reason accounts.

The module intentionally does not zero uncounted products: only products
actually submitted by counting sheets are consolidated and adjusted.

## Operating policy

- Odoo's standard Physical Inventory menu is hidden when this addon is
  installed. Manual `stock.quant` inventory adjustments are rejected unless
  they carry the controlled Smart Inventory Count approval context.
- Count sheets are generated from sessions; standalone sheets are blocked.
- For a first count, select the warehouse, choose **Selected Locations** or
  **Whole Warehouse**, and select one counting user. With one user selected,
  the module automatically creates the location assignments and count sheets.
- Arabic translations are included for the Smart Inventory Count interface.
- While a sheet is in Counting state, use **Import Lines** to import a CSV/XLSX
  file with `Product` and `Counted Qty` columns. The selected sheet and count
  location are supplied automatically.
- For each session, assign every location to one or more counting users. A
  separate sheet is generated for every user/location assignment.
- Configure the inventory count journal and the variance accounts from
  Inventory → Configuration → Settings before approving variances. Each
  product category used in a count must also have a Stock Valuation Account.
- Consolidation displays non-zero variances for review. The supervisor selects
  Damaged Products, Employee Loss, or Recognize Cost of Goods Sold; approval
  posts the configured journal entry and applies the stock quantity.
- Set **Default Variance Reason** on the session to fill all unassigned
  variance lines. Any line with a manually selected reason is preserved.

## Permissions

- Smart Count User: can access and work only on sheets assigned to that user.
- Smart Count Supervisor: can create sessions, assign locations/users,
  consolidate, approve, apply adjustments, and close sessions.

## Testing

The addon includes Odoo 20 transaction tests for assignment coverage, sheet and
line lifecycle rules, deletion protection, and accounting move creation. Run
the focused suite on a disposable database with:

```bash
odoo-bin -d <disposable_db> -u ff_smart_inventory_count \
  --test-enable --test-tags /ff_smart_inventory_count --stop-after-init
```

Physical barcode hardware, production load, and Odoo Apps review are not
covered by the local automated suite.

Normal receipts, deliveries, transfers, and other stock movements remain
available. The restriction applies to manual quantity adjustments only.
