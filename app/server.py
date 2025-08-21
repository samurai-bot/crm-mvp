#!/usr/bin/env python3
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

DB_PATH = os.path.join(os.path.dirname(__file__), 'crm.sqlite3')
STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')


def now_iso():
    # Use timezone-aware UTC to avoid deprecation warnings
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    # Customers
    c.execute(
        '''CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT DEFAULT 'Individual',
            email TEXT,
            phone TEXT,
            status TEXT DEFAULT 'Active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )'''
    )
    c.execute(
        '''CREATE TABLE IF NOT EXISTS addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            line1 TEXT NOT NULL,
            line2 TEXT,
            city TEXT,
            state TEXT,
            postal_code TEXT,
            country TEXT DEFAULT 'US',
            is_primary INTEGER DEFAULT 0,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )'''
    )
    c.execute(
        '''CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            role TEXT,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )'''
    )

    # Products
    c.execute(
        '''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            price_cents INTEGER NOT NULL,
            currency TEXT DEFAULT 'USD',
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        )'''
    )

    # Orders
    c.execute(
        '''CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            status TEXT DEFAULT 'Pending',
            total_cents INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )'''
    )
    c.execute(
        '''CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price_cents INTEGER NOT NULL,
            line_total_cents INTEGER NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products(id)
        )'''
    )

    # Cases
    c.execute(
        '''CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            order_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'Open',
            priority TEXT DEFAULT 'Medium',
            assignee TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE SET NULL
        )'''
    )

    # Activities (simple audit trail)
    c.execute(
        '''CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            activity TEXT NOT NULL,
            created_at TEXT NOT NULL
        )'''
    )

    conn.commit()
    conn.close()


def seed_if_empty():
    conn = get_conn()
    c = conn.cursor()
    # Seed customers
    count = c.execute('SELECT COUNT(*) as n FROM customers').fetchone()['n']
    if count == 0:
        now = now_iso()
        customers = [
            ('Acme Telecom', 'Business', 'ops@acme.example', '+1-202-555-0147', 'Active'),
            ('Jane Doe', 'Individual', 'jane@example.com', '+1-202-555-0183', 'Active'),
        ]
        for name, typ, email, phone, status in customers:
            c.execute(
                'INSERT INTO customers(name, type, email, phone, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?)',
                (name, typ, email, phone, status, now, now),
            )
        # Addresses
        c.execute(
            'INSERT INTO addresses(customer_id, line1, city, state, postal_code, country, is_primary) VALUES (1,?,?,?,?,?,1)',
            ('100 Main St', 'Metropolis', 'NY', '10001', 'US'),
        )
        c.execute(
            'INSERT INTO addresses(customer_id, line1, city, state, postal_code, country, is_primary) VALUES (2,?,?,?,?,?,1)',
            ('55 Pine Ave', 'Springfield', 'IL', '62701', 'US'),
        )
        # Contacts
        c.execute('INSERT INTO contacts(customer_id, name, email, phone, role) VALUES (?,?,?,?,?)',
                  (1, 'Sam Ops', 'sam.ops@acme.example', '+1-202-555-0123', 'Operations'))

    # Seed products
    pcount = c.execute('SELECT COUNT(*) as n FROM products').fetchone()['n']
    if pcount == 0:
        now = now_iso()
        products = [
            ('PLAN-5G-BASIC', '5G Basic Plan', '10GB data, unlimited talk/text', 'Plan', 3000),
            ('PLAN-5G-UNL', '5G Unlimited Plan', 'Unlimited data, talk, text', 'Plan', 7000),
            ('ROUTER-ACME-1000', 'Acme Home Router 1000', 'WiFi 6 home router', 'Device', 12999),
            ('SIM-TRI-CUT', 'Tri-cut SIM', 'Multi-size SIM card', 'Accessory', 500),
        ]
        for sku, name, desc, cat, price_cents in products:
            c.execute(
                'INSERT INTO products(sku, name, description, category, price_cents, created_at) VALUES (?,?,?,?,?,?)',
                (sku, name, desc, cat, price_cents, now),
            )

    # Seed an order
    ocount = c.execute('SELECT COUNT(*) as n FROM orders').fetchone()['n']
    if ocount == 0:
        now = now_iso()
        c.execute('INSERT INTO orders(customer_id, status, total_cents, created_at, updated_at, notes) VALUES (1,?,?,?,?,?)',
                  ('Pending', 0, now, now, 'Initial demo order'))
        order_id = c.lastrowid
        # Add items
        items = c.execute('SELECT id, price_cents FROM products WHERE sku IN (?,?)',
                          ('PLAN-5G-UNL', 'SIM-TRI-CUT')).fetchall()
        total = 0
        for prod in items:
            qty = 1
            unit = prod['price_cents']
            line = unit * qty
            total += line
            c.execute('INSERT INTO order_items(order_id, product_id, quantity, unit_price_cents, line_total_cents) VALUES (?,?,?,?,?)',
                      (order_id, prod['id'], qty, unit, line))
        c.execute('UPDATE orders SET total_cents=?, updated_at=? WHERE id=?', (total, now_iso(), order_id))

    # Seed a case
    ccount = c.execute('SELECT COUNT(*) as n FROM cases').fetchone()['n']
    if ccount == 0:
        now = now_iso()
        c.execute('INSERT INTO cases(customer_id, order_id, title, description, status, priority, assignee, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                  (1, 1, 'SIM not activating', 'Customer reports SIM activation failure.', 'Open', 'High', 'agent.alex', now, now))

    conn.commit()
    conn.close()


def parse_json(handler):
    length = int(handler.headers.get('Content-Length', 0))
    if length == 0:
        return {}
    body = handler.rfile.read(length)
    try:
        return json.loads(body.decode('utf-8'))
    except Exception:
        return {}


def send_json(handler, status, payload):
    data = json.dumps(payload).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Content-Length', str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def not_found(handler):
    send_json(handler, 404, {'error': 'Not found'})


class CRMHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        # Basic CORS for local dev
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/':
            return self.serve_static('index.html')
        if parsed.path.startswith('/static/'):
            rel = parsed.path[len('/static/') :]
            return self.serve_static(rel)

        # API routes
        if parsed.path.startswith('/api/'):
            return self.handle_api('GET', parsed)
        return not_found(self)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/'):
            return self.handle_api('POST', parsed)
        return not_found(self)

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/'):
            return self.handle_api('PUT', parsed)
        return not_found(self)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/'):
            return self.handle_api('DELETE', parsed)
        return not_found(self)

    def serve_static(self, rel_path):
        safe = os.path.normpath(rel_path).lstrip(os.sep)
        full = os.path.join(STATIC_DIR, safe)
        if not os.path.isfile(full):
            return not_found(self)
        ctype = 'text/plain'
        if full.endswith('.html'):
            ctype = 'text/html; charset=utf-8'
        elif full.endswith('.js'):
            ctype = 'text/javascript; charset=utf-8'
        elif full.endswith('.css'):
            ctype = 'text/css; charset=utf-8'
        with open(full, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_api(self, method, parsed):
        path = parsed.path
        # Route patterns
        routes = [
            (r'^/api/customers$', self.api_customers),
            (r'^/api/customers/(\d+)$', self.api_customer_by_id),
            (r'^/api/products$', self.api_products),
            (r'^/api/products/(\d+)$', self.api_product_by_id),
            (r'^/api/orders$', self.api_orders),
            (r'^/api/orders/(\d+)$', self.api_order_by_id),
            (r'^/api/cases$', self.api_cases),
            (r'^/api/cases/(\d+)$', self.api_case_by_id),
            (r'^/api/search$', self.api_search),
            (r'^/api/dashboard$', self.api_dashboard),
        ]
        for pattern, handler in routes:
            m = re.match(pattern, path)
            if m:
                return handler(method, parsed, *m.groups())
        return not_found(self)

    # Collection handlers
    def api_customers(self, method, parsed):
        conn = get_conn()
        c = conn.cursor()
        if method == 'GET':
            qs = parse_qs(parsed.query)
            q = qs.get('q', [''])[0].strip()
            if q:
                rows = c.execute(
                    "SELECT * FROM customers WHERE name LIKE ? OR email LIKE ? ORDER BY created_at DESC",
                    (f'%{q}%', f'%{q}%'),
                ).fetchall()
            else:
                rows = c.execute('SELECT * FROM customers ORDER BY created_at DESC').fetchall()
            conn.close()
            return send_json(self, 200, rows)
        elif method == 'POST':
            data = parse_json(self)
            now = now_iso()
            c.execute(
                'INSERT INTO customers(name, type, email, phone, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?)',
                (
                    data.get('name'),
                    data.get('type', 'Individual'),
                    data.get('email'),
                    data.get('phone'),
                    data.get('status', 'Active'),
                    now,
                    now,
                ),
            )
            conn.commit()
            new_id = c.lastrowid
            row = c.execute('SELECT * FROM customers WHERE id=?', (new_id,)).fetchone()
            conn.close()
            return send_json(self, 201, row)
        else:
            conn.close()
            return not_found(self)

    def api_customer_by_id(self, method, parsed, cid):
        cid = int(cid)
        conn = get_conn()
        c = conn.cursor()
        if method == 'GET':
            row = c.execute('SELECT * FROM customers WHERE id=?', (cid,)).fetchone()
            # include addresses/contacts
            if not row:
                conn.close()
                return not_found(self)
            row['addresses'] = c.execute('SELECT * FROM addresses WHERE customer_id=?', (cid,)).fetchall()
            row['contacts'] = c.execute('SELECT * FROM contacts WHERE customer_id=?', (cid,)).fetchall()
            conn.close()
            return send_json(self, 200, row)
        elif method == 'PUT':
            data = parse_json(self)
            now = now_iso()
            # Only allow certain fields
            fields = ['name', 'type', 'email', 'phone', 'status']
            sets = []
            vals = []
            for f in fields:
                if f in data:
                    sets.append(f"{f}=?")
                    vals.append(data[f])
            sets.append('updated_at=?')
            vals.append(now)
            vals.append(cid)
            c.execute(f"UPDATE customers SET {', '.join(sets)} WHERE id=?", vals)
            conn.commit()
            row = c.execute('SELECT * FROM customers WHERE id=?', (cid,)).fetchone()
            conn.close()
            return send_json(self, 200, row)
        elif method == 'DELETE':
            c.execute('DELETE FROM customers WHERE id=?', (cid,))
            conn.commit()
            conn.close()
            return send_json(self, 200, {'deleted': True})
        else:
            conn.close()
            return not_found(self)

    def api_products(self, method, parsed):
        conn = get_conn()
        c = conn.cursor()
        if method == 'GET':
            qs = parse_qs(parsed.query)
            q = qs.get('q', [''])[0].strip()
            if q:
                rows = c.execute(
                    "SELECT * FROM products WHERE name LIKE ? OR sku LIKE ? ORDER BY created_at DESC",
                    (f'%{q}%', f'%{q}%'),
                ).fetchall()
            else:
                rows = c.execute('SELECT * FROM products ORDER BY created_at DESC').fetchall()
            conn.close()
            return send_json(self, 200, rows)
        elif method == 'POST':
            data = parse_json(self)
            now = now_iso()
            c.execute(
                'INSERT INTO products(sku, name, description, category, price_cents, currency, is_active, created_at) VALUES (?,?,?,?,?,?,?,?)',
                (
                    data.get('sku'),
                    data.get('name'),
                    data.get('description'),
                    data.get('category'),
                    int(data.get('price_cents', 0)),
                    data.get('currency', 'USD'),
                    1 if data.get('is_active', True) else 0,
                    now,
                ),
            )
            conn.commit()
            new_id = c.lastrowid
            row = c.execute('SELECT * FROM products WHERE id=?', (new_id,)).fetchone()
            conn.close()
            return send_json(self, 201, row)
        else:
            conn.close()
            return not_found(self)

    def api_product_by_id(self, method, parsed, pid):
        pid = int(pid)
        conn = get_conn()
        c = conn.cursor()
        if method == 'GET':
            row = c.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
            conn.close()
            if not row:
                return not_found(self)
            return send_json(self, 200, row)
        elif method == 'PUT':
            data = parse_json(self)
            fields = ['sku', 'name', 'description', 'category', 'price_cents', 'currency', 'is_active']
            sets = []
            vals = []
            for f in fields:
                if f in data:
                    val = data[f]
                    if f in ('price_cents', 'is_active') and val is not None:
                        val = int(val)
                    sets.append(f"{f}=?")
                    vals.append(val)
            vals.append(pid)
            if sets:
                c.execute(f"UPDATE products SET {', '.join(sets)} WHERE id=?", vals)
                conn.commit()
            row = c.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
            conn.close()
            return send_json(self, 200, row)
        elif method == 'DELETE':
            c.execute('DELETE FROM products WHERE id=?', (pid,))
            conn.commit()
            conn.close()
            return send_json(self, 200, {'deleted': True})
        else:
            conn.close()
            return not_found(self)

    def api_orders(self, method, parsed):
        conn = get_conn()
        c = conn.cursor()
        if method == 'GET':
            rows = c.execute(
                'SELECT o.*, cu.name as customer_name FROM orders o JOIN customers cu ON cu.id = o.customer_id ORDER BY o.created_at DESC'
            ).fetchall()
            conn.close()
            return send_json(self, 200, rows)
        elif method == 'POST':
            data = parse_json(self)
            now = now_iso()
            customer_id = int(data.get('customer_id'))
            notes = data.get('notes')
            items = data.get('items', [])
            c.execute('INSERT INTO orders(customer_id, status, total_cents, currency, notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?)',
                      (customer_id, 'Pending', 0, data.get('currency', 'USD'), notes, now, now))
            order_id = c.lastrowid
            total = 0
            for item in items:
                product_id = int(item['product_id'])
                quantity = int(item.get('quantity', 1))
                prod = c.execute('SELECT price_cents FROM products WHERE id=?', (product_id,)).fetchone()
                if not prod:
                    continue
                unit = int(item.get('unit_price_cents', prod['price_cents']))
                line = unit * quantity
                total += line
                c.execute('INSERT INTO order_items(order_id, product_id, quantity, unit_price_cents, line_total_cents) VALUES (?,?,?,?,?)',
                          (order_id, product_id, quantity, unit, line))
            c.execute('UPDATE orders SET total_cents=?, updated_at=? WHERE id=?', (total, now_iso(), order_id))
            conn.commit()
            order = c.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
            items = c.execute('SELECT * FROM order_items WHERE order_id=?', (order_id,)).fetchall()
            order['items'] = items
            conn.close()
            return send_json(self, 201, order)
        else:
            conn.close()
            return not_found(self)

    def api_order_by_id(self, method, parsed, oid):
        oid = int(oid)
        conn = get_conn()
        c = conn.cursor()
        if method == 'GET':
            order = c.execute('SELECT * FROM orders WHERE id=?', (oid,)).fetchone()
            if not order:
                conn.close()
                return not_found(self)
            items = c.execute('SELECT oi.*, p.sku, p.name FROM order_items oi JOIN products p ON p.id = oi.product_id WHERE order_id=?', (oid,)).fetchall()
            order['items'] = items
            conn.close()
            return send_json(self, 200, order)
        elif method == 'PUT':
            data = parse_json(self)
            sets = []
            vals = []
            if 'status' in data:
                sets.append('status=?')
                vals.append(data['status'])
            if 'notes' in data:
                sets.append('notes=?')
                vals.append(data['notes'])
            sets.append('updated_at=?')
            vals.append(now_iso())
            vals.append(oid)
            if sets:
                c.execute(f"UPDATE orders SET {', '.join(sets)} WHERE id=?", vals)
                conn.commit()
            order = c.execute('SELECT * FROM orders WHERE id=?', (oid,)).fetchone()
            conn.close()
            return send_json(self, 200, order)
        elif method == 'DELETE':
            c.execute('DELETE FROM orders WHERE id=?', (oid,))
            conn.commit()
            conn.close()
            return send_json(self, 200, {'deleted': True})
        else:
            conn.close()
            return not_found(self)

    def api_cases(self, method, parsed):
        conn = get_conn()
        c = conn.cursor()
        if method == 'GET':
            rows = c.execute(
                'SELECT cs.*, cu.name as customer_name FROM cases cs JOIN customers cu ON cu.id = cs.customer_id ORDER BY cs.created_at DESC'
            ).fetchall()
            conn.close()
            return send_json(self, 200, rows)
        elif method == 'POST':
            data = parse_json(self)
            now = now_iso()
            c.execute('INSERT INTO cases(customer_id, order_id, title, description, status, priority, assignee, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                      (
                          int(data['customer_id']),
                          int(data['order_id']) if data.get('order_id') else None,
                          data['title'],
                          data.get('description'),
                          data.get('status', 'Open'),
                          data.get('priority', 'Medium'),
                          data.get('assignee'),
                          now,
                          now,
                      ))
            conn.commit()
            new_id = c.lastrowid
            row = c.execute('SELECT * FROM cases WHERE id=?', (new_id,)).fetchone()
            conn.close()
            return send_json(self, 201, row)
        else:
            conn.close()
            return not_found(self)

    def api_case_by_id(self, method, parsed, cid):
        cid = int(cid)
        conn = get_conn()
        c = conn.cursor()
        if method == 'GET':
            row = c.execute('SELECT * FROM cases WHERE id=?', (cid,)).fetchone()
            conn.close()
            if not row:
                return not_found(self)
            return send_json(self, 200, row)
        elif method == 'PUT':
            data = parse_json(self)
            fields = ['title', 'description', 'status', 'priority', 'assignee']
            sets = []
            vals = []
            for f in fields:
                if f in data:
                    sets.append(f"{f}=?")
                    vals.append(data[f])
            sets.append('updated_at=?')
            vals.append(now_iso())
            vals.append(cid)
            if sets:
                c.execute(f"UPDATE cases SET {', '.join(sets)} WHERE id=?", vals)
                conn.commit()
            row = c.execute('SELECT * FROM cases WHERE id=?', (cid,)).fetchone()
            conn.close()
            return send_json(self, 200, row)
        elif method == 'DELETE':
            c.execute('DELETE FROM cases WHERE id=?', (cid,))
            conn.commit()
            conn.close()
            return send_json(self, 200, {'deleted': True})
        else:
            conn.close()
            return not_found(self)

    def api_search(self, method, parsed):
        qs = parse_qs(parsed.query)
        q = (qs.get('q', [''])[0]).strip()
        conn = get_conn()
        c = conn.cursor()
        results = {
            'customers': [],
            'products': [],
            'orders': [],
            'cases': [],
        }
        if q:
            results['customers'] = c.execute('SELECT * FROM customers WHERE name LIKE ? OR email LIKE ? LIMIT 10', (f'%{q}%', f'%{q}%')).fetchall()
            results['products'] = c.execute('SELECT * FROM products WHERE name LIKE ? OR sku LIKE ? LIMIT 10', (f'%{q}%', f'%{q}%')).fetchall()
            results['orders'] = c.execute('SELECT * FROM orders WHERE id LIKE ? LIMIT 10', (f'%{q}%',)).fetchall()
            results['cases'] = c.execute('SELECT * FROM cases WHERE title LIKE ? LIMIT 10', (f'%{q}%',)).fetchall()
        conn.close()
        return send_json(self, 200, results)

    def api_dashboard(self, method, parsed):
        conn = get_conn()
        c = conn.cursor()
        metrics = {
            'customers': c.execute('SELECT COUNT(*) as n FROM customers').fetchone()['n'],
            'products': c.execute('SELECT COUNT(*) as n FROM products').fetchone()['n'],
            'orders': c.execute('SELECT COUNT(*) as n FROM orders').fetchone()['n'],
            'cases': c.execute('SELECT COUNT(*) as n FROM cases').fetchone()['n'],
            'open_cases': c.execute("SELECT COUNT(*) as n FROM cases WHERE status IN ('Open','In Progress')").fetchone()['n'],
            'pending_orders': c.execute("SELECT COUNT(*) as n FROM orders WHERE status IN ('Pending','Confirmed')").fetchone()['n'],
        }
        conn.close()
        return send_json(self, 200, metrics)


def run(host='127.0.0.1', port=8000):
    # Allow cloud hosts like Render/Railway to set host/port via env
    host = os.getenv('HOST', host)
    try:
        port = int(os.getenv('PORT', str(port)))
    except ValueError:
        port = port
    init_db()
    seed_if_empty()
    httpd = HTTPServer((host, port), CRMHandler)
    print(f'CRM server running on http://{host}:{port}')
    if host in ('127.0.0.1', 'localhost'):
        print('Open the app at http://127.0.0.1:8000/')
    httpd.serve_forever()


if __name__ == '__main__':
    run()
