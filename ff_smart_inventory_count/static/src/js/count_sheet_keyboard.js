/** @odoo-module */

// Keep the counting workflow fast without changing Odoo's list navigation globally.
document.addEventListener(
    "keydown",
    (event) => {
        if (event.key !== "Enter" || event.isComposing) {
            return;
        }
        const productInput = event.target.closest(
            ".o_ff_inventory_count_lines td[name='product_id'] input"
        );
        if (!productInput) {
            return;
        }

        // Let Enter choose an open autocomplete suggestion first. A second Enter
        // after the product is selected moves to the counted quantity field.
        const openAutocomplete = document.querySelector(
            ".o-autocomplete--dropdown-menu:not(.d-none)"
        );
        if (openAutocomplete) {
            return;
        }

        const row = productInput.closest("tr");
        const countedInput = row?.querySelector(
            "td[name='counted_qty'] input"
        );
        if (!countedInput) {
            return;
        }

        event.preventDefault();
        event.stopImmediatePropagation();
        window.setTimeout(() => {
            countedInput.focus();
            countedInput.select?.();
        }, 0);
    },
    true
);
