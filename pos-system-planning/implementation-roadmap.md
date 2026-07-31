# Implementation roadmap

## Phase 0: Foundation

Build this first.

- Multi-tenant backend structure.
- Roles: super admin, store admin, cashier.
- Feature flag model controlled by super admin.
- Store, register, device registration.
- Login, permission checks, and audit logs.
- Local database in POS client.
- Outbox sync engine.
- Signed license/feature snapshot.

Deliverable:

- A cashier device can log in, cache settings, go offline, and later sync a test operation.

## Phase 1: Core POS billing

- Product/category setup.
- Barcode scan/search.
- Retail, wholesale, and lot pricing.
- Cart and checkout.
- Cash/card/split payments.
- Receipt number generation.
- Receipt printing integration.
- Sales stored locally first.
- Sales sync exactly once.
- Shift open with startup cash.
- Shift close with counted cash and variance.
- Cashier dashboard.
- Keyboard shortcuts.

Deliverable:

- A shop can bill customers all day even if internet fails.

## Phase 2: Inventory

- Stock movements ledger.
- Inventory balances.
- Low-stock alerts.
- Zero-stock view.
- Reorder level.
- Inventory browse table.
- Product history timeline.
- Admin password/permission for adjustment.
- Adjustment history.
- Damage table.
- Doubtful stock table.

Deliverable:

- Admin can track how every product came in, sold, adjusted, damaged, or moved.

## Phase 3: Suppliers and purchases

- Supplier profiles.
- Supplier product links.
- Goods receiving.
- Purchase records.
- Supplier payments.
- Outstanding payment tracking.
- Supplier visit/reorder view.
- Purchases by year report.

Deliverable:

- Admin can see what a supplier supplied last time, what remains, what sold, and what should be reordered.

## Phase 4: Reports and dashboards

- Daily sales dashboard.
- Sales by cashier/register/product/category.
- Payment method breakdown.
- Best salesperson.
- Best-selling products by quantity and revenue.
- Inventory value and estimated profit.
- Supplier outstanding balances.
- Purchase and sales yearly charts.
- Worker performance charts.

Deliverable:

- Store admin can validate daily operation and see business performance.

## Phase 5: Advanced modules

Build only when the core is stable.

- Loyalty.
- Multi-branch.
- Customer accounts/credit.
- Barcode label printing.
- Accounting export.
- Advanced permissions.
- Cloud support dashboard for your company.

## Suggested MVP scope

For the first usable version, keep the MVP tight:

- Super admin tenant setup and feature toggles.
- Store admin product/category setup.
- Cashier billing with offline local database.
- Shift opening and closing.
- Basic inventory stock movement from sales.
- Sync when online.
- Daily sales and cashier summary reports.

Add suppliers, damage/doubtful stock, and advanced reports after the first stable billing release.

## Major engineering risks

Offline sync:

- Highest-risk area. Must be designed before building screens.

Receipt printing:

- Browser printing may be enough for simple shops, but USB thermal printers and cash drawers often need a desktop wrapper or local print agent.

Inventory truth:

- Avoid direct quantity editing. Use stock movements, then calculate balances.

Feature disabling:

- Must be enforced in backend and frontend.

Tax and legal receipts:

- Country-specific tax rules, invoice numbering, and fiscal device laws must be confirmed before production.

## Build order by screens

1. Super admin: shops, plans, feature toggles.
2. Store admin: users/cashiers.
3. Store admin: categories/products.
4. Cashier: shift open.
5. Cashier: billing screen.
6. Cashier: receipt print.
7. Cashier: shift close.
8. Store admin: daily validation dashboard.
9. Store admin: inventory browse and adjustments.
10. Store admin: suppliers and purchases.
11. Store admin: reports.

## Non-negotiable technical rules

- Use decimal-safe money storage.
- Every sale has a cashier, register, shift, and receipt number.
- Every stock change has a stock movement.
- Every sensitive action has an audit log.
- Every offline operation has a unique operation id.
- Sync operations must be idempotent.
- Never delete financial records after sync.
- Use corrections, voids, refunds, and adjustments instead.

