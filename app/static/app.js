const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));

const state = {
  view: 'dashboard',
};

const api = async (path, opts = {}) => {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

function fmtMoney(cents, currency = 'USD') {
  const v = (Number(cents) || 0) / 100;
  return v.toLocaleString(undefined, { style: 'currency', currency });
}

function navTo(view) {
  state.view = view;
  $$('.active', $('nav')).forEach((b) => b.classList.remove('active'));
  $(`nav button[data-view="${view}"]`)?.classList.add('active');
  render();
}

async function renderDashboard() {
  const el = document.createElement('div');
  el.className = 'grid';
  const metrics = await api('/api/dashboard');
  const kpi = (label, val, cls = '') => `
    <div class="card">
      <div class="muted">${label}</div>
      <div class="kpi ${cls}">${val}</div>
    </div>`;
  el.innerHTML = [
    kpi('Customers', metrics.customers),
    kpi('Active Products', metrics.products),
    kpi('Orders', metrics.orders),
    kpi('Open Cases', metrics.open_cases, metrics.open_cases ? 'warn' : 'good'),
    kpi('Pending Orders', metrics.pending_orders, metrics.pending_orders ? 'warn' : 'good'),
  ].join('');
  return el;
}

async function renderCustomers() {
  const wrap = document.createElement('div');
  wrap.className = 'grid';
  const toolbar = document.createElement('div');
  toolbar.className = 'toolbar card';
  toolbar.innerHTML = `
    <div class="row wrap">
      <input id="cust-q" placeholder="Search name or email" />
      <button class="primary" id="cust-search">Search</button>
    </div>
    <form id="cust-form" class="row wrap" onsubmit="return false;">
      <input name="name" placeholder="Customer name" required />
      <select name="type">
        <option>Individual</option>
        <option>Business</option>
      </select>
      <input name="email" placeholder="Email" />
      <input name="phone" placeholder="Phone" />
      <button class="primary" type="submit">Add</button>
    </form>
  `;
  wrap.appendChild(toolbar);

  const tableCard = document.createElement('div');
  tableCard.className = 'card';
  tableCard.innerHTML = `
    <table>
      <thead>
        <tr><th>Name</th><th>Type</th><th>Email</th><th>Phone</th><th>Status</th></tr>
      </thead>
      <tbody id="cust-tbody"></tbody>
    </table>
  `;
  wrap.appendChild(tableCard);

  const load = async (q = '') => {
    const data = await api('/api/customers' + (q ? `?q=${encodeURIComponent(q)}` : ''));
    const tbody = $('#cust-tbody', tableCard);
    tbody.innerHTML = '';
    data.forEach((c) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${c.name}</td><td>${c.type}</td><td>${c.email || ''}</td><td>${c.phone || ''}</td><td><span class="pill ${c.status==='Active'?'good':'warn'}">${c.status}</span></td>`;
      tbody.appendChild(tr);
    });
  };
  load();

  $('#cust-search', toolbar).onclick = () => load($('#cust-q').value.trim());
  $('#cust-form', toolbar).onsubmit = async (e) => {
    const fd = new FormData(e.target);
    const payload = Object.fromEntries(fd.entries());
    await api('/api/customers', { method: 'POST', body: JSON.stringify(payload) });
    e.target.reset();
    load();
  };
  return wrap;
}

async function renderProducts() {
  const wrap = document.createElement('div');
  wrap.className = 'grid';

  const form = document.createElement('form');
  form.className = 'card row wrap';
  form.innerHTML = `
    <input name="sku" placeholder="SKU" required />
    <input name="name" placeholder="Name" required />
    <input name="category" placeholder="Category" />
    <input name="price_cents" type="number" placeholder="Price (cents)" required />
    <input name="description" placeholder="Description" style="flex:1;" />
    <button class="primary" type="submit">Add Product</button>
  `;
  wrap.appendChild(form);

  const list = document.createElement('div');
  list.className = 'card';
  list.innerHTML = `
    <table>
      <thead><tr><th>SKU</th><th>Name</th><th>Category</th><th>Price</th><th>Status</th></tr></thead>
      <tbody id="prod-tbody"></tbody>
    </table>
  `;
  wrap.appendChild(list);

  const load = async () => {
    const data = await api('/api/products');
    const tbody = $('#prod-tbody', list);
    tbody.innerHTML = '';
    data.forEach((p) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${p.sku}</td><td>${p.name}</td><td>${p.category || ''}</td><td>${fmtMoney(p.price_cents, p.currency)}</td><td>${p.is_active?'<span class="pill good">Active</span>':'<span class="pill warn">Inactive</span>'}</td>`;
      tbody.appendChild(tr);
    });
  };
  load();

  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const data = Object.fromEntries(fd.entries());
    data.price_cents = Number(data.price_cents || 0);
    await api('/api/products', { method: 'POST', body: JSON.stringify(data) });
    form.reset();
    load();
  };
  return wrap;
}

async function renderOrders() {
  const wrap = document.createElement('div');
  wrap.className = 'grid';

  const creator = document.createElement('div');
  creator.className = 'card';
  creator.innerHTML = `
    <div class="row wrap">
      <input id="order-customer-id" type="number" placeholder="Customer ID" />
      <input id="order-product-id" type="number" placeholder="Product ID" />
      <input id="order-qty" type="number" value="1" min="1" />
      <button class="primary" id="order-add">Create Order</button>
    </div>
    <div class="muted">Quick-create: single-line order</div>
  `;
  wrap.appendChild(creator);

  const list = document.createElement('div');
  list.className = 'card';
  list.innerHTML = `
    <table>
      <thead><tr><th>#</th><th>Customer</th><th>Status</th><th>Total</th><th>Created</th></tr></thead>
      <tbody id="orders-tbody"></tbody>
    </table>`;
  wrap.appendChild(list);

  async function load() {
    const data = await api('/api/orders');
    const tbody = $('#orders-tbody', list);
    tbody.innerHTML = '';
    data.forEach((o) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${o.id}</td><td>${o.customer_name || o.customer_id}</td><td><span class="pill ${o.status==='Fulfilled'?'good':(o.status==='Cancelled'?'bad':'warn')}">${o.status}</span></td><td>${fmtMoney(o.total_cents, o.currency)}</td><td class="muted">${o.created_at}</td>`;
      tbody.appendChild(tr);
    });
  }
  load();

  $('#order-add', creator).onclick = async () => {
    const customer_id = Number($('#order-customer-id').value);
    const product_id = Number($('#order-product-id').value);
    const quantity = Number($('#order-qty').value || 1);
    if (!customer_id || !product_id) return alert('Enter customer and product IDs');
    await api('/api/orders', {
      method: 'POST',
      body: JSON.stringify({ customer_id, items: [{ product_id, quantity }] }),
    });
    $('#order-product-id').value = '';
    load();
  };
  return wrap;
}

async function renderCases() {
  const wrap = document.createElement('div');
  wrap.className = 'grid';

  const form = document.createElement('form');
  form.className = 'card row wrap';
  form.innerHTML = `
    <input name="customer_id" type="number" placeholder="Customer ID" required />
    <input name="order_id" type="number" placeholder="Order ID (optional)" />
    <input name="title" placeholder="Title" required />
    <input name="priority" placeholder="Priority (Low/Medium/High)" />
    <input name="assignee" placeholder="Assignee" />
    <input name="description" placeholder="Description" style="flex:1" />
    <button class="primary" type="submit">Log Case</button>
  `;
  wrap.appendChild(form);

  const list = document.createElement('div');
  list.className = 'card';
  list.innerHTML = `
    <table>
      <thead><tr><th>#</th><th>Customer</th><th>Title</th><th>Status</th><th>Priority</th><th>Assignee</th></tr></thead>
      <tbody id="cases-tbody"></tbody>
    </table>`;
  wrap.appendChild(list);

  const load = async () => {
    const data = await api('/api/cases');
    const tbody = $('#cases-tbody', list);
    tbody.innerHTML = '';
    data.forEach((cs) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${cs.id}</td><td>${cs.customer_name || cs.customer_id}</td><td>${cs.title}</td><td><span class="pill ${cs.status==='Closed'?'good':'warn'}">${cs.status}</span></td><td>${cs.priority}</td><td>${cs.assignee || ''}</td>`;
      tbody.appendChild(tr);
    });
  };
  load();

  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const data = Object.fromEntries(fd.entries());
    if (!data.customer_id) return;
    if (!data.order_id) delete data.order_id;
    await api('/api/cases', { method: 'POST', body: JSON.stringify(data) });
    form.reset();
    load();
  };
  return wrap;
}

async function render() {
  const content = $('#content');
  content.innerHTML = '';
  try {
    let el;
    if (state.view === 'dashboard') el = await renderDashboard();
    if (state.view === 'customers') el = await renderCustomers();
    if (state.view === 'products') el = await renderProducts();
    if (state.view === 'orders') el = await renderOrders();
    if (state.view === 'cases') el = await renderCases();
    content.appendChild(el);
  } catch (e) {
    const err = document.createElement('div');
    err.className = 'card';
    err.innerHTML = `<div class="bad">Error</div><pre>${e.message}</pre>`;
    content.appendChild(err);
  }
}

window.addEventListener('DOMContentLoaded', () => {
  $$('nav button').forEach((b) => (b.onclick = () => navTo(b.dataset.view)));
  render();
});

