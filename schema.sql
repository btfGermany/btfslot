CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL,
    created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    base_price DECIMAL(10,2) NOT NULL,
    capacity INTEGER NOT NULL,
    image_url TEXT,
    label TEXT,
    product_type TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT 1,
    deleted BOOLEAN NOT NULL DEFAULT 0,

    created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_daily_availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    date DATE NOT NULL,
    available_quantity INTEGER DEFAULT 0,
    FOREIGN KEY (product_id) REFERENCES product_classes(id)
);

CREATE TABLE IF NOT EXISTS order_slot_allocation (
    order_id INTEGER NOT NULL,
    slot_id INTEGER NOT NULL,
    capacity_reserved INTEGER NOT NULL,
    PRIMARY KEY (order_id, slot_id),
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (slot_id) REFERENCES time_slots(id)
);

CREATE TABLE IF NOT EXISTS order_item_slots (
    order_item_id INTEGER NOT NULL,
    slot_id INTEGER NOT NULL,
    allocated_capacity INTEGER NOT NULL,
    FOREIGN KEY (order_item_id) REFERENCES order_items(id),
    FOREIGN KEY (slot_id) REFERENCES time_slots(id)
);

CREATE TABLE IF NOT EXISTS refinement_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_class_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    label TEXT,
    image_url TEXT,
    required BOOLEAN NOT NULL DEFAULT 0,
    position INTEGER NOT NULL,
    FOREIGN KEY (product_class_id) REFERENCES product_classes (id)
);

CREATE TABLE IF NOT EXISTS refinements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    refinement_step_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    label TEXT,
    image_url TEXT,
    price_addition DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    active BOOLEAN NOT NULL DEFAULT 1,
    FOREIGN KEY (refinement_step_id) REFERENCES refinement_steps (id)
);

CREATE TABLE IF NOT EXISTS time_slot_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    interval_minutes INTEGER NOT NULL,
    capacity INTEGER NOT NULL,
    active BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS time_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    capacity INTEGER NOT NULL,
    used_capacity INTEGER NOT NULL DEFAULT 0
);

-- Tabelle für Benutzerrollen
CREATE TABLE IF NOT EXISTS user_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT
);

-- Tabelle für Berechtigungen
CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT
);

-- Tabelle für Rollen-Berechtigungen (welche Rolle hat welche Berechtigung)
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES user_roles(id),
    FOREIGN KEY (permission_id) REFERENCES permissions(id)
);

-- Erweiterung der users Tabelle um role_id
ALTER TABLE users ADD COLUMN role_id INTEGER REFERENCES user_roles(id);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    pickup_date TEXT NOT NULL,
    pickup_time TEXT NOT NULL,
    status TEXT NOT NULL,
    created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reminder_sent INTEGER DEFAULT 0,
    delayed INTEGER DEFAULT 0,
    delay_minutes INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_class_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders (id),
    FOREIGN KEY (product_class_id) REFERENCES product_classes (id)
);

CREATE TABLE IF NOT EXISTS order_item_refinements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_item_id INTEGER NOT NULL,
    refinement_id INTEGER NOT NULL,
    FOREIGN KEY (order_item_id) REFERENCES order_items (id),
    FOREIGN KEY (refinement_id) REFERENCES refinements (id)
);

-- Payment Settings Tabelle
CREATE TABLE IF NOT EXISTS payment_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paypal_enabled BOOLEAN NOT NULL DEFAULT 0,
    paypal_email TEXT,
    paypal_client_id TEXT,
    paypal_secret TEXT,
    paypal_mode TEXT DEFAULT 'sandbox',
    force_paypal BOOLEAN NOT NULL DEFAULT 0,
    allow_cash_payment BOOLEAN NOT NULL DEFAULT 1,
    created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Tabelle für orders erweitert um payment_method
ALTER TABLE orders ADD COLUMN payment_method TEXT DEFAULT 'cash';

-- ============================================
-- Produkt-Verfügbarkeitsregeln (Availability Rules)
-- ============================================

-- Haupt-Tabelle für Verfügbarkeitsregeln
CREATE TABLE IF NOT EXISTS availability_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    active BOOLEAN NOT NULL DEFAULT 1,
    -- Geltungsbereich: 'all' = alle Produkte, 'specific' = bestimmte Produkte
    scope TEXT NOT NULL DEFAULT 'all',
    -- Zeitliche Einschränkung
    start_date TEXT,  -- Format: YYYY-MM-DD (leer = kein Startdatum)
    end_date TEXT,    -- Format: YYYY-MM-DD (leer = kein Enddatum)
    start_time TEXT,  -- Format: HH:MM (leer = ganztägig)
    end_time TEXT,    -- Format: HH:MM (leer = ganztägig)
    -- Wochentage: 0 = Sonntag, 1 = Montag, etc. (leer = alle Tage)
    weekdays TEXT,   -- Komma-getrennte Liste, z.B. "1,2,3,4,5" für Mo-Fr
    -- Monatstage: 1-31 (leer = alle Tage)
    month_days TEXT,-- Komma-getrennte Liste
    -- Monate: 1-12 (leer = alle Monate)
    months TEXT,      -- Komma-getrennte Liste, z.B. "1,2,3,4,5,6,7,8,9,10,11,12"
    -- Verfügbare Menge (0 = nicht verfügbar, -1 = unbegrenzt)
    available_quantity INTEGER NOT NULL DEFAULT -1,
    priority INTEGER NOT NULL DEFAULT 0,  /* Höhere Priorität wird zuerst angewendet */
    created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Verbindungstabelle für spezifische Produkte pro Regel
CREATE TABLE IF NOT EXISTS availability_rule_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    product_class_id INTEGER NOT NULL,
    FOREIGN KEY (rule_id) REFERENCES availability_rules(id) ON DELETE CASCADE,
    FOREIGN KEY (product_class_id) REFERENCES product_classes(id) ON DELETE CASCADE,
    UNIQUE(rule_id, product_class_id)
);

-- ============================================
-- API-Schlüssel-Verwaltung
-- ============================================

CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    permissions TEXT NOT NULL DEFAULT 'read',
    rate_limit INTEGER NOT NULL DEFAULT 100,
    active BOOLEAN NOT NULL DEFAULT 1,
    expires_at TEXT,
    last_used TEXT,
    usage_count INTEGER NOT NULL DEFAULT 0,
    created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- API-Nutzungsstatistiken
CREATE TABLE IF NOT EXISTS api_usage_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key_id INTEGER NOT NULL,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    response_time_ms INTEGER NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (api_key_id) REFERENCES api_keys(id) ON DELETE CASCADE
);