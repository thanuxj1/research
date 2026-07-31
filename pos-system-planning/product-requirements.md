# Product requirements

## 1. Goals

Build an online POS platform that is offline-first for daily shop operations.

The system must support:

- Super admin control over shops, subscription plans, and feature access.
- Store admin control over products, categories, suppliers, inventory, staff, cashiers, reports, and validation.
- Cashier workflow for fast billing, startup cash, receipt printing, payment tracking, shift closing, and keyboard shortcuts.
- Inventory tracking from supplier purchase to sale, damage, adjustment, reorder, and reporting.
- Sync when internet returns without losing sales or stock history.

## 2. Roles

### Super admin

This is your company, the POS provider.

Capabilities:

- Create and manage shops/tenants.
- Create store admin accounts.
- Enable or disable paid features per shop.
- Manage plan limits such as number of users, registers, branches, products, reports, loyalty, inventory, supplier module, and advanced analytics.
- Suspend or reactivate a shop.
- View high-level usage, billing status, device sync health, and support diagnostics.
- Push settings or feature changes to shops.

Important rule:

- Feature access should be controlled by signed feature flags.
- Offline shops continue with the last valid feature snapshot for a defined grace period, for example 7 to 30 days.

### Store admin

This is the shop owner or manager.

Capabilities:

- Add, edit, disable cashiers.
- See who is currently logged in and working.
- Manage cashier permissions.
- Add products manually, by barcode scan, or by CSV import.
- Add categories and unlimited nested subcategories.
- Assign every product to one category and optionally to subcategories.
- Add suppliers.
- Track supplier products, supplied quantities, supplied dates, payments, outstanding balances, and purchase history.
- See what each supplier supplied last time, how many were sold, how many remain, and what should be reordered.
- Browse inventory by item id, barcode, description, serial number, quantity, cost price, selling price, category, supplier, and stock status.
- Adjust stock only with admin password or elevated permission.
- View stock value, selling value, estimated profit, low-stock items, zero-stock items, reorder levels, damaged stock, doubtful stock, and adjustment history.
- View cashier activity, daily sales, payment method breakdowns, shift validation, and mismatch between counted cash and expected cash.
- View reports, rankings, charts, and performance dashboards.

### Cashier

Capabilities:

- Log in to assigned register/device.
- Add startup cash before sales begin.
- Scan barcode or search items.
- Use retail, wholesale, lot/bulk, or custom allowed price tiers.
- Apply allowed discounts or price changes only if permission allows.
- Accept cash, card, split payment, and other configured payment methods.
- Print receipts.
- Continue billing offline.
- See own shift dashboard.
- End shift by entering actual drawer cash.
- See expected cash, card totals, total sales, refunds, and variance.
- Request admin override from cashier screen when needed.

## 3. Feature modules controlled by super admin

Every module should be controlled by feature flags:

- Core POS billing
- Offline sync
- Inventory management
- Supplier management
- Purchase orders and goods receiving
- Damaged stock
- Doubtful stock
- Inventory adjustments
- Advanced reports
- Loyalty
- Multi-register
- Multi-branch
- CSV import/export
- Barcode labels
- User activity audit
- Cash drawer validation
- Low-stock alerts
- Accounting export

Example:

- A shop pays for only billing and basic inventory.
- Super admin disables loyalty and advanced reports.
- The UI hides disabled modules and the API rejects disabled module actions.

## 4. Product and category requirements

Products:

- Item id/SKU
- Barcode
- Product name
- Description
- Brand
- Category
- Optional subcategory path
- Supplier links
- Unit of measure
- Serial number support where needed
- Cost price
- Retail selling price
- Wholesale selling price
- Lot/bulk selling price, for example price when quantity is 12 or more
- Tax setting
- Reorder level
- Low-stock threshold
- Active/inactive status
- Image optional

Categories:

- Admin can create categories manually.
- Admin can create subcategories to any reasonable depth.
- Admin can import categories and subcategories by CSV.
- Products must have a category.
- Product subcategory is optional but must belong under the selected category.

Pricing:

- Retail price for normal sale.
- Wholesale price when customer buys configured quantity or customer type allows it.
- Lot/bulk price for carton/dozen/pack rules.
- Price override only with permission.
- All price changes must be audited.

Barcode:

- Admin can scan barcode while adding product.
- Cashier can scan barcode while billing.
- Duplicate barcode validation is required inside one shop unless variant behavior is enabled.

## 5. Supplier and purchasing requirements

Supplier profile:

- Supplier name
- Contact person
- Phone/email/address
- Payment terms
- Notes
- Active/inactive status

Supplier product link:

- Supplier
- Product
- Supplier item code
- Last cost price
- Last supplied quantity
- Last supplied date
- Minimum order quantity

Goods receiving:

- Admin creates purchase/goods receiving record.
- Each line increases stock through a stock movement.
- Purchase can be paid, partially paid, or unpaid.
- Outstanding supplier balance is tracked.
- Supplier visit view shows:
  - What was supplied last time
  - Quantity received last time
  - Current quantity left
  - Quantity sold since last supply
  - Suggested reorder quantity
  - Outstanding payment

## 6. Inventory requirements

Inventory must be ledger-based. Do not only store a quantity number.

Stock movement types:

- Purchase receive
- Sale
- Sale return
- Damage
- Doubtful stock
- Adjustment increase
- Adjustment decrease
- Transfer between locations/registers, if multi-location is enabled

Views:

- Browse inventory
- Inventory summary by category
- Inventory summary by supplier
- Zero-stock inventory
- Low-stock inventory
- Reorder list
- Damaged stock table
- Doubtful stock table
- Adjustment history
- Product history timeline

Inventory browse columns:

- Item id
- Barcode
- Description/name
- Serial number if applicable
- Quantity
- Cost price
- Selling price
- Category
- Supplier
- Stock value
- Selling value
- Estimated margin

Adjustment rules:

- Quantity adjustment requires admin password or permission.
- Reason is mandatory.
- Before and after quantities are stored.
- Adjustment cannot be deleted.
- Every adjustment creates an audit log entry.

## 7. Cashier shift requirements

Start shift:

- Cashier logs in.
- Cashier selects or is assigned to a register/machine.
- Cashier enters startup cash.
- System prints or stores opening cash receipt if configured.

During shift:

- All sales are linked to cashier, register, and shift.
- Payments are separated by method: cash, card, bank transfer, wallet, voucher, etc.
- Voids, refunds, discounts, and price overrides require permissions.
- Offline status is clearly shown.
- Keyboard shortcuts are available for fast billing.

End shift:

- Cashier enters actual drawer cash.
- System calculates expected cash:
  - Startup cash
  - Cash sales
  - Cash refunds
  - Cash paid in/out
- System shows variance.
- Admin login/override can approve shift closing.
- Shift close summary can be printed.

Admin validation:

- Admin can compare cashier counted cash with system expected cash.
- Admin can see sales by cashier, payment method, register, and shift.
- Admin can see who is currently logged in.

## 8. Reporting requirements

Reports:

- Sales today
- Sales by cashier
- Sales by register/machine
- Sales by category
- Sales by product
- Sales by supplier
- Sales by year
- Purchases by year
- Best-selling item by quantity
- Best-selling item by revenue
- Best salesperson
- Cashier performance
- Worker activity
- Inventory value
- Selling value
- Estimated profit margin
- Low stock
- Zero stock
- Reorder list
- Damage report
- Doubtful stock report
- Supplier outstanding payments
- Supplier purchase history
- Adjustment history

Charts:

- Daily sales trend
- Yearly sales
- Yearly purchases
- Category sales
- Best products ranking
- Cashier ranking
- Payment method split
- Inventory value by category

## 9. Audit and validation

Audit log must record:

- Who performed the action
- Role
- Device/register
- Timestamp
- Online/offline creation status
- Entity changed
- Old value where practical
- New value where practical
- Reason for sensitive actions

Sensitive audited actions:

- Product price changes
- Stock adjustments
- Damage/doubt movements
- Refunds
- Voids
- Discounts above limit
- Cash drawer open
- Shift close approval
- Supplier payment changes
- Feature flag changes

## 10. Acceptance criteria

Offline billing:

- Cashier can complete a sale without internet.
- Receipt can be printed while offline if the printer is locally available.
- Stock decreases locally immediately.
- Shift totals update locally immediately.
- Sale is queued for sync.
- When internet returns, sale syncs once and only once.

Feature control:

- Super admin can disable inventory reports for a shop.
- Store admin and cashiers cannot access disabled reports.
- API rejects disabled feature actions.
- Offline device uses last valid signed feature snapshot.

Inventory:

- Every product quantity change has a stock movement.
- Admin can see product history from purchase to sale or damage.
- Low-stock and zero-stock views update after sale or adjustment.

Cashier validation:

- Cashier enters startup cash.
- Cashier enters counted cash at shift end.
- System calculates expected cash and variance.
- Admin can approve or reject variance.

