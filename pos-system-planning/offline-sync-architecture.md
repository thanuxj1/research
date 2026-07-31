# Offline sync architecture

## 1. Recommended architecture

Use a local-first client and a cloud backend.

Recommended stack:

- Frontend POS app: React or Vue PWA.
- Local database: IndexedDB using Dexie/RxDB for browser PWA, or SQLite if using Electron/Tauri desktop app.
- Optional desktop wrapper: Electron or Tauri for USB receipt printer, cash drawer, and barcode scanner support.
- Backend API: Node.js/NestJS, Laravel, Django, or FastAPI. Pick the stack your team can maintain.
- Cloud database: PostgreSQL.
- Background jobs: sync processing, reports, notifications.
- Cache/queue: Redis if needed.

For serious retail hardware, a desktop wrapper or small local device service is recommended, because browser printer and cash drawer access can be limited.

## 2. Local-first rule

The cashier app writes first to the local database.

For example, when a sale is completed:

1. Create sale locally.
2. Create sale items locally.
3. Create payment records locally.
4. Create stock movement records locally.
5. Update local read models for fast UI.
6. Add sync operation to local outbox.
7. Print receipt.
8. Sync later when internet is available.

This prevents billing from stopping during internet loss.

## 3. Sync model

Use an outbox/inbox pattern.

Local tables:

- `outbox_operations`: unsynced local changes waiting to upload.
- `sync_cursors`: last server version downloaded per entity/table.
- `sync_conflicts`: conflicts requiring admin/super admin review.
- `device_state`: device id, register id, last sync time, license snapshot.

Server tables:

- Main business tables.
- `sync_operations`: accepted client operations for idempotency.
- `entity_versions`: monotonically increasing server version per changed row.
- `audit_logs`: immutable action history.

Each offline operation must have:

- Globally unique operation id.
- Tenant/shop id.
- Device id.
- Register id where relevant.
- User id.
- Local created timestamp.
- Operation type.
- Payload.
- Idempotency key.

## 4. Id generation

Use UUID/ULID ids generated on the client for offline-created records.

Examples:

- Sale id generated before internet exists.
- Payment id generated locally.
- Stock movement id generated locally.

The server accepts the client-generated id after validation. This avoids replacing ids after sync.

## 5. Sale number design

Receipt numbers should be unique while offline.

Recommended format:

`SHOPCODE-REGISTERNO-YYYYMMDD-LOCAL_SEQUENCE`

Example:

`ABC-R02-20260610-000143`

When synced, the server can also assign a server invoice number if needed, but the original receipt number must remain searchable.

## 6. Conflict strategy

Sales and stock movements should be append-only.

That means they usually do not conflict. Instead of editing old sales or stock records:

- Refund creates a new refund record.
- Stock adjustment creates a new movement.
- Damage creates a new movement.
- Supplier correction creates an adjustment or correction record.

Conflict-prone data:

- Product name changed on two devices.
- Selling price changed while another device sold offline.
- Category edited on two devices.
- Supplier details edited on two devices.

Recommended conflict rules:

- For sales, keep the price used at sale time. Do not recalculate old offline sales after sync.
- For product master fields, use last server write unless conflict detection is enabled.
- For stock quantity, never sync absolute quantity. Sync stock movements only.
- For sensitive conflicts, send to `sync_conflicts` for admin review.

## 7. Stock consistency

Do not sync product quantity as a simple editable field.

Use:

- `stock_movements` as the source of truth.
- `inventory_balances` as a calculated/read model.

When a device is offline:

- It subtracts stock locally after each sale.
- It can show a warning if stock is low.
- It may allow overselling if the shop setting allows it.
- Server reconciles stock movements after sync.

Recommended setting:

- Grocery/retail shops may allow offline oversell with warning.
- Serialized or high-value items should block sale if local stock is zero.

## 8. Feature flag and subscription sync

Super admin controls features from the cloud.

The device stores a signed feature snapshot:

- Tenant id
- Enabled features
- Plan limits
- Issued at
- Expires at
- Grace period
- Signature

Offline behavior:

- If the snapshot is valid, continue allowing enabled features.
- If internet is down after expiry, allow only during grace period.
- After grace period, restrict to essential billing and sync only, depending on business policy.

Never rely only on frontend hiding. The backend must also check feature access.

## 9. Security

Authentication:

- Users log in online to obtain tokens and local offline session permission.
- Cashiers can continue within an offline session based on shop policy.
- Admin override offline should require cached admin PIN/password hash.

Local data protection:

- Encrypt local database where possible.
- Store password/PIN hashes, not raw passwords.
- Do not store full card data.
- Use HTTPS for all sync.

Auditing:

- Every synced operation includes user, device, and shift context.
- Sensitive actions require reason and permission.

## 10. Sync lifecycle

Startup:

1. Load local database.
2. Load last feature snapshot.
3. Load current register/device assignment.
4. Check internet.
5. If online, refresh settings, products, prices, users, and feature flags.
6. If offline, continue with cached data.

During work:

1. All writes go local first.
2. Outbox stores operations.
3. UI shows sync status and pending operation count.

When internet returns:

1. Upload outbox operations in order.
2. Server validates tenant, feature, permission, idempotency, and schema.
3. Server stores operations and applies changes.
4. Client downloads newer server changes.
5. Client marks uploaded operations as synced.
6. Conflicts are shown to admin.

## 11. Critical safeguards

- Each operation must be idempotent.
- Sale sync must be exactly-once from business perspective.
- No deleting synced financial records.
- Voids/refunds/adjustments are new records.
- All money values stored as decimal/cents, never floating point.
- Device clock differences should not decide financial truth. Server received time is stored separately.
- Local receipt number and server invoice number should both be searchable.

