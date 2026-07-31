const STORAGE_KEY = "offline_pos_mvp_state_v1";

const starterState = {
  online: navigator.onLine,
  currentRole: "cashier",
  activeView: "pos",
  activeShiftId: null,
  register: "R01",
  features: {
    corePos: true,
    inventory: true,
    suppliers: true,
    reports: true,
    loyalty: false,
    advancedAnalytics: false,
  },
  users: [
    { id: "u-admin", name: "Store Admin", role: "admin", active: true },
    { id: "u-cashier", name: "Cashier One", role: "cashier", active: true },
  ],
  categories: [
    { id: "cat-soap", name: "Soap", parentId: null },
    { id: "cat-food", name: "Food", parentId: null },
    { id: "cat-drinks", name: "Drinks", parentId: null },
  ],
  products: [
    {
      id: "p-1001",
      itemId: "1001",
      barcode: "479100100001",
      name: "Herbal Soap 100g",
      brand: "FreshCo",
      categoryId: "cat-soap",
      supplierId: "s-1",
      stock: 34,
      cost: 90,
      retail: 140,
      wholesale: 125,
      lotPrice: 118,
      lotMinQty: 12,
      reorderLevel: 10,
    },
    {
      id: "p-1002",
      itemId: "1002",
      barcode: "479100100002",
      name: "Rice 5kg",
      brand: "Golden Grain",
      categoryId: "cat-food",
      supplierId: "s-2",
      stock: 9,
      cost: 1450,
      retail: 1690,
      wholesale: 1620,
      lotPrice: 1580,
      lotMinQty: 6,
      reorderLevel: 12,
    },
    {
      id: "p-1003",
      itemId: "1003",
      barcode: "479100100003",
      name: "Orange Drink 1L",
      brand: "SunSip",
      categoryId: "cat-drinks",
      supplierId: "s-1",
      stock: 48,
      cost: 210,
      retail: 290,
      wholesale: 270,
      lotPrice: 255,
      lotMinQty: 12,
      reorderLevel: 18,
    },
  ],
  suppliers: [
    { id: "s-1", name: "Lanka FMCG Supply", phone: "0771234567", outstanding: 18500 },
    { id: "s-2", name: "Golden Wholesale", phone: "0719876543", outstanding: 42000 },
  ],
  shifts: [],
  sales: [],
  stockMovements: [],
  supplierPurchases: [],
  outbox: [],
  cart: [],
  lastReceiptSeq: 0,
};

let state = loadState();

function loadState() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return structuredClone(starterState);
  return { ...structuredClone(starterState), ...JSON.parse(raw) };
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function money(value) {
  return `Rs. ${Number(value || 0).toLocaleString("en-LK", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function id(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function roleCan(view) {
  if (state.currentRole === "superAdmin") return true;
  if (state.currentRole === "admin") return view !== "super";
  return ["pos", "shift"].includes(view);
}

function featureEnabled(key) {
  return Boolean(state.features[key]);
}

function queueOperation(type, payload) {
  state.outbox.push({
    id: id("op"),
    type,
    payload,
    status: "pending",
    createdAt: new Date().toISOString(),
  });
}

function syncNow() {
  if (!state.online) return;
  state.outbox = state.outbox.map((op) => ({
    ...op,
    status: "synced",
    syncedAt: new Date().toISOString(),
  }));
  saveState();
  render();
}

function activeShift() {
  return state.shifts.find((shift) => shift.id === state.activeShiftId && shift.status === "open");
}

function categoryName(categoryId) {
  return state.categories.find((category) => category.id === categoryId)?.name || "Uncategorized";
}

function supplierName(supplierId) {
  return state.suppliers.find((supplier) => supplier.id === supplierId)?.name || "No supplier";
}

function currentPrice(product, qty) {
  if (qty >= product.lotMinQty) return product.lotPrice;
  if (qty >= 6) return product.wholesale;
  return product.retail;
}

function setView(view) {
  if (!roleCan(view)) return;
  state.activeView = view;
  saveState();
  render();
}

function setRole(role) {
  state.currentRole = role;
  if (!roleCan(state.activeView)) state.activeView = "pos";
  saveState();
  render();
}

function toggleOnline() {
  state.online = !state.online;
  if (state.online) syncNow();
  saveState();
  render();
}

function addProductToCart(productId) {
  if (!activeShift()) {
    alert("Open a cashier shift first.");
    state.activeView = "shift";
    saveState();
    render();
    return;
  }
  const product = state.products.find((item) => item.id === productId);
  const existing = state.cart.find((item) => item.productId === productId);
  if (existing) {
    existing.qty += 1;
    existing.price = currentPrice(product, existing.qty);
  } else {
    state.cart.push({ productId, qty: 1, price: currentPrice(product, 1) });
  }
  saveState();
  render();
}

function updateCartQty(productId, qty) {
  const product = state.products.find((item) => item.id === productId);
  const cartItem = state.cart.find((item) => item.productId === productId);
  if (!cartItem || !product) return;
  cartItem.qty = Math.max(1, Number(qty || 1));
  cartItem.price = currentPrice(product, cartItem.qty);
  saveState();
  render();
}

function removeCartItem(productId) {
  state.cart = state.cart.filter((item) => item.productId !== productId);
  saveState();
  render();
}

function completeSale(paymentMethod) {
  const shift = activeShift();
  if (!shift) return alert("Open a shift first.");
  if (!state.cart.length) return alert("Cart is empty.");

  const lines = state.cart.map((item) => {
    const product = state.products.find((entry) => entry.id === item.productId);
    return {
      productId: product.id,
      name: product.name,
      qty: item.qty,
      unitPrice: item.price,
      cost: product.cost,
      total: item.qty * item.price,
    };
  });
  const total = lines.reduce((sum, line) => sum + line.total, 0);
  state.lastReceiptSeq += 1;
  const receiptNumber = `SHOP-${state.register}-${new Date().toISOString().slice(0, 10).replaceAll("-", "")}-${String(state.lastReceiptSeq).padStart(5, "0")}`;
  const sale = {
    id: id("sale"),
    receiptNumber,
    shiftId: shift.id,
    cashierId: "u-cashier",
    register: state.register,
    lines,
    paymentMethod,
    total,
    createdOffline: !state.online,
    createdAt: new Date().toISOString(),
  };

  state.sales.push(sale);
  for (const line of lines) {
    const product = state.products.find((entry) => entry.id === line.productId);
    product.stock -= line.qty;
    const movement = {
      id: id("move"),
      type: "sale",
      productId: line.productId,
      qtyDelta: -line.qty,
      referenceId: sale.id,
      createdAt: sale.createdAt,
    };
    state.stockMovements.push(movement);
  }
  queueOperation("sale.completed", sale);
  state.cart = [];
  saveState();
  if (state.online) syncNow();
  alert(`Sale completed: ${receiptNumber}\nTotal: ${money(total)}`);
  render();
}

function openShift(form) {
  const openingCash = Number(form.openingCash.value || 0);
  const shift = {
    id: id("shift"),
    cashierId: "u-cashier",
    register: state.register,
    openingCash,
    openedAt: new Date().toISOString(),
    status: "open",
  };
  state.shifts.push(shift);
  state.activeShiftId = shift.id;
  queueOperation("shift.opened", shift);
  saveState();
  if (state.online) syncNow();
  render();
}

function closeShift(form) {
  const shift = activeShift();
  if (!shift) return;
  const countedCash = Number(form.countedCash.value || 0);
  const shiftSales = state.sales.filter((sale) => sale.shiftId === shift.id);
  const cashSales = shiftSales
    .filter((sale) => sale.paymentMethod === "cash")
    .reduce((sum, sale) => sum + sale.total, 0);
  shift.countedCash = countedCash;
  shift.expectedCash = shift.openingCash + cashSales;
  shift.cashVariance = countedCash - shift.expectedCash;
  shift.closedAt = new Date().toISOString();
  shift.status = "closed";
  state.activeShiftId = null;
  queueOperation("shift.closed", shift);
  saveState();
  if (state.online) syncNow();
  render();
}

function addProduct(form) {
  const product = {
    id: id("p"),
    itemId: form.itemId.value.trim(),
    barcode: form.barcode.value.trim(),
    name: form.name.value.trim(),
    brand: form.brand.value.trim(),
    categoryId: form.categoryId.value,
    supplierId: form.supplierId.value,
    stock: Number(form.stock.value || 0),
    cost: Number(form.cost.value || 0),
    retail: Number(form.retail.value || 0),
    wholesale: Number(form.wholesale.value || form.retail.value || 0),
    lotPrice: Number(form.lotPrice.value || form.wholesale.value || form.retail.value || 0),
    lotMinQty: Number(form.lotMinQty.value || 12),
    reorderLevel: Number(form.reorderLevel.value || 0),
  };
  if (!product.itemId || !product.barcode || !product.name) return alert("Item id, barcode, and name are required.");
  if (state.products.some((item) => item.barcode === product.barcode)) return alert("Barcode already exists.");
  state.products.push(product);
  queueOperation("product.created", product);
  form.reset();
  saveState();
  if (state.online) syncNow();
  render();
}

function adjustStock(productId, delta, reason) {
  if (!featureEnabled("inventory")) return;
  const product = state.products.find((item) => item.id === productId);
  product.stock += delta;
  const movement = {
    id: id("move"),
    type: delta >= 0 ? "adjustment_increase" : "adjustment_decrease",
    productId,
    qtyDelta: delta,
    reason,
    createdAt: new Date().toISOString(),
  };
  state.stockMovements.push(movement);
  queueOperation("inventory.adjusted", movement);
  saveState();
  if (state.online) syncNow();
  render();
}

function toggleFeature(key) {
  state.features[key] = !state.features[key];
  queueOperation("feature.toggled", { key, enabled: state.features[key] });
  saveState();
  if (state.online) syncNow();
  render();
}

function navButton(view, label, featureKey = null) {
  const disabled = !roleCan(view) || (featureKey && !featureEnabled(featureKey));
  return `<button class="${state.activeView === view ? "active" : ""}" ${disabled ? "disabled" : ""} onclick="setView('${view}')">${label}</button>`;
}

function renderShell(content) {
  const pending = state.outbox.filter((op) => op.status !== "synced").length;
  const synced = state.outbox.filter((op) => op.status === "synced").length;
  document.getElementById("app").innerHTML = `
    <div class="shell">
      <aside class="sidebar">
        <div class="brand">Offline First POS</div>
        <div class="side-meta">
          <span class="pill ${state.online ? "" : "warn"}">${state.online ? "Online" : "Offline mode"}</span>
          <span>Register ${state.register}</span>
          <span>${pending} pending sync / ${synced} synced</span>
        </div>
        <div class="nav">
          ${navButton("pos", "Cashier POS", "corePos")}
          ${navButton("shift", "Cashier Shift")}
          ${navButton("inventory", "Inventory", "inventory")}
          ${navButton("suppliers", "Suppliers", "suppliers")}
          ${navButton("reports", "Reports", "reports")}
          ${navButton("super", "Super Admin")}
        </div>
      </aside>
      <main class="main">
        <div class="topbar">
          <div>
            <strong>${viewTitle()}</strong>
            <div class="muted">Local-first demo. Billing works while offline.</div>
          </div>
          <div class="topbar-actions">
            <select onchange="setRole(this.value)" style="width: 160px">
              <option value="cashier" ${state.currentRole === "cashier" ? "selected" : ""}>Cashier</option>
              <option value="admin" ${state.currentRole === "admin" ? "selected" : ""}>Store Admin</option>
              <option value="superAdmin" ${state.currentRole === "superAdmin" ? "selected" : ""}>Super Admin</option>
            </select>
            <button onclick="toggleOnline()">${state.online ? "Go Offline" : "Go Online"}</button>
            <button class="blue" onclick="syncNow()" ${state.online ? "" : "disabled"}>Sync Now</button>
          </div>
        </div>
        ${content}
      </main>
    </div>
  `;
}

function viewTitle() {
  const titles = {
    pos: "Cashier Billing",
    shift: "Shift Cash Validation",
    inventory: "Inventory Control",
    suppliers: "Supplier Storage",
    reports: "Reports",
    super: "Super Admin Feature Control",
  };
  return titles[state.activeView] || "POS";
}

function renderPos() {
  const query = "";
  const productRows = state.products.map((product) => `
    <tr>
      <td><strong>${product.name}</strong><br><span class="muted">${product.barcode} · ${product.brand}</span></td>
      <td>${categoryName(product.categoryId)}</td>
      <td>${product.stock <= product.reorderLevel ? `<span class="pill bad">${product.stock}</span>` : product.stock}</td>
      <td>${money(product.retail)}</td>
      <td><button class="primary" onclick="addProductToCart('${product.id}')">Add</button></td>
    </tr>
  `).join("");

  const cartRows = state.cart.map((item) => {
    const product = state.products.find((entry) => entry.id === item.productId);
    return `
      <div class="cart-item">
        <div><strong>${product.name}</strong><br><span class="muted">${money(item.price)} each</span></div>
        <input type="number" min="1" value="${item.qty}" onchange="updateCartQty('${product.id}', this.value)" />
        <div>${money(item.qty * item.price)}</div>
        <button onclick="removeCartItem('${product.id}')">X</button>
      </div>
    `;
  }).join("");
  const total = state.cart.reduce((sum, item) => sum + item.qty * item.price, 0);

  renderShell(`
    <div class="grid">
      <section class="panel span-8">
        <h2>Products</h2>
        <div class="notice">Shortcuts: <span class="kbd">F2</span> open shift, <span class="kbd">F9</span> cash checkout, <span class="kbd">F10</span> card checkout.</div>
        <table>
          <thead><tr><th>Item</th><th>Category</th><th>Stock</th><th>Retail</th><th></th></tr></thead>
          <tbody>${productRows}</tbody>
        </table>
      </section>
      <section class="panel span-4">
        <h2>Cart</h2>
        ${activeShift() ? `<span class="pill">Shift open</span>` : `<span class="pill warn">No open shift</span>`}
        <div class="cart-list" style="margin-top: 12px">${cartRows || `<p class="muted">Cart is empty.</p>`}</div>
        <div class="totals">
          <div class="total-row"><span>Subtotal</span><strong>${money(total)}</strong></div>
          <div class="total-row grand"><span>Total</span><span>${money(total)}</span></div>
        </div>
        <div class="row-actions" style="margin-top: 12px">
          <button class="primary" onclick="completeSale('cash')">Cash</button>
          <button class="blue" onclick="completeSale('card')">Card</button>
        </div>
      </section>
    </div>
  `);
}

function renderShift() {
  const shift = activeShift();
  const shiftSales = shift ? state.sales.filter((sale) => sale.shiftId === shift.id) : [];
  const cashSales = shiftSales.filter((sale) => sale.paymentMethod === "cash").reduce((sum, sale) => sum + sale.total, 0);
  const cardSales = shiftSales.filter((sale) => sale.paymentMethod === "card").reduce((sum, sale) => sum + sale.total, 0);
  renderShell(`
    <div class="grid">
      <section class="panel span-6">
        <h2>Open Shift</h2>
        ${shift ? `
          <p><span class="pill">Open</span></p>
          <p>Opening cash: <strong>${money(shift.openingCash)}</strong></p>
          <p>Opened at: ${new Date(shift.openedAt).toLocaleString()}</p>
        ` : `
          <form onsubmit="event.preventDefault(); openShift(this)" class="form-grid">
            <label class="field">Startup cash<input name="openingCash" type="number" min="0" step="0.01" value="5000" /></label>
            <div class="field"><span>&nbsp;</span><button class="primary">Open Shift</button></div>
          </form>
        `}
      </section>
      <section class="panel span-6">
        <h2>Close Shift</h2>
        ${shift ? `
          <p>Cash sales: <strong>${money(cashSales)}</strong></p>
          <p>Card sales: <strong>${money(cardSales)}</strong></p>
          <p>Expected cash: <strong>${money(shift.openingCash + cashSales)}</strong></p>
          <form onsubmit="event.preventDefault(); closeShift(this)" class="form-grid">
            <label class="field">Counted drawer cash<input name="countedCash" type="number" min="0" step="0.01" /></label>
            <div class="field"><span>&nbsp;</span><button class="danger">Close Shift</button></div>
          </form>
        ` : `<p class="muted">No active shift to close.</p>`}
      </section>
      <section class="panel span-12">
        <h2>Recent Shifts</h2>
        <table>
          <thead><tr><th>Status</th><th>Opened</th><th>Opening</th><th>Expected</th><th>Counted</th><th>Variance</th></tr></thead>
          <tbody>${state.shifts.slice().reverse().map((item) => `
            <tr>
              <td>${item.status}</td>
              <td>${new Date(item.openedAt).toLocaleString()}</td>
              <td>${money(item.openingCash)}</td>
              <td>${money(item.expectedCash)}</td>
              <td>${money(item.countedCash)}</td>
              <td>${money(item.cashVariance)}</td>
            </tr>
          `).join("")}</tbody>
        </table>
      </section>
    </div>
  `);
}

function renderInventory() {
  const options = state.categories.map((category) => `<option value="${category.id}">${category.name}</option>`).join("");
  const supplierOptions = state.suppliers.map((supplier) => `<option value="${supplier.id}">${supplier.name}</option>`).join("");
  const rows = state.products.map((product) => {
    const profit = (product.retail - product.cost) * product.stock;
    return `
      <tr>
        <td><strong>${product.itemId}</strong><br><span class="muted">${product.barcode}</span></td>
        <td>${product.name}<br><span class="muted">${product.brand}</span></td>
        <td>${categoryName(product.categoryId)}</td>
        <td>${supplierName(product.supplierId)}</td>
        <td>${product.stock <= product.reorderLevel ? `<span class="pill bad">${product.stock}</span>` : product.stock}</td>
        <td>${money(product.cost)}</td>
        <td>${money(product.retail)}</td>
        <td>${money(profit)}</td>
        <td class="row-actions">
          <button onclick="adjustStock('${product.id}', 1, 'Manual increase')">+1</button>
          <button onclick="adjustStock('${product.id}', -1, 'Manual decrease')">-1</button>
          <button onclick="adjustStock('${product.id}', -1, 'Damage')">Damage</button>
        </td>
      </tr>
    `;
  }).join("");
  const stockValue = state.products.reduce((sum, product) => sum + product.stock * product.cost, 0);
  const sellingValue = state.products.reduce((sum, product) => sum + product.stock * product.retail, 0);
  renderShell(`
    <div class="grid">
      <section class="panel span-12">
        <h2>Inventory Summary</h2>
        <div class="grid">
          <div class="span-3"><span class="muted">Stock value</span><h3>${money(stockValue)}</h3></div>
          <div class="span-3"><span class="muted">Selling value</span><h3>${money(sellingValue)}</h3></div>
          <div class="span-3"><span class="muted">Estimated profit</span><h3>${money(sellingValue - stockValue)}</h3></div>
          <div class="span-3"><span class="muted">Low stock</span><h3>${state.products.filter((p) => p.stock <= p.reorderLevel).length}</h3></div>
        </div>
      </section>
      <section class="panel span-12">
        <h2>Add Product</h2>
        <form onsubmit="event.preventDefault(); addProduct(this)" class="form-grid">
          <label class="field">Item id<input name="itemId" required /></label>
          <label class="field">Barcode<input name="barcode" required placeholder="Scan or type barcode" /></label>
          <label class="field">Name<input name="name" required /></label>
          <label class="field">Brand<input name="brand" /></label>
          <label class="field">Category<select name="categoryId">${options}</select></label>
          <label class="field">Supplier<select name="supplierId">${supplierOptions}</select></label>
          <label class="field">Stock<input name="stock" type="number" min="0" value="0" /></label>
          <label class="field">Reorder level<input name="reorderLevel" type="number" min="0" value="5" /></label>
          <label class="field">Cost price<input name="cost" type="number" min="0" step="0.01" /></label>
          <label class="field">Retail price<input name="retail" type="number" min="0" step="0.01" /></label>
          <label class="field">Wholesale price<input name="wholesale" type="number" min="0" step="0.01" /></label>
          <label class="field">Lot price<input name="lotPrice" type="number" min="0" step="0.01" /></label>
          <label class="field">Lot min qty<input name="lotMinQty" type="number" min="1" value="12" /></label>
          <div class="field"><span>&nbsp;</span><button class="primary">Add Product</button></div>
        </form>
      </section>
      <section class="panel span-12">
        <h2>Browse Inventory</h2>
        <table>
          <thead><tr><th>Item</th><th>Description</th><th>Category</th><th>Supplier</th><th>Qty</th><th>Cost</th><th>Sell</th><th>Profit</th><th>Adjust</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </section>
    </div>
  `);
}

function renderSuppliers() {
  const rows = state.suppliers.map((supplier) => {
    const products = state.products.filter((product) => product.supplierId === supplier.id);
    return `
      <tr>
        <td><strong>${supplier.name}</strong><br><span class="muted">${supplier.phone}</span></td>
        <td>${products.length}</td>
        <td>${money(supplier.outstanding)}</td>
        <td>${products.map((product) => `${product.name}: ${product.stock} left`).join("<br>")}</td>
      </tr>
    `;
  }).join("");
  renderShell(`
    <section class="panel">
      <h2>Supplier Visit View</h2>
      <p class="muted">Use this to see what each supplier provided and what stock is left before reordering.</p>
      <table>
        <thead><tr><th>Supplier</th><th>Products</th><th>Outstanding</th><th>Current stock from supplier</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </section>
  `);
}

function renderReports() {
  const totalSales = state.sales.reduce((sum, sale) => sum + sale.total, 0);
  const cashSales = state.sales.filter((sale) => sale.paymentMethod === "cash").reduce((sum, sale) => sum + sale.total, 0);
  const cardSales = state.sales.filter((sale) => sale.paymentMethod === "card").reduce((sum, sale) => sum + sale.total, 0);
  const productRank = state.products.map((product) => {
    const qty = state.sales.flatMap((sale) => sale.lines).filter((line) => line.productId === product.id).reduce((sum, line) => sum + line.qty, 0);
    return { product, qty };
  }).sort((a, b) => b.qty - a.qty);
  renderShell(`
    <div class="grid">
      <section class="panel span-3"><span class="muted">Total sales</span><h2>${money(totalSales)}</h2></section>
      <section class="panel span-3"><span class="muted">Cash</span><h2>${money(cashSales)}</h2></section>
      <section class="panel span-3"><span class="muted">Card</span><h2>${money(cardSales)}</h2></section>
      <section class="panel span-3"><span class="muted">Receipts</span><h2>${state.sales.length}</h2></section>
      <section class="panel span-6">
        <h2>Best Selling Items</h2>
        <table>
          <thead><tr><th>Product</th><th>Qty sold</th><th>Stock left</th></tr></thead>
          <tbody>${productRank.map((row) => `<tr><td>${row.product.name}</td><td>${row.qty}</td><td>${row.product.stock}</td></tr>`).join("")}</tbody>
        </table>
      </section>
      <section class="panel span-6">
        <h2>Sync Queue</h2>
        <table>
          <thead><tr><th>Operation</th><th>Status</th><th>Created</th></tr></thead>
          <tbody>${state.outbox.slice().reverse().map((op) => `<tr><td>${op.type}</td><td>${op.status}</td><td>${new Date(op.createdAt).toLocaleString()}</td></tr>`).join("")}</tbody>
        </table>
      </section>
    </div>
  `);
}

function renderSuper() {
  const rows = Object.entries(state.features).map(([key, enabled]) => `
    <tr>
      <td><strong>${key}</strong></td>
      <td>${enabled ? `<span class="pill">Enabled</span>` : `<span class="pill bad">Disabled</span>`}</td>
      <td><button onclick="toggleFeature('${key}')">${enabled ? "Disable" : "Enable"}</button></td>
    </tr>
  `).join("");
  renderShell(`
    <section class="panel">
      <h2>Feature Control</h2>
      <p class="muted">This simulates your company turning paid modules on or off per shop.</p>
      <table>
        <thead><tr><th>Feature</th><th>Status</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </section>
  `);
}

function render() {
  if (!roleCan(state.activeView)) state.activeView = "pos";
  if (state.activeView === "inventory" && !featureEnabled("inventory")) state.activeView = "pos";
  if (state.activeView === "suppliers" && !featureEnabled("suppliers")) state.activeView = "pos";
  if (state.activeView === "reports" && !featureEnabled("reports")) state.activeView = "pos";
  const views = {
    pos: renderPos,
    shift: renderShift,
    inventory: renderInventory,
    suppliers: renderSuppliers,
    reports: renderReports,
    super: renderSuper,
  };
  views[state.activeView]();
}

window.addEventListener("online", () => {
  state.online = true;
  syncNow();
});

window.addEventListener("offline", () => {
  state.online = false;
  saveState();
  render();
});

window.addEventListener("keydown", (event) => {
  if (event.key === "F2") {
    event.preventDefault();
    setView("shift");
  }
  if (event.key === "F9") {
    event.preventDefault();
    completeSale("cash");
  }
  if (event.key === "F10") {
    event.preventDefault();
    completeSale("card");
  }
});

render();

