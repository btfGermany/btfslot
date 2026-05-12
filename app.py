# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import sqlite3
import os
import random
import string
from werkzeug.utils import secure_filename
from functools import wraps
import time
import math
import pandas as pd
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestRegressor
import inspect
import uuid
from urllib.parse import quote  # Oben importieren


# Application setup
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['DATABASE'] = 'btf-pre.db'

# Login manager setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # 2MB Limit

# Ensure upload directories exist
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'class'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'ver'), exist_ok=True)

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Environment, FileSystemLoader

import os
from jinja2 import Environment, FileSystemLoader

def render_template_email(template_name, context):
    """Render a template with the given context and always include server_url"""
    # Setup Jinja2 environment
    template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))

    # Füge server_url zum Kontext hinzu (wenn nicht schon vorhanden)
    context = dict(context)  # sichere Kopie
    context.setdefault('server_url', 'http://192.168.178.79:1234')  # hier kannst du auch dynamisch setzen

    template = env.get_template(f"{template_name}.html")
    return template.render(**context)

@app.before_request
def restrict_debug_routes():
    if request.endpoint in ['search'] and not current_user.is_authenticated:
        return redirect(url_for('login'))
    if request.endpoint == 'search' and current_user.role != 'admin':
        flash("Zugriff verweigert", 'error')
        return redirect(url_for('index'))

def get_route_info():
    """Collect all route information including view functions"""
    routes = []
    for rule in app.url_map.iter_rules():
        if 'static' in rule.endpoint:
            continue

        func = app.view_functions[rule.endpoint]
        methods = list(rule.methods - {'HEAD', 'OPTIONS'})
        
        # Extract function metadata
        source_lines, _ = inspect.getsourcelines(func)
        source_code = ''.join(source_lines)
        docstring = func.__doc__ or ''
        
        routes.append({
            'endpoint': rule.endpoint,
            'path': str(rule),
            'methods': methods,
            'func_name': func.__name__,
            'params': list(rule.arguments),
            'doc': docstring.strip(),
            'source': source_code,
            'file': inspect.getfile(func)
        })
    return routes

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return redirect(url_for('dashboard'))
    
    conn = get_db_connection()
    fuzzy_query = f"%{query}%"
    
    # Existing queries for orders, products, and customers
    orders = conn.execute('''
        SELECT o.id, o.order_number, o.customer_name, o.pickup_date, o.pickup_time, o.status,
        GROUP_CONCAT(pc.name, ', ') AS products
        FROM orders o
        LEFT JOIN order_items oi ON o.id = oi.order_id
        LEFT JOIN product_classes pc ON oi.product_class_id = pc.id
        WHERE o.order_number LIKE ?
        OR o.customer_name LIKE ?
        OR o.customer_email LIKE ?
        GROUP BY o.id
        LIMIT 20
        ''', (fuzzy_query, fuzzy_query, fuzzy_query)).fetchall()
    
    products = conn.execute('''
        SELECT * FROM product_classes
        WHERE name LIKE ?
        OR description LIKE ?
        OR label LIKE ?
        LIMIT 20
        ''', (fuzzy_query, fuzzy_query, fuzzy_query)).fetchall()
    
    customers = conn.execute('''
        SELECT DISTINCT customer_name, customer_email, COUNT(*) as order_count
        FROM orders
        WHERE customer_name LIKE ?
        OR customer_email LIKE ?
        GROUP BY customer_email
        LIMIT 20
        ''', (fuzzy_query, fuzzy_query)).fetchall()
    
    # New query for time_slot_rules
    time_slots = conn.execute('''
        SELECT id, name, start_time, end_time, interval_minutes, capacity,
        min_processing_minutes, min_capacity_per_order, max_capacity_per_order, active
        FROM time_slot_rules
        WHERE name LIKE ?
        OR start_time LIKE ?
        OR end_time LIKE ?
        LIMIT 20
        ''', (fuzzy_query, fuzzy_query, fuzzy_query)).fetchall()
    
    # Translation mapping
    translations = {
        'bearbeiten': 'edit',
        'ändern': 'edit',
        'editieren': 'edit',
        'löschen': 'delete',
        'entfernen': 'remove',
        'hinzufügen': 'add',
        'neu': 'new',
        'erstellen': 'create',
        'verwalten': 'manage',
        'produkt': 'product',
        'kunde': 'customer',
        'bestellung': 'order',
        'zeitfenster': 'time slot',
        'kalender': 'calender',
        'nutzer': 'user', 
         'accounts': 'user', 
        'zeitslot': 'time slot'      
    }
    
    search_terms = [query.lower()]
    query_lower = query.lower()
    for ger, eng in translations.items():
        if ger in query_lower:
            search_terms.append(eng)
        if eng in query_lower:
            search_terms.append(ger)
    
    route_results = []
    if current_user.is_authenticated and current_user.role == 'admin':
        all_routes = get_route_info()
        for route in all_routes:
            search_fields = [
                str(route['path']).lower(),
                str(route['endpoint']).lower(),
                str(route['func_name']).lower(),
                ' '.join(str(p) for p in route['params']).lower(),
                str(route['doc']).lower() if route['doc'] else '',
                str(route['source']).lower()
            ]
            for term in search_terms:
                if any(term in field for field in search_fields):
                    route_results.append(route)
                    break
    
    conn.close()
    return render_template('admin/search_results.html',
                          query=query,
                          orders=orders,
                          products=products,
                          customers=customers,
                          time_slots=time_slots,  # Added time_slots to template context
                          routes=route_results)

@app.route('/api/search_suggestions')
def search_suggestions():
    """API endpoint that returns search suggestions based on the query parameter.
    Returns up to 6 suggestions combining results from orders, products, customers and time slots."""
    query = request.args.get('q', '').strip()
    
    if not query or len(query) < 2:
        return jsonify([])
    
    conn = get_db_connection()
    fuzzy_query = f"%{query}%"
    suggestions = []
    
    # Get order suggestions
    order_suggestions = conn.execute('''
        SELECT DISTINCT o.order_number as text, 'Bestellung' as type
        FROM orders o
        WHERE o.order_number LIKE ?
        LIMIT 2
    ''', (fuzzy_query,)).fetchall()
    
    for suggestion in order_suggestions:
        suggestions.append({
            'text': suggestion['text'],
            'type': suggestion['type'],
            'url': url_for('view_order', order_number=suggestion['text'])
        })
    
    # Get product suggestions - KORRIGIERT: 'manage_products' statt 'products'
    product_suggestions = conn.execute('''
    SELECT name as text, 'Produkt' as type
    FROM product_classes
    WHERE name LIKE ?
    LIMIT 2
    ''', (fuzzy_query,)).fetchall()

    
    for suggestion in product_suggestions:
        produkt_name = suggestion['text']
        encoded_name = quote(produkt_name)
        suggestions.append({
        'text': produkt_name,
        'type': suggestion['type'],
        'url': url_for('manage_products') + f'?produkt={encoded_name}'
    })
    
    # Get customer suggestions
    customer_suggestions = conn.execute('''
        SELECT DISTINCT customer_name as text, 'Kunde' as type
        FROM orders
        WHERE customer_name LIKE ?
        LIMIT 1
    ''', (fuzzy_query,)).fetchall()
    
    for suggestion in customer_suggestions:
        suggestions.append({
            'text': suggestion['text'],
            'type': suggestion['type'],
            'url': url_for('search') + f'?q={suggestion["text"]}'
        })
    
    # Get time slot suggestions - Prüfen Sie, ob 'time_slots' der richtige Endpunkt ist
    time_slot_suggestions = conn.execute('''
        SELECT name as text, 'Zeitfenster' as type
        FROM time_slot_rules
        WHERE name LIKE ?
        LIMIT 1
    ''', (fuzzy_query,)).fetchall()
    
    for suggestion in time_slot_suggestions:
        suggestions.append({
            'text': suggestion['text'],
            'type': suggestion['type'],
            'url': url_for('manage_time_slots')  # KORRIGIERTER ENDPUNKT - PRÜFEN
        })
    
    conn.close()
    
    # Return maximum 6 suggestions
    return jsonify(suggestions[:6])

def _similar_enough(str1, str2):
    """Simple function to check if two strings are similar enough (typo-tolerant)"""
    # For strings of different lengths, check if one is contained in the other
    if len(str1) < len(str2) and str1 in str2:
        return True
    if len(str2) < len(str1) and str2 in str1:
        return True
        
    # For strings of similar length, check character overlap
    if abs(len(str1) - len(str2)) <= 2:
        common_chars = 0
        for c in str1:
            if c in str2:
                common_chars += 1
        # If 70% or more characters match, consider them similar
        return common_chars >= 0.7 * max(len(str1), len(str2))
    
    return False
def send_email(subject, body, recipient, template_name=None, context=None):
    """
    Send an email with optional HTML template
    
    Args:
        subject (str): Email subject
        body (str): Plain text email body (fallback)
        recipient (str): Recipient email address
        template_name (str, optional): Name of the HTML template to use
        context (dict, optional): Context data for the template
    
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    config = load_config()
    if not config or 'email' not in config:
        return False
    
    sender_email = config['email']['address']
    sender_password = config['email']['password']
    
    msg = MIMEMultipart('alternative')
    msg['From'] = sender_email
    msg['To'] = recipient
    msg['Subject'] = subject
    
    # Attach plain text version
    msg.attach(MIMEText(body, 'plain'))
    
    # Attach HTML version if template is provided
    if template_name and context:
        html_content = render_template_email(template_name, context)
        msg.attach(MIMEText(html_content, 'html'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Fehler beim Senden der E-Mail: {e}")
        return False

# Usage examples with templates
def send_order_confirmation(order_number, customer_email):
    """Send order confirmation email"""
    subject = "Bestätigung Ihrer Bestellung"
    plain_body = f"Ihre Bestellung #{order_number} wurde erfolgreich aufgegeben."
    context = {
        'order_number': order_number,
        'customer_email': customer_email
    }
    return send_email(
        subject, 
        plain_body,
        customer_email,
        template_name="order_confirmation",
        context=context
    )

def send_pickup_reminder(order):
    """Send pickup reminder email"""
    subject = "Erinnerung an Ihre Abholung"
    plain_body = f"Guten Tag, dies ist eine Erinnerung an Ihre Abholung um {order['pickup_time']}."
    context = {
        'order': order
    }
    return send_email(
        subject,
        plain_body,
        order['customer_email'],
        template_name="pickup_reminder",
        context=context
    )

def send_delay_notification(order, delay_minutes, valid_delays):
    """Send delay notification email"""
    subject = "Verspätungsmeldung"
    plain_body = f"Ihre Bestellung #{order['order_number']} verzögert sich um {valid_delays[delay_minutes]} Minuten."
    context = {
        'order': order,
        'delay_minutes': delay_minutes,
        'delay_text': valid_delays[delay_minutes]
    }
    return send_email(
        subject,
        plain_body,
        order['customer_email'],
        template_name="delay_notification",
        context=context
    )  
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%d.%m.%Y %H:%M'):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value  # Ungültiges Format – gib es einfach zurück
    return value.strftime(format)

def extract_time_features(date_str, time_str):
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    time_obj = datetime.strptime(time_str, "%H:%M").time()
    
    return {
        'day_of_week': date_obj.weekday(),
        'month': date_obj.month,
        'day': date_obj.day,
        'hour': time_obj.hour,
        'minute': time_obj.minute
    }

# Funktion zum Laden und Vorbereiten der Daten
def prepare_data():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT date, start_time, end_time, capacity, used_capacity FROM time_slots", conn)
    conn.close()
    
    if len(df) < 30:  # Mindestens 30 Datenpunkte für eine vernünftige Vorhersage
        return None
    
    # Features aus Datum und Zeit extrahieren
    features = []
    for _, row in df.iterrows():
        time_features = extract_time_features(row['date'], row['start_time'])
        features.append(time_features)
    
    X = pd.DataFrame(features)
    y = df['used_capacity'] / df['capacity']  # Normalisierte Auslastung (0-1)
    
    return X, y

# Modell trainieren und Vorhersagen generieren
def generate_predictions():
    data = prepare_data()
    if data is None:
        return False
    
    X, y = data
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    # Vorhersagen für die nächsten 3 Tage generieren
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Vorhandene Zeitslots abrufen, um deren Muster zu kopieren
    cursor.execute("""
        SELECT DISTINCT start_time, end_time, capacity 
        FROM time_slots 
        ORDER BY start_time
    """)
    time_patterns = cursor.fetchall()
    
    # Bestehende Prognosen löschen
    cursor.execute("DELETE FROM time_slot_predictions")
    
    # Aktuelles Datum
    today = datetime.now().date()
    prediction_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Für die nächsten 3 Tage
    for day_offset in range(1, 4):
        future_date = today + timedelta(days=day_offset)
        date_str = future_date.strftime("%Y-%m-%d")
        
        # Für jedes Zeitmuster
        for pattern in time_patterns:
            start_time = pattern['start_time']
            end_time = pattern['end_time']
            capacity = pattern['capacity']
            
            # Features für die Vorhersage erstellen
            features = extract_time_features(date_str, start_time)
            features_df = pd.DataFrame([features])
            
            # Vorhersage machen
            prediction = model.predict(features_df)[0]
            predicted_capacity = int(prediction * capacity)  # Denormalisieren
            
            # In die Datenbank einfügen
            cursor.execute("""
                INSERT INTO time_slot_predictions (date, start_time, end_time, predicted_capacity, prediction_timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (date_str, start_time, end_time, predicted_capacity, prediction_timestamp))
    
    conn.commit()
    conn.close()
    return True

# Route zum Aktualisieren der Vorhersagen
@app.route('/update_predictions')
def update_predictions():
    success = generate_predictions()
    if success:
        return jsonify({"status": "success", "message": "Vorhersagen wurden aktualisiert"})
    else:
        return jsonify({"status": "error", "message": "Nicht genügend Daten für Vorhersagen vorhanden"})

@app.template_filter('strftime')
def _jinja2_filter_datetime(date, fmt=None):
    date_obj = datetime.strptime(date, '%Y-%m-%d')
    return date_obj.strftime(fmt or '%d.%m.%Y')

# Route zum Anzeigen der Vorhersagen
@app.route('/predictions')
def show_predictions():
    conn = get_db_connection()
    predictions = conn.execute('''
        SELECT date, start_time, end_time, predicted_capacity, prediction_timestamp 
        FROM time_slot_predictions 
        ORDER BY date, start_time
    ''').fetchall()
    conn.close()
    
    return render_template('admin/predictions.html', predictions=predictions)

@app.route('/calendar')
@login_required
def calendar_view():
    # Get date from query parameter or use today
    date_str = request.args.get('date')
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            selected_date = datetime.now()
    else:
        selected_date = datetime.now()
        
    # Format date for SQL query
    formatted_date = selected_date.strftime('%Y-%m-%d')
    current_date = datetime.now().date()
    
    # Check if selected date is in the future (max 3 days ahead)
    is_future_date = (selected_date.date() > current_date) and (selected_date.date() <= current_date + timedelta(days=3))
    
    conn = get_db_connection()
    
    # Get all upcoming slots
    slots = conn.execute('''
        SELECT ts.*,
        (SELECT SUM(allocated_capacity) FROM order_item_slots WHERE slot_id = ts.id) AS used_capacity
        FROM time_slots ts
        WHERE date >= date('now')
        ORDER BY date, start_time
    ''').fetchall()
    
    # Get slots for the selected day
    day_slots = conn.execute('''
        SELECT ts.*,
        (SELECT SUM(allocated_capacity) FROM order_item_slots WHERE slot_id = ts.id) AS used_capacity
        FROM time_slots ts
        WHERE date = ?
        ORDER BY start_time
    ''', (formatted_date,)).fetchall()
    
    # Convert sqlite3.Row objects to dictionaries
    slots = [dict(slot) for slot in slots]
    day_slots = [dict(slot) for slot in day_slots]
    
    # Get prediction data if the date is in the future (up to 3 days)
    prediction_data = None
    if is_future_date:
        prediction_data = conn.execute('''
            SELECT id AS prediction_id, date, start_time, end_time, predicted_capacity, prediction_timestamp
            FROM time_slot_predictions
            WHERE date = ?
            ORDER BY start_time
        ''', (formatted_date,)).fetchall()
        
        # Convert prediction data to dictionaries
        prediction_data = [dict(p) for p in prediction_data]
        
        # If we have predictions, merge them with day_slots
        if prediction_data:
            # Create a dictionary of predictions keyed by time
            predictions_by_time = {f"{p['start_time']}-{p['end_time']}": p for p in prediction_data}
            
            # Enhance day_slots with prediction data
            for slot in day_slots:
                time_key = f"{slot['start_time']}-{slot['end_time']}"
                if time_key in predictions_by_time:
                    slot['predicted_capacity'] = predictions_by_time[time_key]['predicted_capacity']
                    slot['prediction_timestamp'] = predictions_by_time[time_key]['prediction_timestamp']
    
    # Get slot assignments
    slot_assignments = {}
    all_slots = slots + [s for s in day_slots if s['id'] not in [slot['id'] for slot in slots]]
    
    for slot in all_slots:
        items = conn.execute('''
            SELECT oi.*, pc.name AS product_name, ois.allocated_capacity
            FROM order_item_slots ois
            JOIN order_items oi ON ois.order_item_id = oi.id
            JOIN product_classes pc ON oi.product_class_id = pc.id
            WHERE ois.slot_id = ?
        ''', (slot['id'],)).fetchall()
        
        # Convert items to dictionaries if you need to modify them
        items = [dict(item) for item in items]
        slot_assignments[slot['id']] = items
    
    conn.close()
    
    return render_template(
        'admin/calendar.html',
        slots=slots,
        day_slots=day_slots,
        slot_assignments=slot_assignments,
        selected_date=selected_date,
        timedelta=timedelta,
        now=datetime.now(),
        is_future_date=is_future_date,
        prediction_data=prediction_data,
        datetime=datetime  # Pass datetime module to template
    )

class User(UserMixin):
    def __init__(self, id, username, password, role):
        self.id = id
        self.username = username
        self.password = password
        self.role = role


    @staticmethod
    def get(user_id):
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        if user:
            return User(user['id'], user['username'], user['password'], user['role'])
        return None

import json
from pathlib import Path

# Config file path
CONFIG_FILE = 'config.json'

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

# Database functions
def get_db_connection():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

from functools import wraps
from flask import abort

def permission_required(permission_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            
            conn = get_db_connection()
            has_permission = conn.execute('''
                SELECT 1 FROM role_permissions rp
                JOIN permissions p ON rp.permission_id = p.id
                WHERE rp.role_id = ? AND p.name = ?
            ''', (current_user.role_id, permission_name)).fetchone()
            conn.close()
            
            if not has_permission:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def init_db():
    conn = get_db_connection()
    is_new_db = False
    
    try:
        # Prüfe ob Datenbank bereits initialisiert wurde
        users_table = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='users'
        """).fetchone()
        
        if users_table:
            # Datenbank existiert bereits - füge alle fehlende Tabellen hinzu
            with open('schema.sql', 'r') as f:
                schema_content = f.read()
            
            # Führe alle CREATE TABLE Statements aus
            statements = schema_content.split(';')
            tables_created = 0
            
            for stmt in statements:
                stmt = stmt.strip()
                if stmt.startswith('CREATE TABLE IF NOT EXISTS'):
                    try:
                        conn.execute(stmt + ';')
                        tables_created += 1
                    except:
                        pass
            
            conn.commit()
            print(f"Database check completed - {tables_created} tables processed")
        else:
            # Datenbank existiert nicht - erstelle sie komplett neu
            with open('schema.sql', 'r') as f:
                conn.executescript(f.read())
            print("Database schema created")
            is_new_db = True
        
        # Initiale Rollen und Berechtigungen erstellen falls neue DB
        if is_new_db:
            roles = conn.execute('SELECT COUNT(*) as count FROM user_roles').fetchone()
            if roles['count'] == 0:
                conn.execute('INSERT INTO user_roles (name, description) VALUES (?, ?)', ('admin', 'Vollzugriff'))
                conn.execute('INSERT INTO user_roles (name, description) VALUES (?, ?)', ('manager', 'Bestellverwaltung'))
                conn.execute('INSERT INTO user_roles (name, description) VALUES (?, ?)', ('terminal', 'Terminal'))
                
                permissions = [('manage_users', 'Benutzer verwalten'), ('manage_products', 'Produkte verwalten'),
                            ('manage_orders', 'Bestellungen verwalten'), ('access_terminal', 'Terminal'),
                            ('view_reports', 'Berichte'), ('manage_system', 'System')]
                conn.executemany('INSERT INTO permissions (name, description) VALUES (?, ?)', permissions)
                
                perms = conn.execute('SELECT id FROM permissions').fetchall()
                admin_role = conn.execute('SELECT id FROM user_roles WHERE name = "admin"').fetchone()
                for p in perms:
                    conn.execute('INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)', (admin_role['id'], p['id']))
                
                manager_role = conn.execute('SELECT id FROM user_roles WHERE name = "manager"').fetchone()
                for pn in ['manage_products', 'manage_orders', 'view_reports']:
                    p = conn.execute('SELECT id FROM permissions WHERE name = ?', (pn,)).fetchone()
                    if p:
                        conn.execute('INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)', (manager_role['id'], p['id']))
                
                term_role = conn.execute('SELECT id FROM user_roles WHERE name = "terminal"').fetchone()
                p = conn.execute('SELECT id FROM permissions WHERE name = "access_terminal"').fetchone()
                if p:
                    conn.execute('INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)', (term_role['id'], p['id']))
            
            # Admin erstellen falls nicht vorhanden
            admin = conn.execute('SELECT * FROM users WHERE username = "admin"').fetchone()
            if not admin:
                config = load_config()
                username = config.get('admin', {}).get('username', 'admin') if config else 'admin'
                password = config.get('admin', {}).get('password', '') if config else ''
                if not password:
                    password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
                    if config:
                        config['admin']['password'] = password
                    else:
                        config = {'admin': {'username': username, 'password': password}}
                    save_config(config)
                pw_hash = generate_password_hash(password)
                conn.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', (username, pw_hash, 'admin'))
                print(f"Admin created: {username}")
            
            conn.commit()
        
    except Exception as e:
        print(f"Database init error: {e}")
    finally:
        conn.close()

@app.route('/admin/users')
@login_required
def manage_users():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users').fetchall()
    conn.close()
    return render_template('admin/users.html', users=users)

# Route zum Erstellen neuer Benutzer
@app.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        if not username or not password:
            flash('Benutzername und Passwort sind erforderlich')
            return redirect(url_for('add_user'))
        conn = get_db_connection()
        existing_user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if existing_user:
            flash('Benutzername existiert bereits')
            conn.close()
            return redirect(url_for('add_user'))
        hashed_password = generate_password_hash(password)
        conn.execute(
            'INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
            (username, hashed_password, role)
        )
        conn.commit()
        conn.close()
        flash('Benutzer erfolgreich erstellt')
        return redirect(url_for('manage_users'))
    return render_template('admin/add_user.html')

# Route zum Bearbeiten von Benutzern
@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    if user is None:
        conn.close()
        flash('Benutzer nicht gefunden')
        return redirect(url_for('manage_users'))
    
    if request.method == 'POST':
        username = request.form['username']
        role = request.form['role']
        new_password = request.form.get('new_password')
        
        if not username:
            flash('Benutzername ist erforderlich')
            conn.close()
            return redirect(url_for('edit_user', user_id=user_id))
        
        # Überprüfen, ob der neue Benutzername bereits existiert (außer für diesen Benutzer selbst)
        existing_user = conn.execute('SELECT * FROM users WHERE username = ? AND id != ?', 
                                 (username, user_id)).fetchone()
        if existing_user:
            flash('Benutzername existiert bereits')
            conn.close()
            return redirect(url_for('edit_user', user_id=user_id))
        
        # Wenn ein neues Passwort angegeben wurde, aktualisiere es
        if new_password:
            hashed_password = generate_password_hash(new_password)
            conn.execute(
                'UPDATE users SET username = ?, password = ?, role = ? WHERE id = ?',
                (username, hashed_password, role, user_id)
            )
        else:
            # Nur Benutzername und Rolle aktualisieren
            conn.execute(
                'UPDATE users SET username = ?, role = ? WHERE id = ?',
                (username, role, user_id)
            )
        
        conn.commit()
        conn.close()
        flash('Benutzer erfolgreich aktualisiert')
        return redirect(url_for('manage_users'))
    
    conn.close()
    return render_template('admin/edit_user.html', user=user)

# Route zum Löschen von Benutzern
@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    # Verhindern, dass der eingeloggte Admin sich selbst löscht
    if user_id == current_user.id:
        flash('Sie können Ihren eigenen Account nicht löschen')
        return redirect(url_for('manage_users'))
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    if user is None:
        conn.close()
        flash('Benutzer nicht gefunden')
        return redirect(url_for('manage_users'))
    
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    flash('Benutzer erfolgreich gelöscht')
    return redirect(url_for('manage_users'))


# Stelle sicher, dass die Datenbank existiert und initialisiert ist
if not Path(app.config['DATABASE']).exists():
    init_db()
    print("Database created and initialized")
else:
    print("Database already exists")
@app.cli.command('init-db')
def init_db_command():
    init_db()
    print('Database initialized.')

# Login handlers
@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            user_obj = User(user['id'], user['username'], user['password'], user['role'])
            login_user(user_obj)
            return redirect(url_for('dashboard'))
        
        flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Admin routes
from flask import render_template, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, timedelta

@app.route('/admin/dashboard')
@login_required
def dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('index'))

    conn = get_db_connection()

    # Top Suchanfragen
    top_searches = conn.execute('''
        SELECT search_query, COUNT(*) as count 
        FROM search_logs 
        GROUP BY search_query 
        ORDER BY count DESC 
        LIMIT 10
    ''').fetchall()

    # Top verkaufte Produkte
    top_products = conn.execute('''
        SELECT pc.id, pc.name, SUM(oi.quantity) as total 
        FROM order_items oi
        JOIN product_classes pc ON oi.product_class_id = pc.id
        GROUP BY pc.id 
        ORDER BY total DESC 
        LIMIT 10
    ''').fetchall()

    # Slot-Auslastung heute
    today = datetime.now().strftime('%Y-%m-%d')
    slot_usage = conn.execute('''
        SELECT *, 
        (used_capacity * 100.0 / capacity) as usage_percent 
        FROM time_slots 
        WHERE date = ?
    ''', (today,)).fetchall()

    # Produkte mit geringster Verfügbarkeit
    low_availability = conn.execute('''
        SELECT pc.id, pc.name,
        COALESCE(pda.available_quantity, pc.capacity) as available
        FROM product_classes pc
        LEFT JOIN product_daily_availability pda
        ON pc.id = pda.product_id AND pda.date = ?
        ORDER BY available ASC
        LIMIT 10
    ''', (today,)).fetchall()

    # Neueste Bestellungen
    recent_orders = conn.execute('''
        SELECT * FROM orders 
        ORDER BY created DESC 
        LIMIT 10
    ''').fetchall()

    # Aktueller Slot
    now = datetime.now().strftime('%H:%M')
    current_slot = conn.execute('''
        SELECT *, 
        (used_capacity * 100.0 / capacity) as usage_percent 
        FROM time_slots 
        WHERE date = ? AND start_time <= ? AND end_time > ?
    ''', (today, now, now)).fetchone()

    # Umsatzdaten (letzte 30 Tage)
    revenue_data = conn.execute('''
        SELECT DATE(o.created) as day, 
               SUM(oi.quantity * pc.base_price + 
                   COALESCE((SELECT SUM(r.price_addition) 
                             FROM order_item_refinements oir 
                             JOIN refinements r ON oir.refinement_id = r.id 
                             WHERE oir.order_item_id = oi.id), 0)) as total
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN product_classes pc ON oi.product_class_id = pc.id
        WHERE o.status = 'completed'
        GROUP BY day
        ORDER BY day DESC
        LIMIT 30
    ''').fetchall()

    # Statusverteilung
    status_distribution = conn.execute('''
        SELECT status, COUNT(*) as count 
        FROM orders 
        GROUP BY status
    ''').fetchall()


    # Kommende Slots für morgen
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    upcoming_slots = conn.execute('''
        SELECT *, 
        (used_capacity * 100.0 / capacity) as usage_percent 
        FROM time_slots 
        WHERE date = ?
    ''', (tomorrow,)).fetchall()

    # Beliebteste Verfeinerungen
    popular_refinements = conn.execute('''
        SELECT r.name, COUNT(*) as count 
        FROM order_item_refinements oir
        JOIN refinements r ON oir.refinement_id = r.id
        GROUP BY r.id
        ORDER BY count DESC
        LIMIT 10
    ''').fetchall()

    conn.close()

    return render_template(
        'admin/dashboard.html',
        top_searches=top_searches,
        top_products=top_products,
        slot_usage=slot_usage,
        low_availability=low_availability,
        recent_orders=recent_orders,
        current_slot=current_slot,
        revenue_data=revenue_data,
        status_distribution=status_distribution,
        
        upcoming_slots=upcoming_slots,
        popular_refinements=popular_refinements,
        today=today
    )
# Product management
@app.route('/admin/products')
@login_required
def manage_products():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    product_classes = conn.execute('SELECT * FROM product_classes WHERE deleted = 0').fetchall()
    conn.close()
    
    return render_template('admin/products.html', product_classes=product_classes)

@app.route('/admin/generate-today-slots', methods=['POST'])
@login_required
def generate_today_slots():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db_connection()
    
    # Check existing slots
    existing = conn.execute('SELECT COUNT(*) FROM time_slots WHERE date = ?', (today,)).fetchone()[0]
    if existing > 0:
        flash('Slots für heute existieren bereits', 'warning')
        return redirect(url_for('dashboard'))
    
    # Get default rule
    rule = conn.execute('SELECT * FROM time_slot_rules WHERE is_default = 1').fetchone()
    if not rule:
        flash('Keine Standard-Slot-Regel gefunden', 'error')
        return redirect(url_for('dashboard'))
    
    # Generate slots
    start_time = datetime.strptime(rule['start_time'], '%H:%M')
    end_time = datetime.strptime(rule['end_time'], '%H:%M')
    interval = timedelta(minutes=rule['interval_minutes'])
    current = start_time
    
    while current < end_time:
        next_time = current + interval
        conn.execute(
            'INSERT INTO time_slots (date, start_time, end_time, capacity) VALUES (?, ?, ?, ?)',
            (today, current.strftime('%H:%M'), next_time.strftime('%H:%M'), rule['capacity'])
        )
        current = next_time
    
    conn.commit()
    conn.close()
    flash('Slots für heute erfolgreich generiert', 'success')
    return redirect(url_for('dashboard'))

@app.route('/admin/products/add', methods=['GET', 'POST'])
@login_required
def add_product_class():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Pflichtfelder
        name = request.form['name']
        base_price = float(request.form['base_price'])
        capacity = int(request.form['capacity'])
        product_type = request.form['product_type']
        
        # Optionale Felder
        description = request.form.get('description', '')
        label = request.form.get('label', '')
        active = 1 if 'active' in request.form else 0
        image_url = None

        # Bildupload verarbeiten
        if 'image' in request.files:
            file = request.files['image']
            if file.filename != '':
                # Sicherer Dateiname mit Produktname
                filename = f"{secure_filename(name.lower().replace(' ', '-'))}.png"
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'class', filename)
                file.save(upload_path)
                image_url = f'uploads/class/{filename}'

        conn = get_db_connection()
        conn.execute(
            '''INSERT INTO product_classes (
                name, 
                description, 
                base_price, 
                capacity, 
                product_type, 
                label, 
                image_url, 
                active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (name, description, base_price, capacity, product_type, label, image_url, active)
        )
        conn.commit()
        conn.close()
        
        return redirect(url_for('manage_products'))
    
    return render_template('admin/add_product_class.html')

import unicodedata

import unicodedata
import re

def normalize_filename(name):
    # Kleinbuchstaben
    name = name.lower()
    
    # Umlaute und Sonderzeichen in ASCII konvertieren
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    
    # Kommazahlen finden und in passende Form bringen: "0,5" -> "05"
    name = re.sub(r'(\d),(\d)', r'\1\2', name)

    # Leerzeichen durch Unterstriche ersetzen (optional, falls du das nicht willst, einfach weglassen)
    name = name.replace(" ", "-")

    # Alle übrigen unerwünschten Zeichen entfernen (nur Buchstaben, Ziffern, Unterstrich und Minus erlaubt)
    name = re.sub(r'[^a-z0-9_-]', '', name)

    return name

app.jinja_env.filters['normalize_filename'] = normalize_filename

@app.route('/admin/products/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_product_class(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    product_class = conn.execute('SELECT * FROM product_classes WHERE id = ?', (id,)).fetchone()
    
    if not product_class:
        conn.close()
        flash('Product not found', 'error')
        return redirect(url_for('manage_products'))
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        base_price = float(request.form['base_price'])
        capacity = int(request.form['capacity'])
        product_type = request.form['product_type']
        label = request.form.get('label', '')
        active = 1 if 'active' in request.form else 0
        
        # Handle image management
        image_url = product_class['image_url']
        
        # Check if user wants to remove the current image
        if 'remove_image' in request.form and image_url:
            # Delete the physical file if it exists
            old_path = os.path.join(app.static_folder, image_url)
            if os.path.exists(old_path):
                os.remove(old_path)
            image_url = None
        
        # Check if a new image is being uploaded
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '':
                # Delete the old image if it exists and we're not already removing it
                if image_url and 'remove_image' not in request.form:
                    old_path = os.path.join(app.static_folder, image_url)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                
                # Create a safe filename with timestamp to avoid caching issues
                filename = secure_filename(f"{name.lower().replace(' ', '-')}.png")
                upload_folder = os.path.join(app.static_folder, 'uploads', 'class')
                
                # Ensure upload directory exists
                os.makedirs(upload_folder, exist_ok=True)
                
                # Save the new image
                upload_path = os.path.join(upload_folder, filename)
                file.save(upload_path)
                image_url = f'uploads/class/{filename}'
        
        # Update the database record
        conn.execute(
            '''UPDATE product_classes SET
                name = ?, 
                description = ?,
                base_price = ?,
                capacity = ?,
                product_type = ?,
                label = ?,
                image_url = ?,
                active = ?
                WHERE id = ?''',
            (name, description, base_price, capacity, product_type, label, image_url, active, id)
        )
        conn.commit()
        conn.close()
        
        flash('Product updated successfully', 'success')
        return redirect(url_for('manage_products'))
    
    conn.close()
    return render_template('admin/edit_product_class.html', product_class=product_class)
@app.route('/admin/products/<int:id>/delete', methods=['POST'])
@login_required
def delete_product_class(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    conn.execute('UPDATE product_classes SET deleted = 1 WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('manage_products'))

@app.route('/admin/products/<int:id>/toggle-active', methods=['POST'])
@login_required
def toggle_product_active(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    product = conn.execute('SELECT active FROM product_classes WHERE id = ?', (id,)).fetchone()
    new_active = 0 if product['active'] == 1 else 1
    
    conn.execute('UPDATE product_classes SET active = ? WHERE id = ?', (new_active, id))
    conn.commit()
    conn.close()
    
    return redirect(url_for('manage_products'))

# Refinement steps management
@app.route('/admin/products/<int:product_id>/refinements')
@login_required
def manage_refinement_steps(product_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM product_classes WHERE id = ?', (product_id,)).fetchone()
    steps = conn.execute('SELECT * FROM refinement_steps WHERE product_class_id = ? ORDER BY position', 
                        (product_id,)).fetchall()
    conn.close()
    
    return render_template('admin/refinement_steps.html', product=product, steps=steps)

@app.route('/admin/refinement_steps/<int:step_id>/refinements/add', methods=['GET', 'POST'])
@login_required
def add_refinement(step_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Formularverarbeitung
        name = request.form['name']
        price_addition = float(request.form['price_addition'])
        active = 1 if 'active' in request.form else 0
        label = request.form.get('label', '')
        image_url = None

        if 'image' in request.files:
            file = request.files['image']
            if file.filename != '':
                # Sicherer Dateiname mit Verfeinerungsname
                filename = f"{secure_filename(name.lower().replace(' ', '-'))}.png"
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'ver', filename)
                file.save(upload_path)
                image_url = f'uploads/ver/{filename}'

        conn = get_db_connection()
        conn.execute(
            '''INSERT INTO refinements (
                refinement_step_id,
                name,
                label,
                image_url,
                price_addition,
                active
            ) VALUES (?, ?, ?, ?, ?, ?)''',
            (step_id, name, label, image_url, price_addition, active)
        )
        conn.commit()
        conn.close()
        
        return redirect(url_for('manage_refinements', step_id=step_id))
    
    # GET-Request: Formular anzeigen
    return render_template('admin/add_refinement.html', step_id=step_id)

@app.route('/admin/refinements/<int:refinement_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_refinement(refinement_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    refinement = conn.execute('SELECT * FROM refinements WHERE id = ?', (refinement_id,)).fetchone()
    
    if not refinement:
        conn.close()
        flash('Option not found', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form['name']
        price_addition = float(request.form['price_addition'])
        active = 1 if 'active' in request.form else 0
        label = request.form.get('label', '')
        
        # Handle image management
        image_url = refinement['image_url']
        
        # Check if user wants to remove the current image
        if 'remove_image' in request.form and image_url:
            # Delete the physical file if it exists
            old_path = os.path.join(app.static_folder, image_url)
            if os.path.exists(old_path):
                os.remove(old_path)
            image_url = None
        
        # Check if a new image is being uploaded
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '':
                # Delete the old image if it exists and we're not already removing it
                if image_url and 'remove_image' not in request.form:
                    old_path = os.path.join(app.static_folder, image_url)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                
                # Create a safe filename with timestamp to avoid caching issues
                filename = secure_filename(f"{name.lower().replace(' ', '-')}.png")
                upload_folder = os.path.join(app.static_folder, 'uploads', 'ver')
                
                # Ensure upload directory exists
                os.makedirs(upload_folder, exist_ok=True)
                
                # Save the new image
                upload_path = os.path.join(upload_folder, filename)
                file.save(upload_path)
                image_url = f'uploads/ver/{filename}'
        
        # Update the database record
        conn.execute(
            '''UPDATE refinements SET
                name = ?,
                price_addition = ?,
                active = ?,
                label = ?,
                image_url = ?
                WHERE id = ?''',
            (name, price_addition, active, label, image_url, refinement_id)
        )
        conn.commit()
        
        step_id = refinement['refinement_step_id']
        conn.close()
        
        flash('Option updated successfully', 'success')
        return redirect(url_for('manage_refinements', step_id=step_id))
    
    conn.close()
    return render_template('admin/edit_refinement.html', refinement=refinement)
# Refinements management
@app.route('/admin/refinement_steps/<int:step_id>/refinements')
@login_required
def manage_refinements(step_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    step = conn.execute('SELECT * FROM refinement_steps WHERE id = ?', (step_id,)).fetchone()
    refinements = conn.execute('SELECT * FROM refinements WHERE refinement_step_id = ?', (step_id,)).fetchall()
    product = conn.execute('SELECT * FROM product_classes WHERE id = ?', (step['product_class_id'],)).fetchone()
    conn.close()
    
    return render_template('admin/refinements.html', step=step, refinements=refinements, product=product)

@app.route('/admin/refinement_steps/<int:step_id>/delete', methods=['POST'])
@login_required
def delete_refinement_step(step_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    step = conn.execute('SELECT product_class_id FROM refinement_steps WHERE id = ?', (step_id,)).fetchone()
    product_id = step['product_class_id']
    
    conn.execute('DELETE FROM refinement_steps WHERE id = ?', (step_id,))
    conn.execute('DELETE FROM refinements WHERE refinement_step_id = ?', (step_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('manage_refinement_steps', product_id=product_id))

@app.route('/admin/products/<int:product_id>/refinement_steps/add', methods=['GET', 'POST'])
@login_required
def add_refinement_step(product_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form['name']
        type = request.form['type']
        label = request.form.get('label', '')
        position = int(request.form.get('position', 1))
        required = 1 if 'required' in request.form else 0
        image_url = None
        
        # Handle image upload if present
        if 'image' in request.files:
            file = request.files['image']
            if file.filename != '':
                # Create secure filename based on step name
                filename = f"{secure_filename(name.lower().replace(' ', '-'))}.png"
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'step', filename)
                file.save(upload_path)
                image_url = f'uploads/step/{filename}'
        
        conn = get_db_connection()
        conn.execute(
            '''INSERT INTO refinement_steps (
                product_class_id,
                name,
                type,
                label,
                image_url,
                required,
                position
            ) VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (product_id, name, type, label, image_url, required, position)
        )
        conn.commit()
        conn.close()
        
        return redirect(url_for('manage_refinement_steps', product_id=product_id))
    
    return render_template('admin/add_refinement_step.html', product_id=product_id)

@app.route('/admin/refinement_steps/<int:step_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_refinement_step(step_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    step = conn.execute('SELECT * FROM refinement_steps WHERE id = ?', (step_id,)).fetchone()
    
    if not step:
        conn.close()
        flash('Refinement step not found', 'error')
        return redirect(url_for('manage_products'))
    
    product_id = step['product_class_id']
    
    if request.method == 'POST':
        name = request.form['name']
        type = request.form['type']
        label = request.form.get('label', '')
        position = int(request.form.get('position', 1))
        required = 1 if 'required' in request.form else 0
        
        # Handle image upload
        image_url = step['image_url']
        if 'image' in request.files:
            file = request.files['image']
            if file.filename != '':
                # Delete old image if exists
                if image_url:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], image_url.replace('uploads/', ''))
                    if os.path.exists(old_path):
                        os.remove(old_path)
                
                # Save new image
                filename = f"{secure_filename(name.lower().replace(' ', '-'))}.png"
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'step', filename)
                file.save(upload_path)
                image_url = f'uploads/step/{filename}'
        
        conn.execute(
            '''UPDATE refinement_steps SET 
                name = ?, 
                type = ?, 
                label = ?, 
                image_url = ?, 
                required = ?, 
                position = ?
            WHERE id = ?''',
            (name, type, label, image_url, required, position, step_id)
        )
        conn.commit()
        conn.close()
        
        return redirect(url_for('manage_refinement_steps', product_id=product_id))
    
    conn.close()
    return render_template('admin/edit_refinement_step.html', step=step)

@app.route('/admin/refinements/<int:refinement_id>/delete', methods=['POST'])
@login_required
def delete_refinement(refinement_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    refinement = conn.execute('SELECT refinement_step_id FROM refinements WHERE id = ?', (refinement_id,)).fetchone()
    step_id = refinement['refinement_step_id']
    
    conn.execute('DELETE FROM refinements WHERE id = ?', (refinement_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('manage_refinements', step_id=step_id))

@app.route('/admin/refinements/<int:refinement_id>/toggle-active', methods=['POST'])
@login_required
def toggle_refinement_active(refinement_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    refinement = conn.execute('SELECT * FROM refinements WHERE id = ?', (refinement_id,)).fetchone()
    new_active = 0 if refinement['active'] == 1 else 1
    
    conn.execute('UPDATE refinements SET active = ? WHERE id = ?', (new_active, refinement_id))
    conn.commit()
    
    step_id = refinement['refinement_step_id']
    conn.close()
    
    return redirect(url_for('manage_refinements', step_id=step_id))

# Time slot management
@app.route('/admin/time-slots')
@login_required
def manage_time_slots():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    time_rules = conn.execute('SELECT * FROM time_slot_rules').fetchall()
    
    # Get slots for today
    today = datetime.now().strftime('%Y-%m-%d')
    slots = conn.execute(
        'SELECT * FROM time_slots WHERE date = ? ORDER BY start_time',
        (today,)
    ).fetchall()
    
    conn.close()
    
    return render_template('admin/time_slots.html', time_rules=time_rules, slots=slots, current_date=today)

@app.route('/admin/time-slots/rules/add', methods=['GET', 'POST'])
@login_required
def add_time_rule():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form['name']
        start_time = request.form['start_time']
        end_time = request.form['end_time']
        interval_minutes = int(request.form['interval_minutes'])
        capacity = int(request.form['capacity'])
        min_processing = int(request.form.get('min_processing_minutes', 0))
        min_capacity = int(request.form.get('min_capacity_per_order', 0))
        max_capacity = int(request.form.get('max_capacity_per_order', 0))
        active = 1 if 'active' in request.form else 0
        
        conn = get_db_connection()
        conn.execute(
            '''INSERT INTO time_slot_rules 
            (name, start_time, end_time, interval_minutes, capacity, 
             min_processing_minutes, min_capacity_per_order, max_capacity_per_order, active) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (name, start_time, end_time, interval_minutes, capacity, 
             min_processing, min_capacity, max_capacity, active)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('manage_time_slots'))
    
    return render_template('admin/add_time_rule.html')

@app.route('/admin/time-slots/rules/<int:rule_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_time_rule(rule_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    rule = conn.execute('SELECT * FROM time_slot_rules WHERE id = ?', (rule_id,)).fetchone()
    
    if request.method == 'POST':
        name = request.form['name']
        start_time = request.form['start_time']
        end_time = request.form['end_time']
        interval_minutes = int(request.form['interval_minutes'])
        capacity = int(request.form['capacity'])
        min_processing = int(request.form.get('min_processing_minutes', 0))
        min_capacity = int(request.form.get('min_capacity_per_order', 0))
        max_capacity = int(request.form.get('max_capacity_per_order', 0))
        active = 1 if 'active' in request.form else 0
        
        conn.execute(
            '''UPDATE time_slot_rules SET 
            name = ?, start_time = ?, end_time = ?, interval_minutes = ?, capacity = ?,
            min_processing_minutes = ?, min_capacity_per_order = ?, max_capacity_per_order = ?, active = ?
            WHERE id = ?''',
            (name, start_time, end_time, interval_minutes, capacity,
             min_processing, min_capacity, max_capacity, active, rule_id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('manage_time_slots'))
    
    conn.close()
    return render_template('admin/edit_time_rule.html', rule=rule)
@app.route('/admin/time-slots/rules/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_time_rule(rule_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    conn.execute('DELETE FROM time_slot_rules WHERE id = ?', (rule_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('manage_time_slots'))

@app.route('/admin/time-slots/generate', methods=['POST'])
@login_required
def generate_time_slots():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    date = request.form['date']
    rule_id = request.form['rule_id']
    
    conn = get_db_connection()
    rule = conn.execute('SELECT * FROM time_slot_rules WHERE id = ?', (rule_id,)).fetchone()
    
    # Check if slots already exist for this date
    existing = conn.execute('SELECT COUNT(*) as count FROM time_slots WHERE date = ?', (date,)).fetchone()
    if existing['count'] > 0:
        flash('Time slots already exist for this date. Delete them first if you want to regenerate.')
        conn.close()
        return redirect(url_for('manage_time_slots'))
    
    # Generate time slots
    start_time = datetime.strptime(f"{date} {rule['start_time']}", '%Y-%m-%d %H:%M')
    end_time = datetime.strptime(f"{date} {rule['end_time']}", '%Y-%m-%d %H:%M')
    current = start_time
    
    while current < end_time:
        next_time = current + timedelta(minutes=rule['interval_minutes'])
        
        if next_time > end_time:
            break
        
        conn.execute(
            'INSERT INTO time_slots (date, start_time, end_time, capacity, used_capacity) VALUES (?, ?, ?, ?, 0)',
            (
                date, 
                current.strftime('%H:%M'),
                next_time.strftime('%H:%M'),
                rule['capacity']
            )
        )
        
        current = next_time
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('manage_time_slots'))

@app.route('/admin/time-slots/<date>/view')
@login_required
def view_time_slots(date):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    slots = conn.execute(
        'SELECT * FROM time_slots WHERE date = ? ORDER BY start_time',
        (date,)
    ).fetchall()
    conn.close()
    
    return render_template('admin/view_time_slots.html', slots=slots, date=date)

@app.route('/admin/time-slots/<date>/delete', methods=['POST'])
@login_required
def delete_date_slots(date):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    conn.execute('DELETE FROM time_slots WHERE date = ?', (date,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('manage_time_slots'))

@app.route('/')
def index():
    conn = get_db_connection()
    today = datetime.now().date().isoformat()
    
    # Get filter parameters from request
    product_type = request.args.get('type', '')
    min_price = request.args.get('min_price', '')
    max_price = request.args.get('max_price', '')
    search_query = request.args.get('search', '')
    sort_by = request.args.get('sort', 'created_desc')  # Default sort by newest
    
    # Base query
    query = '''SELECT pc.*, 
                COALESCE(pda.available_quantity, -1) as available_today
            FROM product_classes pc
            LEFT JOIN product_daily_availability pda 
                ON pc.id = pda.product_id AND pda.date = ?
            WHERE pc.active = 1 AND pc.deleted = 0'''
    
    params = [today]
    
    # Add filters to query
    if product_type:
        query += ' AND pc.product_type = ?'
        params.append(product_type)
    
    if min_price and min_price.replace('.', '', 1).isdigit():
        query += ' AND pc.base_price >= ?'
        params.append(float(min_price))
    
    if max_price and max_price.replace('.', '', 1).isdigit():
        query += ' AND pc.base_price <= ?'
        params.append(float(max_price))
    
    if search_query:
        query += ' AND (pc.name LIKE ? OR pc.description LIKE ?)'
        search_term = f'%{search_query}%'
        params.append(search_term)
        params.append(search_term)
        
        # Log search query if it exists
        log_search_query(search_query)
    
    # Add sorting
    if sort_by == 'price_asc':
        query += ' ORDER BY pc.base_price ASC'
    elif sort_by == 'price_desc':
        query += ' ORDER BY pc.base_price DESC'
    elif sort_by == 'name_asc':
        query += ' ORDER BY pc.name ASC'
    elif sort_by == 'name_desc':
        query += ' ORDER BY pc.name DESC'
    else:  # Default sorting by creation date (newest first)
        query += ' ORDER BY pc.created DESC'
    
    product_classes = conn.execute(query, params).fetchall()
    
    # Get all unique product types for filter dropdown
    product_types = conn.execute(
        '''SELECT DISTINCT product_type FROM product_classes 
           WHERE active = 1 AND deleted = 0'''
    ).fetchall()
    
    conn.close()
    
    return render_template('shop/index.html', 
                          product_classes=product_classes,
                          product_types=product_types,
                          current_filters={
                              'type': product_type,
                              'min_price': min_price,
                              'max_price': max_price,
                              'search': search_query,
                              'sort': sort_by
                          })

def log_search_query(search_query):
    """Log search queries with timestamp and IP address"""
    conn = get_db_connection()
    
    # Get user IP address
    user_ip = request.remote_addr
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Create the search_logs table if it doesn't exist
    conn.execute('''
        CREATE TABLE IF NOT EXISTS search_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            search_query TEXT NOT NULL,
            user_ip TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')
    
    # Insert search log entry
    conn.execute(
        'INSERT INTO search_logs (search_query, user_ip, timestamp) VALUES (?, ?, ?)',
        (search_query, user_ip, timestamp)
    )
    
    conn.commit()
    conn.close()

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    conn = get_db_connection()
    product = conn.execute(
        '''SELECT * FROM product_classes 
        WHERE id = ? AND active = 1 AND deleted = 0''',
        (product_id,)
    ).fetchone()
    
    if not product:
        conn.close()
        return redirect(url_for('index'))
    
    steps = conn.execute(
        '''SELECT * FROM refinement_steps 
        WHERE product_class_id = ? 
        ORDER BY position''',
        (product_id,)
    ).fetchall()
    
    step_refinements = {}
    for step in steps:
        refinements = conn.execute(
            '''SELECT * FROM refinements 
            WHERE refinement_step_id = ? AND active = 1''',
            (step['id'],)
        ).fetchall()
        step_refinements[step['id']] = refinements
    
    conn.close()
    return render_template(
        'shop/product_detail.html',
        product=product,
        steps=steps,
        step_refinements=step_refinements
    )

@app.route('/cart/update_quantity/<int:index>/<string:change>', methods=['POST'])
def update_quantity(index, change):
    if 'cart' in session and 0 <= index < len(session['cart']):
        if change == 'increase':
            # Check if more items are available before increasing
            product_id = session['cart'][index]['product_id']
            new_quantity = session['cart'][index]['quantity'] + 1
            
            today = datetime.now().date().isoformat()
            conn = get_db_connection()
            available = conn.execute(
                'SELECT available_quantity FROM product_daily_availability WHERE product_id = ? AND date = ?',
                (product_id, today)
            ).fetchone()
            
            max_available = available['available_quantity'] if available else None
            
            if max_available is not None:
                total_in_cart = sum(item['quantity'] for item in session['cart'] if item['product_id'] == product_id)
                if total_in_cart - session['cart'][index]['quantity'] + new_quantity <= max_available:
                    session['cart'][index]['quantity'] = new_quantity
                    session.modified = True
                else:
                    flash('Gewünschte Menge nicht verfügbar', 'error')
            else:
                session['cart'][index]['quantity'] = new_quantity
                session.modified = True
                
        elif change == 'decrease' and session['cart'][index]['quantity'] > 1:
            session['cart'][index]['quantity'] -= 1
            session.modified = True
    
    return redirect(url_for('cart'))
@app.route('/cart/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'cart' not in session:
        session['cart'] = []
    
    # Formulardaten verarbeiten
    quantity = int(request.form['quantity'])
    refinements = {}

    today = datetime.now().date().isoformat()
    conn = get_db_connection()
    available = conn.execute(
        'SELECT available_quantity FROM product_daily_availability WHERE product_id = ? AND date = ?',
        (product_id, today)
    ).fetchone()
    
    max_available = available['available_quantity'] if available else None
    
    if max_available is not None:
        total_in_cart = sum(item['quantity'] for item in session['cart'] if item['product_id'] == product_id)
        if total_in_cart + quantity > max_available:
            flash('Gewünschte Menge nicht verfügbar', 'error')
            return redirect(url_for('product_detail', product_id=product_id))
        
    # Verfeinerungen sammeln
    for key in request.form:
        if key.startswith('refinement_'):
            step_id = key.split('_')[1]
            refinements[step_id] = request.form.getlist(key)  # Unterstützt Mehrfachauswahl

    # Produktdaten aus der DB holen
    conn = get_db_connection()
    product = conn.execute('''
        SELECT id, name, base_price, capacity 
        FROM product_classes 
        WHERE id = ?''', (product_id,)).fetchone()
    
    if not product:
        flash('Produkt nicht gefunden')
        return redirect(url_for('index'))

    # Cart-Item erstellen
    cart_item = {
        'product_id': product_id,
        'quantity': quantity,
        'refinements': refinements,
        'base_price': float(product['base_price'])
    }

    session['cart'].append(cart_item)
    session.modified = True
    flash('Artikel wurde zum Warenkorb hinzugefügt')
    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/cart')
def cart():
    if 'cart' not in session:
        session['cart'] = []
    
    cart_items = []
    total_price = 0
    total_capacity = 0

    conn = get_db_connection()
    
    for item in session['cart']:
        # Produktdetails aus der Datenbank holen
        product = conn.execute(
            'SELECT * FROM product_classes WHERE id = ?', 
            (item['product_id'],)
        ).fetchone()
        
        if product:
            # Verfeinerungen berechnen
            refinements = []
            item_price = product['base_price']
            
            # Hole Details für jede Verfeinerung
            for step_id, refinement_ids in item['refinements'].items():
                if not isinstance(refinement_ids, list):
                    refinement_ids = [refinement_ids]
                
                for r_id in refinement_ids:
                    refinement = conn.execute(
                        '''SELECT r.*, s.name AS step_name 
                        FROM refinements r 
                        JOIN refinement_steps s ON r.refinement_step_id = s.id 
                        WHERE r.id = ?''', 
                        (r_id,)
                    ).fetchone()
                    
                    if refinement:
                        refinements.append(dict(refinement))
                        item_price += refinement['price_addition']
            
            # Gesamtpreis für dieses Item
            item_total = item_price * item['quantity']
            total_price += item_total
            total_capacity += product['capacity'] * item['quantity']
            
            cart_items.append({
                'product': dict(product),
                'quantity': item['quantity'],
                'refinements': refinements,
                'total_price': item_total
            })
    
    conn.close()
    
    return render_template(
        'shop/cart.html',
        cart_items=cart_items,
        total_price=total_price,
        total_capacity=total_capacity
    )
@app.route('/cart/remove/<int:index>', methods=['POST'])
def remove_from_cart(index):
    if 'cart' in session and 0 <= index < len(session['cart']):
        session['cart'].pop(index)
        session.modified = True
    
    return redirect(url_for('cart'))

@app.route('/cart/clear', methods=['POST'])
def clear_cart():
    session['cart'] = []
    session.modified = True
    return redirect(url_for('cart'))

API_TOKENS = {
    'your_api_token_here': 'description_of_token_usage'
}

def require_api_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for API token in headers or query params
        token = request.headers.get('X-API-TOKEN') or request.args.get('api_token')
        if token not in API_TOKENS:
            return jsonify({'error': 'Invalid or missing API token'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/generate-slots', methods=['POST'])
@require_api_token
def api_generate_slots():
    """API endpoint to generate time slots for today using a specific rule"""
    data = request.get_json()
    rule_id = data.get('rule_id')
    
    if not rule_id:
        return jsonify({'error': 'Missing rule_id parameter'}), 400
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    
    # Check if slots already exist for today
    existing = conn.execute('SELECT COUNT(*) as count FROM time_slots WHERE date = ?', (today,)).fetchone()
    if existing['count'] > 0:
        conn.close()
        return jsonify({'error': 'Time slots already exist for today'}), 400
    
    # Get the rule
    rule = conn.execute('SELECT * FROM time_slot_rules WHERE id = ?', (rule_id,)).fetchone()
    if not rule:
        conn.close()
        return jsonify({'error': 'Time slot rule not found'}), 404
    
    # Generate time slots
    start_time = datetime.strptime(f"{today} {rule['start_time']}", '%Y-%m-%d %H:%M')
    end_time = datetime.strptime(f"{today} {rule['end_time']}", '%Y-%m-%d %H:%M')
    current = start_time
    
    slots_created = 0
    
    while current < end_time:
        next_time = current + timedelta(minutes=rule['interval_minutes'])
        
        if next_time > end_time:
            break
        
        conn.execute(
            'INSERT INTO time_slots (date, start_time, end_time, capacity, used_capacity) VALUES (?, ?, ?, ?, 0)',
            (
                today, 
                current.strftime('%H:%M'),
                next_time.strftime('%H:%M'),
                rule['capacity']
            )
        )
        slots_created += 1
        current = next_time
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'message': f'Successfully created {slots_created} time slots for {today}',
        'date': today,
        'slots_created': slots_created
    })

@app.route('/available-slots', methods=['POST'])
def available_slots():
    if 'cart' not in session or not session['cart']:
        return jsonify([])
        
    # Calculate required capacity
    total_capacity = 0
    conn = get_db_connection()
    for item in session['cart']:
        product = conn.execute('SELECT capacity FROM product_classes WHERE id = ?', (item['product_id'],)).fetchone()
        total_capacity += product['capacity'] * item['quantity']
        
    # Get all available rules
    rules = conn.execute('SELECT * FROM time_slot_rules WHERE active = 1').fetchall()
    
    # Check capacity against all rules
    capacity_error = None
    for rule in rules:
        min_capacity = rule['min_capacity_per_order']
        max_capacity = rule['max_capacity_per_order']
        if min_capacity and total_capacity < min_capacity:
            capacity_error = {
                "error": "capacity_too_small",
                "min_capacity": min_capacity,
                "current_capacity": total_capacity
            }
            break
        if max_capacity and total_capacity > max_capacity:
            capacity_error = {
                "error": "capacity_too_large",
                "max_capacity": max_capacity,
                "current_capacity": total_capacity
            }
            break
            
    # If capacity error, return immediately
    if capacity_error:
        conn.close()
        return jsonify(capacity_error)
        
    # Search for available slots
    available_days = []
    current_datetime = datetime.now()
    today = current_datetime.date()
    
    for i in range(8):  # Today + 7 days
        check_date = today + timedelta(days=i)
        date_str = check_date.strftime('%Y-%m-%d')
        
        # Get ALL slots for this day - not just ones with enough capacity
        # This is important for slot combination functionality
        slots_query = '''
            SELECT id, date, start_time, end_time, capacity, used_capacity
            FROM time_slots
            WHERE date = ?
            ORDER BY start_time
        '''
        slots_data = conn.execute(slots_query, (date_str,)).fetchall()
        
        if slots_data:
            # Convert all slots to dictionaries
            all_slots = [dict(slot) for slot in slots_data]
            
            # Filter slots that are in the future and have not started yet
            future_slots = []
            for slot in all_slots:
                # Convert time string to datetime object
                slot_date = datetime.strptime(slot['date'], '%Y-%m-%d').date()
                # Handle time format (assuming it's stored as HH:MM:SS or HH:MM)
                try:
                    slot_start_time = datetime.strptime(slot['start_time'], '%H:%M:%S').time()
                except ValueError:
                    slot_start_time = datetime.strptime(slot['start_time'], '%H:%M').time()
                
                # Create full datetime object for comparison
                slot_datetime = datetime.combine(slot_date, slot_start_time)
                
                # Only include slots that have not started yet
                if slot_datetime > current_datetime:
                    future_slots.append(slot)
            
            # If no future slots available for this day, skip to next day
            if not future_slots:
                continue
                
            # Find the most appropriate rule for this day
            matching_rule = None
            for rule in rules:
                # Here could be more complex logic for rule selection
                if rule['active']:
                    matching_rule = rule
                    break
                    
            # If no matching rule found, use default rule
            if not matching_rule:
                matching_rule = {
                    'min_processing_minutes': 0,
                    'min_capacity_per_order': 0,
                    'max_capacity_per_order': 0
                }
                
            # Get available pickup times, passing only future slots for the day
            # This allows the function to combine slots if needed
            pickup_times = get_available_pickup_times(future_slots, total_capacity, matching_rule)
            
            # If pickup times found, add to result
            if pickup_times:
                available_days.append({
                    'date': date_str,
                    'pickup_times': pickup_times
                })
                
    conn.close()
    return jsonify(available_days)

def get_available_pickup_times(slots, needed_capacity, rule=None):
    """
    Berechnet verfügbare Abholzeiten für die gegebenen Slots basierend auf der benötigten Kapazität.
    Abholzeit wird präzise auf Minutenbasis berechnet, basierend auf bereits belegter Kapazität.
    Optional kann eine Regel mit Mindestbearbeitungszeit übergeben werden.
    Unterstützt auch die Kombination mehrerer aufeinanderfolgender Slots für größere Bestellungen.
    """
    available_times = []
    
    # Stelle sicher, dass rule ein Dictionary ist, falls es übergeben wurde
    if rule and not isinstance(rule, dict):
        rule = dict(rule)
    
    # Prüfung, ob eine maximale Bestellkapazität definiert ist
    max_order_capacity = rule.get('max_capacity_per_order', 0) if rule else 0
    if max_order_capacity > 0 and needed_capacity > max_order_capacity:
        # Bestellung überschreitet die maximale Kapazität
        return []
    
    # Einzelne Slots prüfen
    for slot in slots:
        available_capacity = max(0, slot['capacity'] - slot['used_capacity'])
        
        if available_capacity >= needed_capacity:
            # Berechnung der Abholzeit basierend auf der Slotdauer und benötigter Kapazität
            slot_start = datetime.strptime(slot['start_time'], '%H:%M')
            slot_end = datetime.strptime(slot['end_time'], '%H:%M')
            
            # Slotdauer in Minuten
            slot_duration_minutes = (slot_end - slot_start).total_seconds() / 60
            
            # Minuten pro Kapazitätseinheit
            minutes_per_capacity = slot_duration_minutes / slot['capacity'] if slot['capacity'] > 0 else 0
            
            # Berechnung der benötigten Verarbeitungszeit
            processing_time = needed_capacity * minutes_per_capacity
            
            # Wende Mindestbearbeitungszeit an, falls definiert
            if rule and rule.get('min_processing_minutes', 0) > 0:
                processing_time = max(processing_time, rule.get('min_processing_minutes'))
            
            # Auf ganze Minuten aufrunden
            processing_time = math.ceil(processing_time)
            
            # Berechnung der bereits belegten Minuten
            used_minutes = slot['used_capacity'] * minutes_per_capacity
            
            # Abholzeit berechnen: Startzeit + bereits belegte Minuten + Verarbeitungszeit
            pickup_minutes = used_minutes + processing_time
            
            # Sicherstellen, dass die Abholzeit nicht über das Slotende hinausgeht
            if slot_start + timedelta(minutes=pickup_minutes) <= slot_end:
                pickup_time_dt = slot_start + timedelta(minutes=pickup_minutes)
                pickup_time = pickup_time_dt.strftime('%H:%M')
                
                available_times.append(pickup_time)
    
    # Wenn die Slots chronologisch sortiert sind (was sie sein sollten)
    # können wir aufeinanderfolgende Slots kombinieren
    if len(slots) > 1:
        # Kombinationen von Slots für größere Kapazitäten prüfen
        for start_idx in range(len(slots) - 1):
            combined_capacity = 0
            combined_used_capacity = 0
            combined_slots = []
            
            # Bis zu 4 aufeinanderfolgende Slots betrachten
            for i in range(min(4, len(slots) - start_idx)):
                current_slot = slots[start_idx + i]
                combined_slots.append(current_slot)
                
                # Verfügbare und belegte Kapazität addieren
                current_available = max(0, current_slot['capacity'] - current_slot['used_capacity'])
                combined_capacity += current_available
                combined_used_capacity += current_slot['used_capacity']
                
                # Wenn genug Kapazität vorhanden ist
                if combined_capacity >= needed_capacity:
                    # Zeitberechnung basierend auf dem ersten Slot
                    first_slot = slots[start_idx]
                    slot_start = datetime.strptime(first_slot['start_time'], '%H:%M')
                    
                    # Gesamtdauer und Kapazität berechnen
                    total_duration = 0
                    total_capacity = 0
                    
                    for j in range(i + 1):
                        slot_j = slots[start_idx + j]
                        start_j = datetime.strptime(slot_j['start_time'], '%H:%M')
                        end_j = datetime.strptime(slot_j['end_time'], '%H:%M')
                        duration_j = (end_j - start_j).total_seconds() / 60
                        
                        total_duration += duration_j
                        total_capacity += slot_j['capacity']
                    
                    # Minuten pro Kapazitätseinheit über alle betrachteten Slots
                    if total_capacity > 0:
                        minutes_per_capacity = total_duration / total_capacity
                        
                        # Berechnung der bereits belegten Minuten im ersten Slot
                        used_minutes_first = first_slot['used_capacity'] * (
                            (datetime.strptime(first_slot['end_time'], '%H:%M') - slot_start).total_seconds() / 60
                        ) / first_slot['capacity'] if first_slot['capacity'] > 0 else 0
                        
                        # Berechnung der Verarbeitungszeit für die neue Bestellung
                        processing_time = needed_capacity * minutes_per_capacity
                        
                        # Wende Mindestbearbeitungszeit an, falls definiert
                        if rule and rule.get('min_processing_minutes', 0) > 0:
                            processing_time = max(processing_time, rule.get('min_processing_minutes'))
                        
                        # Auf ganze Minuten aufrunden
                        processing_time = math.ceil(processing_time)
                        
                        # Abholzeit berechnen
                        pickup_minutes = used_minutes_first + processing_time
                        
                        # Sicherstellen, dass die Abholzeit innerhalb der kombinierten Slots liegt
                        last_slot = slots[start_idx + i]
                        slot_end = datetime.strptime(last_slot['end_time'], '%H:%M')
                        
                        if slot_start + timedelta(minutes=pickup_minutes) <= slot_end:
                            pickup_time_dt = slot_start + timedelta(minutes=pickup_minutes)
                            pickup_time = pickup_time_dt.strftime('%H:%M')
                            
                            if pickup_time not in available_times:
                                available_times.append(pickup_time)
                    
                    # Valide Kombination gefunden, weitere Slots nicht betrachten
                    break
    
    # Zeiten sortieren
    return sorted(available_times)
def identify_slots_for_pickup(slots, pickup_time, total_capacity):
    """
    Identifies which slots are used for a given pickup time and total capacity.
    Returns a list of slot IDs and how much capacity to allocate to each.
    """
    pickup_time_dt = datetime.strptime(pickup_time, '%H:%M')
    identified_slots = []
    
    # First, check if this is a single slot pickup
    for slot in slots:
        slot_start = datetime.strptime(slot['start_time'], '%H:%M')
        slot_end = datetime.strptime(slot['end_time'], '%H:%M')
        
        # Calculate how much capacity is available in this slot
        available_capacity = max(0, slot['capacity'] - slot['used_capacity'])
        
        # If pickup time is within this slot and slot has enough capacity
        if slot_start <= pickup_time_dt <= slot_end and available_capacity >= total_capacity:
            identified_slots.append({
                'id': slot['id'],
                'capacity_to_use': total_capacity
            })
            return identified_slots
    
    # If no single slot works, try combinations
    remaining_capacity = total_capacity
    sorted_slots = sorted(slots, key=lambda x: datetime.strptime(x['start_time'], '%H:%M'))
    
    for slot in sorted_slots:
        slot_start = datetime.strptime(slot['start_time'], '%H:%M')
        slot_end = datetime.strptime(slot['end_time'], '%H:%M')
        available_capacity = max(0, slot['capacity'] - slot['used_capacity'])
        
        # Only consider slots up to and including the pickup time slot
        if slot_end < pickup_time_dt:
            # Use all available capacity from this slot
            if available_capacity > 0:
                capacity_to_use = min(remaining_capacity, available_capacity)
                identified_slots.append({
                    'id': slot['id'],
                    'capacity_to_use': capacity_to_use
                })
                remaining_capacity -= capacity_to_use
                
                if remaining_capacity <= 0:
                    break
        # For the slot containing the pickup time
        elif slot_start <= pickup_time_dt <= slot_end:
            # Calculate how much of this slot we need to use
            slot_duration_minutes = (slot_end - slot_start).total_seconds() / 60
            minutes_until_pickup = (pickup_time_dt - slot_start).total_seconds() / 60
            
            # Calculate capacity per minute
            capacity_per_minute = slot['capacity'] / slot_duration_minutes if slot_duration_minutes > 0 else 0
            
            # Calculate how much capacity we need from this slot
            capacity_needed_until_pickup = math.ceil(minutes_until_pickup * capacity_per_minute)
            
            # Adjust for already used capacity
            capacity_needed = min(remaining_capacity, max(0, capacity_needed_until_pickup - slot['used_capacity']))
            
            if capacity_needed > 0:
                identified_slots.append({
                    'id': slot['id'],
                    'capacity_to_use': capacity_needed
                })
                remaining_capacity -= capacity_needed
            
            break
    
    return identified_slots

def distribute_items_to_slots(order_id, conn):
    """
    Distributes order items to slots based on their capacity requirements,
    with larger items given priority.
    """
    # Get all items for this order
    order_items = conn.execute('SELECT * FROM order_items WHERE order_id = ?', (order_id,)).fetchall()
    
    # Get capacity for each item and sort by capacity (larger items first)
    sorted_items = []
    for item in order_items:
        product = conn.execute(
            'SELECT capacity FROM product_classes WHERE id = ?', 
            (item['product_class_id'],)
        ).fetchone()
        sorted_items.append({
            'id': item['id'],
            'capacity': product['capacity'] * item['quantity']
        })
    
    # Sort items by capacity (largest first)
    sorted_items.sort(key=lambda x: x['capacity'], reverse=True)
    
    # Get allocated slots for this order
    allocated_slots = conn.execute(
        'SELECT slot_id, capacity_reserved FROM order_slot_allocation WHERE order_id = ?',
        (order_id,)
    ).fetchall()
    
    # Distribute items to slots
    for item in sorted_items:
        required = item['capacity']
        for slot in allocated_slots:
            allocate = min(slot['capacity_reserved'], required)
            if allocate > 0:
                # Reduce available capacity in this slot
                conn.execute(
                    'UPDATE order_slot_allocation SET capacity_reserved = ? WHERE order_id = ? AND slot_id = ?',
                    (slot['capacity_reserved'] - allocate, order_id, slot['slot_id'])
                )
                
                # Allocate item capacity to this slot
                conn.execute(
                    'INSERT INTO order_item_slots (order_item_id, slot_id, allocated_capacity) VALUES (?, ?, ?)',
                    (item['id'], slot['slot_id'], allocate)
                )
                
                required -= allocate
                if required <= 0:
                    break

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    try:
        if 'cart' not in session or not session['cart']:
            return redirect(url_for('cart'))
        
        conn = get_db_connection()
        
        # Hole Zahlungseinstellungen
        payment_settings = get_payment_settings()
        paypal_enabled = bool(payment_settings['paypal_enabled'])
        force_paypal = bool(payment_settings['force_paypal'])
        allow_cash = bool(payment_settings['allow_cash_payment'])
        
        # Wenn PayPal erzwungen wird, ist Barzahlung nicht erlaubt
        if force_paypal:
            allow_cash = False
        
        cart_items = []
        total_price = 0

        for item in session['cart']:
            product = conn.execute(
                'SELECT * FROM product_classes WHERE id = ?',
                (item['product_id'],)
            ).fetchone()
            
            refinements = []
            for step_id, refinement_id in item['refinements'].items():
                if isinstance(refinement_id, list):
                    for r_id in refinement_id:
                        step = conn.execute('SELECT name FROM refinement_steps WHERE id = ?', (step_id,)).fetchone()
                        ref = conn.execute('SELECT name FROM refinements WHERE id = ?', (r_id,)).fetchone()
                        if step and ref:
                            refinements.append({'step_name': step['name'], 'name': ref['name']})
                else:
                    step = conn.execute('SELECT name FROM refinement_steps WHERE id = ?', (step_id,)).fetchone()
                    ref = conn.execute('SELECT name FROM refinements WHERE id = ?', (refinement_id,)).fetchone()
                    if step and ref:
                        refinements.append({'step_name': step['name'], 'name': ref['name']})

            item_price = product['base_price'] * item['quantity']
            for step_id, refinement_id in item['refinements'].items():
                if isinstance(refinement_id, list):
                    for r_id in refinement_id:
                        ref_price = conn.execute(
                            'SELECT price_addition FROM refinements WHERE id = ?',
                            (r_id,)
                        ).fetchone()
                        if ref_price:
                            item_price += ref_price['price_addition'] * item['quantity']
                else:
                    ref_price = conn.execute(
                        'SELECT price_addition FROM refinements WHERE id = ?',
                        (refinement_id,)
                    ).fetchone()
                    if ref_price:
                        item_price += ref_price['price_addition'] * item['quantity']

            total_price += item_price
            cart_items.append({
                'product': product,
                'quantity': item['quantity'],
                'refinements': refinements,
                'total_price': item_price
            })

        if request.method == 'POST':
            pickup_date = request.form['pickup_date']
            pickup_time = request.form['pickup_time']
            customer_name = request.form['customer_name']
            customer_email = request.form['customer_email']
            
            # Zahlungsmethode bestimmen
            if force_paypal:
                payment_method = 'paypal'
            else:
                payment_method = request.form.get('payment_method', 'cash')
                # Validieren: nur 'paypal' oder 'cash' erlauben
                if payment_method not in ['paypal', 'cash']:
                    payment_method = 'cash'

            # Verfügbarkeit prüfen
            availability_check = {}
            availability_ok = True
            unavailable_items = []

            for item in session['cart']:
                product = conn.execute(
                    'SELECT * FROM product_classes WHERE id = ?',
                    (item['product_id'],)
                ).fetchone()

                availability = conn.execute(
                    'SELECT available_quantity FROM product_daily_availability WHERE product_id = ? AND date = ?',
                    (item['product_id'], pickup_date)
                ).fetchone()

                # Verwende die erweiterte Funktion für Verfügbarkeitsregeln
                available_quantity = get_product_availability_for_date(item['product_id'], pickup_date)

                if item['quantity'] > available_quantity:
                    availability_ok = False
                    unavailable_items.append({
                        'name': product['name'],
                        'requested': item['quantity'],
                        'available': available_quantity
                    })
                else:
                    availability_check[item['product_id']] = available_quantity

            if not availability_ok:
                conn.close()
                return render_template(
                    'shop/checkout.html', 
                    cart_items=cart_items, 
                    total_price=total_price,
                    error="Ihre Bestellung wurde nicht aufgegeben! Ein paar der bestellten Produkte sind in der angeforderten Menge leider nicht verfügbar:",
                    unavailable_items=unavailable_items
                )

            # Berechnung der gesamten Bestellkapazität
            total_capacity = sum(
                product['capacity'] * item['quantity'] 
                for item in session['cart'] 
                for product in [conn.execute('SELECT capacity FROM product_classes WHERE id = ?', (item['product_id'],)).fetchone()]
            )

            # 🔐 Kapazitätsregelprüfung (neu)
            rule_id = 1  # Annahme: Feste Regel-ID
            rule = conn.execute('SELECT * FROM time_slot_rules WHERE id = ?', (rule_id,)).fetchone()
            if rule:
                if rule['max_capacity_per_order'] > 0 and total_capacity > rule['max_capacity_per_order']:
                    flash(f"Maximale Bestellgröße überschritten ({rule['max_capacity_per_order']} Kapazitätseinheiten).")
                    conn.close()
                    return redirect(url_for('cart'))

                if rule['min_capacity_per_order'] > 0 and total_capacity < rule['min_capacity_per_order']:
                    flash(f"Mindestbestellgröße nicht erreicht ({rule['min_capacity_per_order']} Kapazitätseinheiten).")
                    conn.close()
                    return redirect(url_for('cart'))

            order_number = ''.join(random.choices(string.digits, k=4))
            conn.execute(
                '''INSERT INTO orders 
                (order_number, customer_name, customer_email, pickup_date, pickup_time, status, payment_method) 
                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (order_number, customer_name, customer_email, pickup_date, pickup_time, 'new', payment_method)
            )
            order_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

            for item in session['cart']:
                product = conn.execute(
                    'SELECT * FROM product_classes WHERE id = ?',
                    (item['product_id'],)
                ).fetchone()

                conn.execute(
                    'INSERT INTO order_items (order_id, product_class_id, quantity) VALUES (?, ?, ?)',
                    (order_id, item['product_id'], item['quantity'])
                )
                item_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

                for step_id, refinement_id in item['refinements'].items():
                    if isinstance(refinement_id, list):
                        for r_id in refinement_id:
                            conn.execute(
                                'INSERT INTO order_item_refinements (order_item_id, refinement_id) VALUES (?, ?)',
                                (item_id, r_id)
                            )
                    else:
                        conn.execute(
                            'INSERT INTO order_item_refinements (order_item_id, refinement_id) VALUES (?, ?)',
                            (item_id, refinement_id)
                        )

                availability_exists = conn.execute(
                    'SELECT COUNT(*) FROM product_daily_availability WHERE product_id = ? AND date = ?',
                    (item['product_id'], pickup_date)
                ).fetchone()[0]

                if availability_exists > 0:
                    conn.execute(
                        'UPDATE product_daily_availability SET available_quantity = available_quantity - ? WHERE product_id = ? AND date = ?',
                        (item['quantity'], item['product_id'], pickup_date)
                    )
                else:
                    default_stock = product['default_stock'] if 'default_stock' in product else 0
                    new_quantity = max(0, default_stock - item['quantity'])
                    conn.execute(
                        'INSERT INTO product_daily_availability (product_id, date, available_quantity) VALUES (?, ?, ?)',
                        (item['product_id'], pickup_date, new_quantity)
                    )

            slots = conn.execute(
                'SELECT * FROM time_slots WHERE date = ? ORDER BY start_time',
                (pickup_date,)
            ).fetchall()

            identified_slots = identify_slots_for_pickup(slots, pickup_time, total_capacity)

            if identified_slots:
                for slot_info in identified_slots:
                    slot_id = slot_info['id']
                    capacity_to_use = slot_info['capacity_to_use']
                    conn.execute(
                        'UPDATE time_slots SET used_capacity = used_capacity + ? WHERE id = ?',
                        (capacity_to_use, slot_id)
                    )
            else:
                remaining_capacity = total_capacity
                for slot in slots:
                    available = max(0, slot['capacity'] - slot['used_capacity'])
                    capacity_to_use = min(remaining_capacity, available)
                    if capacity_to_use > 0:
                        conn.execute(
                            'UPDATE time_slots SET used_capacity = used_capacity + ? WHERE id = ?',
                            (capacity_to_use, slot['id'])
                        )
                        remaining_capacity -= capacity_to_use
                        if remaining_capacity <= 0:
                            break

            for slot_info in identified_slots:
                conn.execute(
                    'INSERT INTO order_slot_allocation (order_id, slot_id, capacity_reserved) VALUES (?, ?, ?)',
                    (order_id, slot_info['id'], slot_info['capacity_to_use'])
                )

            order_items = conn.execute('SELECT * FROM order_items WHERE order_id = ?', (order_id,)).fetchall()
            sorted_items = []
            for item in order_items:
                product = conn.execute('SELECT capacity FROM product_classes WHERE id = ?', (item['product_class_id'],)).fetchone()
                sorted_items.append({
                    'id': item['id'],
                    'capacity': product['capacity'] * item['quantity']
                })
            sorted_items.sort(key=lambda x: x['capacity'], reverse=True)

            for item in sorted_items:
                required = item['capacity']
                allocated_slots = conn.execute(
                    'SELECT slot_id, capacity_reserved FROM order_slot_allocation WHERE order_id = ? AND capacity_reserved > 0',
                    (order_id,)
                ).fetchall()

                for slot in allocated_slots:
                    allocate = min(slot['capacity_reserved'], required)
                    conn.execute(
                        'UPDATE order_slot_allocation SET capacity_reserved = ? WHERE order_id = ? AND slot_id = ?',
                        (slot['capacity_reserved'] - allocate, order_id, slot['slot_id'])
                    )
                    conn.execute(
                        'INSERT INTO order_item_slots (order_item_id, slot_id, allocated_capacity) VALUES (?, ?, ?)',
                        (item['id'], slot['slot_id'], allocate)
                    )
                    required -= allocate
                    if required == 0:
                        break

            conn.commit()
            temp_order_number = order_number
            session.clear()
            session['last_order'] = temp_order_number
            session.modified = True

            send_order_confirmation(order_number, customer_email)

            conn.close()
            return redirect(url_for('order_confirmation'))

        conn.close()
        return render_template('shop/checkout.html', 
                        cart_items=cart_items, 
                        total_price=total_price,
                        paypal_enabled=paypal_enabled,
                        force_paypal=force_paypal,
                        allow_cash=allow_cash)

    except Exception as e:
        return render_template('error.html', error=str(e)), 500

def check_reminders():
    now = datetime.now()
    reminder_time = now + timedelta(minutes=15)
    reminder_time_str = reminder_time.strftime('%Y-%m-%d %H:%M')

    conn = get_db_connection()
    orders = conn.execute('''
        SELECT * FROM orders 
        WHERE status NOT IN ('completed', 'cancelled') 
        AND datetime(pickup_date || ' ' || pickup_time) 
            BETWEEN datetime(?) AND datetime(?, '+1 minute')
        AND reminder_sent = 0
    ''', (reminder_time_str, reminder_time_str)).fetchall()

    for order in orders:
        send_pickup_reminder(order)
        conn.execute('UPDATE orders SET reminder_sent = 1 WHERE id = ?', (order['id'],))
    
    conn.commit()
    conn.close()

@app.before_request
def before_every_request():
    check_reminders()

# Product availability management
@app.route('/admin/products/<int:product_id>/availability')
@login_required
def manage_availability(product_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM product_classes WHERE id = ?', (product_id,)).fetchone()
    
    # Get availability for next 7 days
    today = datetime.now().date()
    availability = {}
    for i in range(7):
        date = today + timedelta(days=i)
        date_str = date.isoformat()
        entry = conn.execute(
            'SELECT * FROM product_daily_availability WHERE product_id = ? AND date = ?',
            (product_id, date_str)
        ).fetchone()
        availability[date_str] = entry['available_quantity'] if entry else None
    
    conn.close()
    return render_template(
        'admin/availability.html',
        product=product,
        today=today,
        timedelta=timedelta,
        availability=availability
    )

@app.route('/admin/products/<int:product_id>/set-availability', methods=['POST'])
@login_required
def set_availability(product_id):
    date = request.form['date']
    quantity = int(request.form.get('quantity', 0))
    
    conn = get_db_connection()
    
    # Delete existing entry if quantity is null
    if quantity == '':
        conn.execute(
            'DELETE FROM product_daily_availability WHERE product_id = ? AND date = ?',
            (product_id, date)
        )
    else:
        # Upsert availability
        conn.execute(
            '''INSERT INTO product_daily_availability (product_id, date, available_quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(product_id, date) DO UPDATE SET available_quantity = excluded.available_quantity''',
            (product_id, date, quantity)
        )
    
    conn.commit()
    conn.close()
    return redirect(url_for('manage_availability', product_id=product_id))


@app.route('/orders/<int:order_id>/mark-delayed', methods=['POST'])
@login_required
def mark_order_delayed(order_id):
    delay_minutes = int(request.form['delay'])
    valid_delays = {2: '2-5', 5: '5-10', 10: '10-20', 20: '20+'}
    if delay_minutes not in valid_delays:
        flash('Ungültige Eingabe')
        return redirect(url_for('current_terminal'))

    conn = get_db_connection()
    conn.execute('UPDATE orders SET delayed = 1, delay_minutes = ? WHERE id = ?', (delay_minutes, order_id))
    conn.commit()
    order = conn.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
    conn.close()

    send_delay_notification(order, delay_minutes, valid_delays)
    return redirect(url_for('current_terminal'))

def identify_slots_for_pickup(slots, pickup_time, needed_capacity):
    """
    Identifiziert die relevanten Slots für eine bestimmte Abholzeit und benötigte Kapazität.
    Gibt eine Liste von Dictionaries zurück, die für jeden Slot die ID und die zu nutzende Kapazität enthält.
    """
    time_format = '%H:%M'
    pickup_time_dt = datetime.strptime(pickup_time, time_format)
    result_slots = []
    
    # Fall 1: Abholzeit entspricht genau dem Ende eines Slots
    for i, slot in enumerate(slots):
        if slot['end_time'] == pickup_time:
            # Dieser Slot und möglicherweise nachfolgende Slots verwenden
            remaining_capacity = needed_capacity
            current_idx = i
            
            while remaining_capacity > 0 and current_idx < len(slots):
                current_slot = slots[current_idx]
                available = max(0, current_slot['capacity'] - current_slot['used_capacity'])
                capacity_to_use = min(remaining_capacity, available)
                
                if capacity_to_use > 0:
                    result_slots.append({
                        'id': current_slot['id'],
                        'capacity_to_use': capacity_to_use
                    })
                    
                    remaining_capacity -= capacity_to_use
                
                current_idx += 1
            
            return result_slots
    
    # Fall 2: Abholzeit liegt innerhalb eines Slots
    for i, slot in enumerate(slots):
        slot_start = datetime.strptime(slot['start_time'], time_format)
        slot_end = datetime.strptime(slot['end_time'], time_format)
        
        if slot_start <= pickup_time_dt <= slot_end:
            # Dieser Slot und möglicherweise vorherige Slots verwenden
            result_slots = []
            remaining_capacity = needed_capacity
            
            # Beginne mit dem aktuellen Slot
            available = max(0, slot['capacity'] - slot['used_capacity'])
            capacity_to_use = min(remaining_capacity, available)
            
            if capacity_to_use > 0:
                result_slots.append({
                    'id': slot['id'],
                    'capacity_to_use': capacity_to_use
                })
                
                remaining_capacity -= capacity_to_use
            
            # Prüfe, ob der vorherige Slot auch genutzt werden muss
            if remaining_capacity > 0 and i > 0:
                prev_slot = slots[i-1]
                prev_available = max(0, prev_slot['capacity'] - prev_slot['used_capacity'])
                prev_capacity_to_use = min(remaining_capacity, prev_available)
                
                if prev_capacity_to_use > 0:
                    result_slots.append({
                        'id': prev_slot['id'],
                        'capacity_to_use': prev_capacity_to_use
                    })
                    
                    remaining_capacity -= prev_capacity_to_use
            
            # Wenn immer noch Kapazität benötigt wird, versuche nachfolgende Slots
            current_idx = i + 1
            while remaining_capacity > 0 and current_idx < len(slots):
                current_slot = slots[current_idx]
                available = max(0, current_slot['capacity'] - current_slot['used_capacity'])
                capacity_to_use = min(remaining_capacity, available)
                
                if capacity_to_use > 0:
                    result_slots.append({
                        'id': current_slot['id'],
                        'capacity_to_use': capacity_to_use
                    })
                    
                    remaining_capacity -= capacity_to_use
                
                current_idx += 1
            
            return result_slots
    
    # Fall 3: Spezialfall für kombinierte Slots, wenn die Abholzeit nach einem Slot aber vor dem nächsten liegt
    for i in range(len(slots) - 1):
        current_slot = slots[i]
        next_slot = slots[i+1]
        
        current_end = datetime.strptime(current_slot['end_time'], time_format)
        next_start = datetime.strptime(next_slot['start_time'], time_format)
        
        # Wenn die Abholzeit zwischen zwei Slots liegt
        if current_end < pickup_time_dt < next_start:
            # Dies ist wahrscheinlich eine Kombination aus aktuellem Slot und dem nächsten
            result_slots = []
            remaining_capacity = needed_capacity
            
            # Beginne mit dem aktuellen Slot
            current_available = max(0, current_slot['capacity'] - current_slot['used_capacity'])
            current_capacity_to_use = min(remaining_capacity, current_available)
            
            if current_capacity_to_use > 0:
                result_slots.append({
                    'id': current_slot['id'],
                    'capacity_to_use': current_capacity_to_use
                })
                
                remaining_capacity -= current_capacity_to_use
            
            # Füge den nächsten Slot hinzu
            if remaining_capacity > 0:
                next_available = max(0, next_slot['capacity'] - next_slot['used_capacity'])
                next_capacity_to_use = min(remaining_capacity, next_available)
                
                if next_capacity_to_use > 0:
                    result_slots.append({
                        'id': next_slot['id'],
                        'capacity_to_use': next_capacity_to_use
                    })
                    
                    remaining_capacity -= next_capacity_to_use
            
            # Wenn immer noch mehr Kapazität benötigt wird, verwende weitere nachfolgende Slots
            current_idx = i + 2
            while remaining_capacity > 0 and current_idx < len(slots):
                add_slot = slots[current_idx]
                available = max(0, add_slot['capacity'] - add_slot['used_capacity'])
                capacity_to_use = min(remaining_capacity, available)
                
                if capacity_to_use > 0:
                    result_slots.append({
                        'id': add_slot['id'],
                        'capacity_to_use': capacity_to_use
                    })
                    
                    remaining_capacity -= capacity_to_use
                
                current_idx += 1
            
            return result_slots
    
    # Fallback: Wenn keine passenden Slots gefunden wurden, verwende die Slots mit Kapazität
    # Dies sollte nur in Ausnahmefällen passieren
    remaining_capacity = needed_capacity
    for slot in slots:
        available = max(0, slot['capacity'] - slot['used_capacity'])
        capacity_to_use = min(remaining_capacity, available)
        
        if capacity_to_use > 0:
            result_slots.append({
                'id': slot['id'],
                'capacity_to_use': capacity_to_use
            })
            
            remaining_capacity -= capacity_to_use
            
            if remaining_capacity <= 0:
                break
    
    return result_slots


@app.route('/order-confirmation')
def order_confirmation():
    if 'last_order' not in session:
        return redirect(url_for('index'))
    
    order_number = session['last_order']
    
    conn = get_db_connection()
    order = conn.execute(
        'SELECT * FROM orders WHERE order_number = ?',
        (order_number,)
    ).fetchone()
    conn.close()
    
    return render_template('shop/order_confirmation.html', order=order)

@app.route('/track/<order_number>')
def track_order(order_number):
    conn = get_db_connection()
    
    # Korrigierte SQL-Abfrage ohne Kommentarzeichen
    order = conn.execute(
        '''SELECT 
            id, 
            order_number, 
            customer_name,
            customer_email,
            pickup_date, 
            pickup_time,
            delayed,
            delay_minutes , 
            status,
            created,
            (SELECT SUM(oi.quantity * pc.base_price) 
             FROM order_items oi 
             JOIN product_classes pc ON oi.product_class_id = pc.id 
             WHERE oi.order_id = orders.id) as total_amount
        FROM orders 
        WHERE order_number = ?''',
        (order_number,)
    ).fetchone()

    if not order:
        flash('Bestellung nicht gefunden')
        return redirect(url_for('index'))
    
    # Rest der Funktion bleibt gleich
    items = conn.execute(
        '''SELECT oi.*, pc.name as product_name, pc.base_price as price
        FROM order_items oi 
        JOIN product_classes pc ON oi.product_class_id = pc.id 
        WHERE oi.order_id = ?''',
        (order['id'],)
    ).fetchall()
    
    
    # Get refinements for each item
    item_refinements = {}
    for item in items:
        refinements = conn.execute(
            '''
            SELECT r.name 
            FROM order_item_refinements oir 
            JOIN refinements r ON oir.refinement_id = r.id 
            WHERE oir.order_item_id = ?
            ''',
            (item['id'],)
        ).fetchall()
        item_refinements[item['id']] = refinements
    
    conn.close()
    
    return render_template(
        'shop/track_order.html', 
        order=order, 
        items=items,
        item_refinements=item_refinements,
        now=datetime.now()
    )

# Terminal routes

@app.route('/terminal/current')
@login_required
def current_terminal():
    now = datetime.now().strftime('%H:%M')
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Get offset parameter for navigation
    offset = request.args.get('offset', 0, type=int)
    
    conn = get_db_connection()
    
    # Get current or navigated slot
    if offset == 0:
        # Get current slot
        slot = conn.execute('''
            SELECT * FROM time_slots
            WHERE date = ? AND start_time <= ? AND end_time > ?
            ORDER BY start_time
            LIMIT 1
        ''', (today, now, now)).fetchone()
    else:
        # Get reference slot (current or first of the day)
        reference_slot = conn.execute('''
            SELECT * FROM time_slots
            WHERE date = ? AND start_time <= ? AND end_time > ?
            ORDER BY start_time
            LIMIT 1
        ''', (today, now, now)).fetchone()
        
        if not reference_slot:
            # If no current slot, get first slot of the day
            reference_slot = conn.execute('''
                SELECT * FROM time_slots
                WHERE date = ?
                ORDER BY start_time
                LIMIT 1
            ''', (today,)).fetchone()
        
        if reference_slot:
            # Get slot by offset from reference
            if offset > 0:
                # Get future slots
                slot = conn.execute('''
                    SELECT * FROM time_slots
                    WHERE (date > ? OR (date = ? AND start_time > ?))
                    ORDER BY date, start_time
                    LIMIT 1 OFFSET ?
                ''', (reference_slot['date'], reference_slot['date'], reference_slot['start_time'], offset - 1)).fetchone()
            else:
                # Get past slots
                slot = conn.execute('''
                    SELECT * FROM time_slots
                    WHERE (date < ? OR (date = ? AND start_time < ?))
                    ORDER BY date DESC, start_time DESC
                    LIMIT 1 OFFSET ?
                ''', (reference_slot['date'], reference_slot['date'], reference_slot['start_time'], abs(offset) - 1)).fetchone()
        else:
            slot = None
    
    # Set current_slot to the navigated slot
    current_slot = slot
    
    orders = []
    order_items = {}
    
    if current_slot:
        # Get orders for the current slot
        orders = conn.execute('''
            SELECT o.*
            FROM orders o
            JOIN order_item_slots ois ON o.id = (
                SELECT order_id FROM order_items WHERE id = ois.order_item_id
            )
            WHERE ois.slot_id = ? AND o.status IN ('new', 'in_progress')
            GROUP BY o.id
        ''', (current_slot['id'],)).fetchall()
        
        # Get items for each order
        order_items = {}
        for order in orders:
            items = conn.execute(
                '''
                SELECT oi.*, pc.name as product_name
                FROM order_items oi
                JOIN product_classes pc ON oi.product_class_id = pc.id
                WHERE oi.order_id = ?
                ''',
                (order['id'],)
            ).fetchall()
            
            # Get refinements for each item
            item_refinements = {}
            for item in items:
                refinements = conn.execute(
                    '''
                    SELECT r.name
                    FROM order_item_refinements oir
                    JOIN refinements r ON oir.refinement_id = r.id
                    WHERE oir.order_item_id = ?
                    ''',
                    (item['id'],)
                ).fetchall()
                item_refinements[item['id']] = refinements
            
            order_items[order['id']] = {
                'items': items,
                'refinements': item_refinements
            }
    
    # Calculate previous and next offsets
    prev_offset = offset - 1
    next_offset = offset + 1
    
    conn.close()
    
    return render_template('terminal/current.html',
                         current_slot=current_slot,
                         orders=orders,
                         order_items=order_items,
                         current_offset=offset,
                         prev_offset=prev_offset,
                         next_offset=next_offset)

@app.route('/terminal/incoming')
@login_required
def incoming_terminal():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    # Get orders that are new or in progress, sorted by pickup time
    orders = conn.execute(
        '''
        SELECT * FROM orders 
        WHERE status IN ('new', 'in_progress') 
        ORDER BY pickup_date, pickup_time
        '''
    ).fetchall()
    
    # Get items for each order
    order_items = {}
    for order in orders:
        items = conn.execute(
            '''
            SELECT oi.*, pc.name as product_name 
            FROM order_items oi 
            JOIN product_classes pc ON oi.product_class_id = pc.id 
            WHERE oi.order_id = ?
            ''',
            (order['id'],)
        ).fetchall()
        
        # Get refinements for each item
        item_refinements = {}
        for item in items:
            refinements = conn.execute(
                '''
                SELECT r.name 
                FROM order_item_refinements oir 
                JOIN refinements r ON oir.refinement_id = r.id 
                WHERE oir.order_item_id = ?
                ''',
                (item['id'],)
            ).fetchall()
            item_refinements[item['id']] = refinements
        
        order_items[order['id']] = {
            'items': items,
            'refinements': item_refinements
        }
    
    conn.close()
    
    return render_template(
        'terminal/incoming.html', 
        orders=orders, 
        order_items=order_items
    )

@app.route('/terminal/outgoing')
@login_required
def outgoing_terminal():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    # Get orders that are ready for pickup, sorted by pickup time
    orders = conn.execute(
        '''
        SELECT * FROM orders 
        WHERE status = 'ready' 
        ORDER BY pickup_date, pickup_time
        '''
    ).fetchall()
    
    # Get items for each order
    order_items = {}
    for order in orders:
        items = conn.execute(
            '''
            SELECT oi.*, pc.name as product_name 
            FROM order_items oi 
            JOIN product_classes pc ON oi.product_class_id = pc.id 
            WHERE oi.order_id = ?
            ''',
            (order['id'],)
        ).fetchall()
        
        # Get refinements for each item
        item_refinements = {}
        for item in items:
            refinements = conn.execute(
                '''
                SELECT r.name 
                FROM order_item_refinements oir 
                JOIN refinements r ON oir.refinement_id = r.id 
                WHERE oir.order_item_id = ?
                ''',
                (item['id'],)
            ).fetchall()
            item_refinements[item['id']] = refinements
        
        order_items[order['id']] = {
            'items': items,
            'refinements': item_refinements
        }
    
    conn.close()
    
    return render_template(
        'terminal/outgoing.html', 
        orders=orders, 
        order_items=order_items
    )

from flask import request

@app.route('/orders/<int:order_id>/mark-in-progress', methods=['POST'])
@login_required
def mark_order_in_progress(order_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    conn.execute('UPDATE orders SET status = ? WHERE id = ?', ('in_progress', order_id))
    conn.commit()
    conn.close()
    
    return redirect(request.referrer or url_for('index'))

@app.route('/orders/<int:order_id>/mark-ready', methods=['POST'])
@login_required
def mark_order_ready(order_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    conn.execute('UPDATE orders SET status = ? WHERE id = ?', ('ready', order_id))
    conn.commit()
    conn.close()
    
    return redirect(request.referrer or url_for('index'))

@app.route('/orders/<int:order_id>/mark-completed', methods=['POST'])
@login_required
def mark_order_completed(order_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    conn.execute('UPDATE orders SET status = ? WHERE id = ?', ('completed', order_id))
    conn.commit()
    conn.close()
    
    return redirect(request.referrer or url_for('index'))


# ============================================
# Zahlungseinstellungen (Payment Settings)
# ============================================

def get_payment_settings():
    """Hole die Zahlungseinstellungen aus der Datenbank"""
    conn = get_db_connection()
    settings = conn.execute('SELECT * FROM payment_settings ORDER BY id DESC LIMIT 1').fetchone()
    
    if not settings:
        # Erstelle Standard-Einstellungen wenn nicht vorhanden
        conn.execute('''
            INSERT INTO payment_settings 
            (paypal_enabled, paypal_email, paypal_client_id, paypal_secret, paypal_mode, force_paypal, allow_cash_payment)
            VALUES (0, NULL, NULL, NULL, 'sandbox', 0, 1)
        ''')
        conn.commit()
        settings = conn.execute('SELECT * FROM payment_settings ORDER BY id DESC LIMIT 1').fetchone()
    
    conn.close()
    return settings


@app.route('/admin/payment-settings', methods=['GET', 'POST'])
@login_required
def payment_settings():
    """Admin-Seite für Zahlungseinstellungen"""
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        # Einstellungen speichern
        paypal_enabled = 1 if request.form.get('paypal_enabled') else 0
        paypal_email = request.form.get('paypal_email', '').strip()
        paypal_client_id = request.form.get('paypal_client_id', '').strip()
        paypal_secret = request.form.get('paypal_secret', '').strip()
        paypal_mode = request.form.get('paypal_mode', 'sandbox')
        force_paypal = 1 if request.form.get('force_paypal') else 0
        allow_cash_payment = 1 if request.form.get('allow_cash_payment') else 0
        
        # Aktualisiere oder füge neue Einstellungen ein
        existing = conn.execute('SELECT id FROM payment_settings ORDER BY id DESC LIMIT 1').fetchone()
        
        if existing:
            conn.execute('''
                UPDATE payment_settings 
                SET paypal_enabled = ?, paypal_email = ?, paypal_client_id = ?, 
                    paypal_secret = ?, paypal_mode = ?, force_paypal = ?, 
                    allow_cash_payment = ?, updated = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (paypal_enabled, paypal_email, paypal_client_id, paypal_secret,
                  paypal_mode, force_paypal, allow_cash_payment, existing['id']))
        else:
            conn.execute('''
                INSERT INTO payment_settings 
                (paypal_enabled, paypal_email, paypal_client_id, paypal_secret, 
                 paypal_mode, force_paypal, allow_cash_payment)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (paypal_enabled, paypal_email, paypal_client_id, paypal_secret,
                  paypal_mode, force_paypal, allow_cash_payment))
        
        conn.commit()
        flash('Zahlungseinstellungen wurden gespeichert!', 'success')
        return redirect(url_for('payment_settings'))
    
    # Lade aktuelle Einstellungen
    settings = conn.execute('SELECT * FROM payment_settings ORDER BY id DESC LIMIT 1').fetchone()
    
    if not settings:
        # Erstelle Standard-Einstellungen
        settings = {
            'id': 0,
            'paypal_enabled': 0,
            'paypal_email': '',
            'paypal_client_id': '',
            'paypal_secret': '',
            'paypal_mode': 'sandbox',
            'force_paypal': 0,
            'allow_cash_payment': 1
        }
    
    conn.close()
    
    return render_template('admin/payment_settings.html', settings=settings)


# API-Endpunkt für Zahlungseinstellungen (für Checkout)
@app.route('/api/payment-settings')
def api_payment_settings():
    """API, das die Zahlungseinstellungen für das Frontend zurückgibt"""
    settings = get_payment_settings()
    
    return jsonify({
        'paypal_enabled': bool(settings['paypal_enabled']),
        'paypal_mode': settings['paypal_mode'],
        'force_paypal': bool(settings['force_paypal']),
        'allow_cash_payment': bool(settings['allow_cash_payment']),
        'paypal_email': settings['paypal_email'] or ''
    })


# ============================================
# PayPal Developer/Test-Modus
# ============================================

@app.route('/admin/paypal-developer')
@login_required
def paypal_developer():
    """PayPal Developer Test-Interface"""
    if current_user.role != 'admin':
        flash("Zugriff verweigert", 'error')
        return redirect(url_for('dashboard'))
    
    settings = get_payment_settings()
    
    # Letzte Test-Transaktionen abrufen
    conn = get_db_connection()
    test_transactions = conn.execute('''
        SELECT * FROM paypal_test_logs 
        ORDER BY created DESC 
        LIMIT 20
    ''').fetchall()
    conn.close()
    
    return render_template('admin/paypal_developer.html', 
                         settings=settings,
                         test_transactions=test_transactions)


@app.route('/admin/paypal-developer/test-payment', methods=['POST'])
@login_required
def paypal_test_payment():
    """Testet eine PayPal-Zahlung mit dem eingestellten Modus"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Zugriff verweigert'}), 403
    
    settings = get_payment_settings()
    paypal_mode = settings.get('paypal_mode', 'sandbox')
    paypal_enabled = bool(settings.get('paypal_enabled', 0))
    
    test_amount = float(request.form.get('test_amount', 10.00))
    test_email = request.form.get('test_email', 'test@example.com')
    test_scenario = request.form.get('test_scenario', 'success')
    
    conn = get_db_connection()
    
    # Test-Transaktion simulieren
    test_order_id = f"TEST-{uuid.uuid4().hex[:8].upper()}"
    
    # PayPal API-Aufruf simulieren basierend auf Modus
    result = {
        'success': False,
        'test_order_id': test_order_id,
        'amount': test_amount,
        'mode': paypal_mode,
        'scenario': test_scenario,
        'error': None,
        'details': None
    }
    
    if not paypal_enabled:
        result['error'] = 'PayPal ist nicht aktiviert'
    elif paypal_mode == 'sandbox':
        # Sandbox-Modus: Test-Szenarien
        if test_scenario == 'success':
            result['success'] = True
            result['details'] = 'Zahlung erfolgreich im Sandbox-Modus'
            result['paypal_transaction_id'] = f"SANDBOX-{uuid.uuid4().hex[:12].upper()}"
        elif test_scenario == 'decline':
            result['error'] = 'Zahlung wurde abgelehnt (simuliert)'
            result['details'] = 'Die Karte wurde abgelehnt. Bitte verwenden Sie eine andere Zahlungsmethode.'
        elif test_scenario == 'expired':
            result['error'] = 'Zahlungszeitraum abgelaufen'
            result['details'] = 'Die Zahlung wurde nicht innerhalb von 30 Minuten abgeschlossen.'
        elif test_scenario == 'error':
            result['error'] = 'PayPal-Systemfehler'
            result['details'] = 'Ein internen PayPal-Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.'
    else:
        # Live-Modus: Nur Simulation (keine echten API-Aufrufe)
        result['success'] = True
        result['details'] = f'Live-Modus: Testzahlung für {test_amount} EUR würde jetzt an PayPal gesendet'
        result['note'] = 'Dies ist ein Simulationstest. Im echten Live-Modus wird eine echte PayPal-Transaktion erstellt.'
    
    # Test-Transaktion in Datenbank speichern
    conn.execute('''
        INSERT INTO paypal_test_logs 
        (test_order_id, amount, paypal_mode, test_scenario, success, error_message, details, test_email)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (test_order_id, test_amount, paypal_mode, test_scenario, 
          1 if result['success'] else 0, result['error'], result.get('details'), test_email))
    conn.commit()
    conn.close()
    
    if request.headers.get('Accept') == 'application/json':
        return jsonify(result)
    
    if result['success']:
        flash(f'Testzahlung erfolgreich! Betrag: {test_amount} EUR, Modus: {paypal_mode}', 'success')
    else:
        flash(f'Testzahlung fehlgeschlagen: {result.get("error", "Unbekannter Fehler")}', 'error')
    
    return redirect(url_for('paypal_developer'))


@app.route('/admin/paypal-developer/validate-config', methods=['POST'])
@login_required
def paypal_validate_config():
    """Validiert die PayPal-Konfiguration"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Zugriff verweigert'}), 403
    
    settings = get_payment_settings()
    
    issues = []
    warnings = []
    
    # Validierung der Konfiguration
    if not settings.get('paypal_enabled'):
        issues.append('PayPal ist nicht aktiviert')
    
    if not settings.get('paypal_email'):
        issues.append('PayPal-E-Mail-Adresse fehlt')
    
    if not settings.get('paypal_client_id'):
        issues.append('PayPal Client ID fehlt')
    
    if not settings.get('paypal_secret'):
        issues.append('PayPal Secret fehlt')
    
    if settings.get('paypal_mode') == 'sandbox':
        warnings.append('PayPal läuft im Sandbox-Modus (Testmodus)')
    
    # Prüfen, ob Force-PayPal aktiviert ist
    if settings.get('force_paypal') and not settings.get('allow_cash_payment'):
        pass  # Das ist OK, nur eine Info
    
    return jsonify({
        'success': len(issues) == 0,
        'issues': issues,
        'warnings': warnings,
        'current_config': {
            'mode': settings.get('paypal_mode'),
            'enabled': bool(settings.get('paypal_enabled')),
            'email': settings.get('paypal_email', '').replace('@', '***') if settings.get('paypal_email') else ''
        }
    })


@app.route('/admin/paypal-developer/switch-mode', methods=['POST'])
@login_required
def paypal_switch_mode():
    """Schaltet zwischen Sandbox und Live-Modus um"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Zugriff verweigert'}), 403
    
    new_mode = request.form.get('mode', 'sandbox')
    
    if new_mode not in ['sandbox', 'live']:
        return jsonify({'success': False, 'error': 'Ungültiger Modus'}), 400
    
    confirm = request.form.get('confirm', 'no')
    
    if new_mode == 'live' and confirm != 'yes':
        return jsonify({
            'success': False, 
            'error': 'Bitte bestätigen Sie den Wechsel zum Live-Modus',
            'requires_confirmation': True
        }), 400
    
    conn = get_db_connection()
    conn.execute('''
        UPDATE payment_settings 
        SET paypal_mode = ?
        WHERE id = (SELECT id FROM payment_settings ORDER BY id DESC LIMIT 1)
    ''', (new_mode,))
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': f'PayPal-Modus wechsel zu {new_mode.upper()}',
        'old_mode': 'sandbox' if new_mode == 'live' else 'live',
        'new_mode': new_mode
    })


@app.route('/admin/paypal-developer/test-webhook', methods=['POST'])
@login_required
def paypal_test_webhook():
    """Testet den PayPal Webhook"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Zugriff verweigert'}), 403
    
    webhook_type = request.form.get('webhook_type', 'payment_completed')
    
    # Simuliere Webhook-Events
    webhook_events = {
        'payment_completed': {
            'event_type': 'CHECKOUT.ORDER.APPROVED',
            'resource': {
                'status': 'COMPLETED',
                'id': f"ORDER-{uuid.uuid4().hex[:8].upper()}"
            }
        },
        'payment_failed': {
            'event_type': 'PAYMENT.CAPTURE.DENIED',
            'resource': {
                'status': 'DENIED',
                'id': f"ORDER-{uuid.uuid4().hex[:8].upper()}"
            }
        },
        'refund': {
            'event_type': 'PAYMENT.CAPTURE.REFUNDED',
            'resource': {
                'status': 'REFUNDED',
                'id': f"ORDER-{uuid.uuid4().hex[:8].upper()}"
            }
        }
    }
    
    event = webhook_events.get(webhook_type, webhook_events['payment_completed'])
    
    return jsonify({
        'success': True,
        'event_type': webhook_type,
        'simulated_event': event,
        'message': f'Test-Webhook vom Typ {webhook_type} empfangen (simuliert)'
    })


# ============================================
# Produkt-Verfügbarkeitsregeln (Availability Rules)
# ============================================

def get_applicable_availability_rule(product_id, date, time=None):
    """
    Ermittelt die anwendbare Verfügbarkeitsregel für ein Produkt zu einem bestimmten Zeitpunkt.
    Returns: (rule_dict or None, applies_to_product)
    """
    conn = get_db_connection()
    now = datetime.now()
    
    # Zeit und Datum bestimmen
    if not time:
        time = now.strftime('%H:%M')
    check_date = date if date else now.strftime('%Y-%m-%d')
    check_weekday = now.weekday()  # 0 = Montag, 6 = Sonntag
    check_month = now.month
    check_day = now.day
    
    # Alle aktiven Regeln abrufen, sortiert nach Priorität (absteigend)
    rules = conn.execute('''
        SELECT * FROM availability_rules 
        WHERE active = 1 
        ORDER BY priority DESC, id DESC
    ''').fetchall()
    
    applicable_rule = None
    
    for rule in rules:
        # Prüfen ob Regel für dieses Produkt gilt
        if rule['scope'] == 'specific':
            # Prüfen ob Produkt in der Regel enthalten ist
            product_in_rule = conn.execute('''
                SELECT 1 FROM availability_rule_products 
                WHERE rule_id = ? AND product_class_id = ?
            ''', (rule['id'], product_id)).fetchone()
            
            if not product_in_rule:
                continue  # Regel gilt nicht für dieses Produkt
        
        # Datumsbereich prüfen
        if rule['start_date'] and check_date < rule['start_date']:
            continue
        if rule['end_date'] and check_date > rule['end_date']:
            continue
        
        # Tageszeit prüfen (falls start_time oder end_time angegeben)
        if rule['start_time'] and time < rule['start_time']:
            continue
        if rule['end_time'] and time > rule['end_time']:
            continue
        
        # Wochentage prüfen
        if rule['weekdays']:
            weekdays = [int(d) for d in rule['weekdays'].split(',')]
            if check_weekday not in weekdays:
                continue
        
        # Monatstage prüfen
        if rule['month_days']:
            month_days = [int(d) for d in rule['month_days'].split(',')]
            if check_day not in month_days:
                continue
        
        # Monate prüfen
        if rule['months']:
            months = [int(m) for m in rule['months'].split(',')]
            if check_month not in months:
                continue
        
        # Alle Bedingungen erfüllt - Regel anwenden
        applicable_rule = rule
        break  # Erste passende Regel (höchste Priorität) verwenden
    
    conn.close()
    return applicable_rule


def get_product_availability_for_date(product_id, date, time=None):
    """
    Ermittelt die verfügbare Menge für ein Produkt an einem bestimmten Datum.
    Berücksichtigt sowohl tägliche Verfügbarkeit als auch Verfügbarkeitsregeln.
    """
    conn = get_db_connection()
    now = datetime.now()
    
    if not time:
        time = now.strftime('%H:%M')
    check_date = date if date else now.strftime('%Y-%m-%d')
    
    # Produkt-Standardmenge abrufen
    product = conn.execute('SELECT default_stock FROM product_classes WHERE id = ?', (product_id,)).fetchone()
    default_stock = product['default_stock'] if product else 0
    
    # Zuerst: Standard tägliche Verfügbarkeit prüfen
    daily_availability = conn.execute('''
        SELECT available_quantity FROM product_daily_availability 
        WHERE product_id = ? AND date = ?
    ''', (product_id, check_date)).fetchone()
    
    # Dann: Regel-basierte Verfügbarkeit prüfen
    rule = get_applicable_availability_rule(product_id, check_date, time)
    
    if rule:
        rule_quantity = rule['available_quantity']
        
        if rule_quantity == -1:
            # Unbegrenzt - verwende Daily-Availability oder Standard
            available = daily_availability['available_quantity'] if daily_availability else default_stock
        else:
            # Regel bestimmt Menge
            available = rule_quantity
    else:
        # Keine Regel - Standard verwenden
        available = daily_availability['available_quantity'] if daily_availability else default_stock
    
    conn.close()
    return max(0, available)


@app.route('/admin/availability-rules')
@login_required
def availability_rules():
    """Admin-Seite für Verfügbarkeitsregeln"""
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Alle Regeln abrufen
    rules = conn.execute('SELECT * FROM availability_rules ORDER BY priority DESC, id DESC').fetchall()
    
    # Produkte für jede Regel abrufen (falls scope = 'specific')
    rules_with_products = []
    for rule in rules:
        if rule['scope'] == 'specific':
            products = conn.execute('''
                SELECT pc.* FROM product_classes pc
                JOIN availability_rule_products arp ON pc.id = arp.product_class_id
                WHERE arp.rule_id = ?
            ''', (rule['id'],)).fetchall()
            rules_with_products.append({
                'rule': rule,
                'products': products
            })
        else:
            rules_with_products.append({
                'rule': rule,
                'products': []
            })
    
    conn.close()
    
    return render_template('admin/availability_rules.html', rules=rules_with_products)


@app.route('/admin/availability-rules/add', methods=['GET', 'POST'])
@login_required
def add_availability_rule():
    """Neue Verfügbarkeitsregel erstellen"""
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        active = 1 if request.form.get('active') else 0
        scope = request.form.get('scope', 'all')
        
        # Zeitliche Einschränkungen
        start_date = request.form.get('start_date', '').strip() or None
        end_date = request.form.get('end_date', '').strip() or None
        start_time = request.form.get('start_time', '').strip() or None
        end_time = request.form.get('end_time', '').strip() or None
        
        # Wochentage (0=So, 1=Mo, ..., 6=Sa)
        weekdays = []
        for i in range(7):
            if request.form.get(f'weekday_{i}'):
                weekdays.append(str(i))
        weekdays_str = ','.join(weekdays) if weekdays else None
        
        # Monatstage
        month_days = []
        for i in range(1, 32):
            if request.form.get(f'monthday_{i}'):
                month_days.append(str(i))
        month_days_str = ','.join(month_days) if month_days else None
        
        # Monate
        months = []
        for i in range(1, 13):
            if request.form.get(f'month_{i}'):
                months.append(str(i))
        months_str = ','.join(months) if months else None
        
        # Menge und Priorität
        quantity = int(request.form.get('available_quantity', -1))
        priority = int(request.form.get('priority', 0))
        
        # Regel speichern
        conn.execute('''
            INSERT INTO availability_rules 
            (name, description, active, scope, start_date, end_date, start_time, end_time,
             weekdays, month_days, months, available_quantity, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, description, active, scope, start_date, end_date, start_time, end_time,
              weekdays_str, month_days_str, months_str, quantity, priority))
        
        rule_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        
        # Produkte für spezifische Regeln speichern
        if scope == 'specific':
            product_ids = request.form.getlist('products')
            for product_id in product_ids:
                conn.execute('''
                    INSERT INTO availability_rule_products (rule_id, product_class_id)
                    VALUES (?, ?)
                ''', (rule_id, int(product_id)))
        
        conn.commit()
        flash(f'Verfügbarkeitsregel "{name}" wurde erstellt!', 'success')
        conn.close()
        return redirect(url_for('availability_rules'))
    
    # Produkte für Auswahl abrufen
    products = conn.execute('''
        SELECT * FROM product_classes 
        WHERE active = 1 AND deleted = 0
        ORDER BY name
    ''').fetchall()
    
    conn.close()
    return render_template('admin/add_availability_rule.html', products=products)


@app.route('/admin/availability-rules/<int:rule_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_availability_rule(rule_id):
    """Verfügbarkeitsregel bearbeiten"""
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        active = 1 if request.form.get('active') else 0
        scope = request.form.get('scope', 'all')
        
        # Zeitliche Einschränkungen
        start_date = request.form.get('start_date', '').strip() or None
        end_date = request.form.get('end_date', '').strip() or None
        start_time = request.form.get('start_time', '').strip() or None
        end_time = request.form.get('end_time', '').strip() or None
        
        # Wochentage
        weekdays = []
        for i in range(7):
            if request.form.get(f'weekday_{i}'):
                weekdays.append(str(i))
        weekdays_str = ','.join(weekdays) if weekdays else None
        
        # Monatstage
        month_days = []
        for i in range(1, 32):
            if request.form.get(f'monthday_{i}'):
                month_days.append(str(i))
        month_days_str = ','.join(month_days) if month_days else None
        
        # Monate
        months = []
        for i in range(1, 13):
            if request.form.get(f'month_{i}'):
                months.append(str(i))
        months_str = ','.join(months) if months else None
        
        # Menge und Priorität
        quantity = int(request.form.get('available_quantity', -1))
        priority = int(request.form.get('priority', 0))
        
        # Regel aktualisieren
        conn.execute('''
            UPDATE availability_rules 
            SET name = ?, description = ?, active = ?, scope = ?,
                start_date = ?, end_date = ?, start_time = ?, end_time = ?,
                weekdays = ?, month_days = ?, months = ?, 
                available_quantity = ?, priority = ?, updated = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (name, description, active, scope, start_date, end_date, start_time, end_time,
              weekdays_str, month_days_str, months_str, quantity, priority, rule_id))
        
        # Produkte aktualisieren (für spezifische Regeln)
        if scope == 'specific':
            # Alte Produkte entfernen
            conn.execute('DELETE FROM availability_rule_products WHERE rule_id = ?', (rule_id,))
            # Neue Produkte hinzufügen
            product_ids = request.form.getlist('products')
            for product_id in product_ids:
                conn.execute('''
                    INSERT INTO availability_rule_products (rule_id, product_class_id)
                    VALUES (?, ?)
                ''', (rule_id, int(product_id)))
        else:
            # Alle Produkte entfernen
            conn.execute('DELETE FROM availability_rule_products WHERE rule_id = ?', (rule_id,))
        
        conn.commit()
        flash(f'Verfügbarkeitsregel "{name}" wurde aktualisiert!', 'success')
        conn.close()
        return redirect(url_for('availability_rules'))
    
    # Regel abrufen
    rule = conn.execute('SELECT * FROM availability_rules WHERE id = ?', (rule_id,)).fetchone()
    
    if not rule:
        conn.close()
        flash('Regel nicht gefunden!', 'error')
        return redirect(url_for('availability_rules'))
    
    # Zugehörige Produkte abrufen
    selected_products = []
    if rule['scope'] == 'specific':
        selected_products = conn.execute('''
            SELECT product_class_id FROM availability_rule_products WHERE rule_id = ?
        ''', (rule_id,)).fetchall()
        selected_products = [p['product_class_id'] for p in selected_products]
    
    # Alle Produkte abrufen
    products = conn.execute('''
        SELECT * FROM product_classes 
        WHERE active = 1 AND deleted = 0
        ORDER BY name
    ''').fetchall()
    
    conn.close()
    
    return render_template('admin/edit_availability_rule.html', 
                      rule=rule, products=products, selected_products=selected_products)


@app.route('/admin/availability-rules/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_availability_rule(rule_id):
    """Verfügbarkeitsregel löschen"""
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Regel abrufen
    rule = conn.execute('SELECT name FROM availability_rules WHERE id = ?', (rule_id,)).fetchone()
    
    if rule:
        conn.execute('DELETE FROM availability_rules WHERE id = ?', (rule_id,))
        conn.commit()
        flash(f'Regel "{rule["name"]}" wurde gelöscht!', 'success')
    else:
        flash('Regel nicht gefunden!', 'error')
    
    conn.close()
    return redirect(url_for('availability_rules'))


@app.route('/admin/availability-rules/<int:rule_id>/toggle', methods=['POST'])
@login_required
def toggle_availability_rule(rule_id):
    """Verfügbarkeitsregel aktivieren/deaktivieren"""
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    rule = conn.execute('SELECT active, name FROM availability_rules WHERE id = ?', (rule_id,)).fetchone()
    
    if rule:
        new_active = 0 if rule['active'] else 1
        conn.execute('UPDATE availability_rules SET active = ?, updated = CURRENT_TIMESTAMP WHERE id = ?', 
                  (new_active, rule_id))
        conn.commit()
        status_text = "aktiviert" if new_active else "deaktiviert"
        flash(f'Regel "{rule["name"]}" wurde {status_text}!', 'success')
    else:
        flash('Regel nicht gefunden!', 'error')
    
    conn.close()
    return redirect(url_for('availability_rules'))


# ============================================
# API-Schlüssel-Verwaltung (API Keys)
# ============================================

def generate_api_key():
    """Generiert einen zufälligen API-Schlüssel"""
    import secrets
    import hashlib
    key = f"btf_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return key, key_hash


def verify_api_key(api_key):
    """Validiert einen API-Schlüssel"""
    if not api_key:
        return None
    
    import hashlib
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    conn = get_db_connection()
    key_record = conn.execute('''
        SELECT * FROM api_keys 
        WHERE key_hash = ? AND active = 1
    ''', (key_hash,)).fetchone()
    
    # Prüfen ob abgelaufen
    if key_record and key_record['expires_at']:
        from datetime import datetime
        if datetime.now() > datetime.fromisoformat(key_record['expires_at']):
            conn.close()
            return None
    
    conn.close()
    return key_record


def log_api_usage(api_key_id, endpoint, method, status_code, response_time_ms, ip_address=None, user_agent=None):
    """Loggt API-Nutzung"""
    conn = get_db_connection()
    
    # Usage count aktualisieren
    conn.execute('''
        UPDATE api_keys 
        SET usage_count = usage_count + 1, last_used = CURRENT_TIMESTAMP 
        WHERE id = ?
    ''', (api_key_id,))
    
    # Log-Eintrag
    conn.execute('''
        INSERT INTO api_usage_logs 
        (api_key_id, endpoint, method, status_code, response_time_ms, ip_address, user_agent)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (api_key_id, endpoint, method, status_code, response_time_ms, ip_address, user_agent))
    
    conn.commit()
    conn.close()


@app.route('/admin/api-keys')
@login_required
def api_keys():
    """Admin-Seite für API-Schlüssel"""
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    keys = conn.execute('SELECT * FROM api_keys ORDER BY created DESC').fetchall()
    conn.close()
    
    return render_template('admin/api_keys.html', keys=keys)


@app.route('/admin/api-keys/add', methods=['GET', 'POST'])
@login_required
def add_api_key():
    """Neuen API-Schlüssel erstellen"""
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        permissions = request.form.get('permissions', 'read')
        rate_limit = int(request.form.get('rate_limit', 100))
        expires_at = request.form.get('expires_at', '').strip() or None
        
        # API-Schlüssel generieren
        api_key, key_hash = generate_api_key()
        
        conn.execute('''
            INSERT INTO api_keys (name, key_hash, permissions, rate_limit, expires_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, key_hash, permissions, rate_limit, expires_at))
        
        conn.commit()
        
        # Letztgenierten Schlüssel abrufen
        key_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.close()
        
        # Zeige Schlüssel nur einmalig an
        flash(f'API-Schlüssel erstellt! Dies ist der einzige Zeitpunkt, zu dem Sie den Schlüssel sehen können.', 'success')
        
        return render_template('admin/api_key_created.html', api_key=api_key, key_name=name, key_id=key_id)
    
    conn.close()
    return render_template('admin/add_api_key.html')


@app.route('/admin/api-keys/<int:key_id>/toggle', methods=['POST'])
@login_required
def toggle_api_key(key_id):
    """API-Schlüssel aktivieren/deaktivieren"""
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    key = conn.execute('SELECT active, name FROM api_keys WHERE id = ?', (key_id,)).fetchone()
    
    if key:
        new_active = 0 if key['active'] else 1
        conn.execute('UPDATE api_keys SET active = ?, updated = CURRENT_TIMESTAMP WHERE id = ?', 
                    (new_active, key_id))
        conn.commit()
        status_text = "aktiviert" if new_active else "deaktiviert"
        flash(f'API-Schlüssel "{key["name"]}" wurde {status_text}!', 'success')
    else:
        flash('Schlüssel nicht gefunden!', 'error')
    
    conn.close()
    return redirect(url_for('api_keys'))


@app.route('/admin/api-keys/<int:key_id>/delete', methods=['POST'])
@login_required
def delete_api_key(key_id):
    """API-Schlüssel löschen"""
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    key = conn.execute('SELECT name FROM api_keys WHERE id = ?', (key_id,)).fetchone()
    
    if key:
        conn.execute('DELETE FROM api_keys WHERE id = ?', (key_id,))
        conn.execute('DELETE FROM api_usage_logs WHERE api_key_id = ?', (key_id,))
        conn.commit()
        flash(f'API-Schlüssel "{key["name"]}" wurde gelöscht!', 'success')
    else:
        flash('Schlüssel nicht gefunden!', 'error')
    
    conn.close()
    return redirect(url_for('api_keys'))


@app.route('/admin/api-keys/<int:key_id>/regenerate', methods=['POST'])
@login_required
def regenerate_api_key(key_id):
    """API-Schlüssel neu generieren"""
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    key = conn.execute('SELECT name FROM api_keys WHERE id = ?', (key_id,)).fetchone()
    
    if key:
        api_key, key_hash = generate_api_key()
        conn.execute('''
            UPDATE api_keys 
            SET key_hash = ?, updated = CURRENT_TIMESTAMP, usage_count = 0 
            WHERE id = ?
        ''', (key_hash, key_id))
        conn.commit()
        flash(f'API-Schlüssel für "{key["name"]}" wurde neu generiert!', 'success')
        conn.close()
        return render_template('admin/api_key_created.html', api_key=api_key, key_name=key['name'], key_id=key_id)
    else:
        flash('Schlüssel nicht gefunden!', 'error')
        conn.close()
        return redirect(url_for('api_keys'))


@app.route('/admin/api-docs')
@login_required
def api_docs():
    """API-Dokumentation"""
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    
    return render_template('admin/api_docs.html')


# ============================================
# Öffentliche API-Endpunkte
# ============================================

@app.route('/api/v1/slots', methods=['GET'])
def api_slots():
    """
    GET /api/v1/slots
    
    Gibt Zeit-Slots zurück.
    
    Query-Parameter:
    - date: Datum (YYYY-MM-DD),optional - nur Slots für dieses Datum
    - upcoming: 'true'/'false', optional - nur zukünftige Slots
    - limit: Integer, optional - maximale Anzahl (default: 10)
    
    Antwort:
    {
        "success": true,
        "data": [...],
        "meta": {...}
    }
    """
    start_time = time.time()
    
    # API-Schlüssel validieren
    api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
    key_record = verify_api_key(api_key)
    
    if not key_record:
        return jsonify({
            "success": false,
            "error": "Ungültiger oder abgelaufener API-Schlüssel"
        }), 401
    
    conn = get_db_connection()
    
    # Query-Parameter
    date = request.args.get('date')
    upcoming = request.args.get('upcoming', 'true').lower() == 'true'
    limit = min(int(request.args.get('limit', 10)), 100)
    
    query = 'SELECT * FROM time_slots WHERE 1=1'
    params = []
    
    if date:
        query += ' AND date = ?'
        params.append(date)
    
    if upcoming:
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        query += ' AND date >= ?'
        params.append(today)
    
    query += ' ORDER BY date, start_time LIMIT ?'
    params.append(limit)
    
    slots = conn.execute(query, params).fetchall()
    
    slots_data = []
    for slot in slots:
        slots_data.append({
            'id': slot['id'],
            'date': slot['date'],
            'start_time': slot['start_time'],
            'end_time': slot['end_time'],
            'capacity': slot['capacity'],
            'used_capacity': slot['used_capacity'],
            'available': slot['capacity'] - slot['used_capacity']
        })
    
    conn.close()
    
    response_time = int((time.time() - start_time) * 1000)
    log_api_usage(key_record['id'], '/api/v1/slots', 'GET', 200, response_time, request.remote_addr, request.headers.get('User-Agent'))
    
    return jsonify({
        'success': True,
        'data': slots_data,
        'meta': {
            'total': len(slots_data),
            'date': date or 'all',
            'upcoming': upcoming
        }
    })


@app.route('/api/v1/orders', methods=['GET'])
def api_orders():
    """
    GET /api/v1/orders
    
    Gibt Bestellungen zurück.
    
    Query-Parameter:
    - status: Bestellstatus (new, in_progress, ready, completed, cancelled)
    - date: Datum (YYYY-MM-DD)
    - slot_id: Zeit-Slot-ID
    - from_date: Datum ab (YYYY-MM-DD)
    - to_date: Datum bis (YYYY-MM-DD)
    - limit: maximale Anzahl (default: 50, max: 100)
    
    Antwort:
    {
        "success": true,
        "data": [...],
        "meta": {...}
    }
    """
    start_time = time.time()
    
    api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
    key_record = verify_api_key(api_key)
    
    if not key_record:
        return jsonify({
            "success": False,
            "error": "Ungültiger oder abgelaufener API-Schlüssel"
        }), 401
    
    # Nur Lese-Zugriff erlauben
    if 'read' not in key_record['permissions']:
        return jsonify({
            "success": False,
            "error": "Keine Lese-Berechtigung"
        }), 403
    
    conn = get_db_connection()
    
    # Query-Parameter
    status = request.args.get('status')
    date = request.args.get('date')
    slot_id = request.args.get('slot_id', type=int)
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    limit = min(int(request.args.get('limit', 50)), 100)
    
    query = 'SELECT o.*, GROUP_CONCAT(pc.name) as products FROM orders o'
    joins_needed = 'LEFT JOIN order_items oi ON o.id = oi.order_id LEFT JOIN product_classes pc ON oi.product_class_id = pc.id'
    
    where = []
    params = []
    
    if status:
        where.append('o.status = ?')
        params.append(status)
    
    if date:
        where.append('o.pickup_date = ?')
        params.append(date)
    
    if slot_id:
        query += f' {joins_needed}'
        where.append('EXISTS (SELECT 1 FROM order_item_slots ois JOIN order_items oi2 ON ois.order_item_id = oi2.id WHERE oi2.order_id = o.id AND ois.slot_id = ?)')
        params.append(slot_id)
    
    if from_date:
        where.append('o.pickup_date >= ?')
        params.append(from_date)
    
    if to_date:
        where.append('o.pickup_date <= ?')
        params.append(to_date)
    
    if where:
        query += ' WHERE ' + ' AND '.join(where)
    
    query += ' GROUP BY o.id ORDER BY o.pickup_date, o.pickup_time LIMIT ?'
    params.append(limit)
    
    orders = conn.execute(query, params).fetchall()
    
    orders_data = []
    for order in orders:
        items = conn.execute('''
            SELECT oi.quantity, pc.name, pc.id as product_id
            FROM order_items oi
            JOIN product_classes pc ON oi.product_class_id = pc.id
            WHERE oi.order_id = ?
        ''', (order['id'],)).fetchall()
        
        orders_data.append({
            'id': order['id'],
            'order_number': order['order_number'],
            'customer_name': order['customer_name'],
            'customer_email': order['customer_email'],
            'pickup_date': order['pickup_date'],
            'pickup_time': order['pickup_time'],
            'status': order['status'],
            'payment_method': order.get('payment_method', 'cash'),
            'items': [{'product_id': item['product_id'], 'name': item['name'], 'quantity': item['quantity']} for item in items],
            'created': order['created']
        })
    
    conn.close()
    
    response_time = int((time.time() - start_time) * 1000)
    log_api_usage(key_record['id'], '/api/v1/orders', 'GET', 200, response_time, request.remote_addr, request.headers.get('User-Agent'))
    
    return jsonify({
        'success': True,
        'data': orders_data,
        'meta': {
            'total': len(orders_data),
            'filters': {
                'status': status,
                'date': date,
                'slot_id': slot_id,
                'from_date': from_date,
                'to_date': to_date
            }
        }
    })


@app.route('/api/v1/orders/<int:order_id>', methods=['GET'])
def api_order_detail(order_id):
    """
    GET /api/v1/orders/{id}
    
    Gibt Details einer einzelnen Bestellung zurück.
    """
    start_time = time.time()
    
    api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
    key_record = verify_api_key(api_key)
    
    if not key_record:
        return jsonify({
            "success": False,
            "error": "Ungültiger oder abgelepener API-Schlüssel"
        }), 401
    
    if 'read' not in key_record['permissions']:
        return jsonify({
            "success": False,
            "error": "Keine Lese-Berechtigung"
        }), 403
    
    conn = get_db_connection()
    order = conn.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
    
    if not order:
        conn.close()
        return jsonify({
            "success": False,
            "error": "Bestellung nicht gefunden"
        }), 404
    
    # Items abrufen
    items = conn.execute('''
        SELECT oi.*, pc.name, pc.id as product_id
        FROM order_items oi
        JOIN product_classes pc ON oi.product_class_id = pc.id
        WHERE oi.order_id = ?
    ''', (order_id,)).fetchall()
    
    # Refinements abrufen
    items_list = []
    for item in items:
        refinements = conn.execute('''
            SELECT r.name
            FROM order_item_refinements oir
            JOIN refinements r ON oir.refinement_id = r.id
            WHERE oir.order_item_id = ?
        ''', (item['id'],)).fetchall()
        
        items_list.append({
            'product_id': item['product_id'],
            'product_name': item['name'],
            'quantity': item['quantity'],
            'refinements': [r['name'] for r in refinements]
        })
    
    conn.close()
    
    response_time = int((time.time() - start_time) * 1000)
    log_api_usage(key_record['id'], f'/api/v1/orders/{order_id}', 'GET', 200, response_time, request.remote_addr, request.headers.get('User-Agent'))
    
    return jsonify({
        'success': True,
        'data': {
            'id': order['id'],
            'order_number': order['order_number'],
            'customer_name': order['customer_name'],
            'customer_email': order['customer_email'],
            'pickup_date': order['pickup_date'],
            'pickup_time': order['pickup_time'],
            'status': order['status'],
            'payment_method': order.get('payment_method', 'cash'),
            'items': items_list,
            'created': order['created']
        }
    })


@app.route('/api/v1/products', methods=['GET'])
def api_products():
    """
    GET /api/v1/products
    
    Gibt Produkte zurück.
    
    Query-Parameter:
    - active: 'true'/'false' - nur aktive Produkte
    - product_type: Produkt-Typ
    """
    start_time = time.time()
    
    api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
    key_record = verify_api_key(api_key)
    
    if not key_record:
        return jsonify({
            "success": False,
            "error": "Ungültiger oder abgelaufener API-Schlüssel"
        }), 401
    
    conn = get_db_connection()
    
    active_only = request.args.get('active', 'true').lower() == 'true'
    product_type = request.args.get('product_type')
    
    query = 'SELECT * FROM product_classes WHERE deleted = 0'
    params = []
    
    if active_only:
        query += ' AND active = 1'
    
    if product_type:
        query += ' AND product_type = ?'
        params.append(product_type)
    
    query += ' ORDER BY name'
    
    products = conn.execute(query, params).fetchall()
    
    products_data = [{
        'id': p['id'],
        'name': p['name'],
        'description': p['description'],
        'base_price': float(p['base_price']),
        'product_type': p['product_type'],
        'capacity': p['capacity'],
        'label': p['label'],
        'active': bool(p['active'])
    } for p in products]
    
    conn.close()
    
    response_time = int((time.time() - start_time) * 1000)
    log_api_usage(key_record['id'], '/api/v1/products', 'GET', 200, response_time, request.remote_addr, request.headers.get('User-Agent'))
    
    return jsonify({
        'success': True,
        'data': products_data,
        'meta': {'total': len(products_data)}
    })


@app.route('/api/v1/availability', methods=['GET'])
def api_availability():
    """
    GET /api/v1/availability
    
    Gibt Produktverfügbarkeit zurück.
    
    Query-Parameter:
    - product_id: Produkt-ID (erforderlich)
    - date: Datum (YYYY-MM-DD), optional
    
    Antwort:
    {
        "success": true,
        "data": {
            "product_id": 1,
            "date": "2024-01-01",
            "available_quantity": 10,
            "rule_applied": {...} oder null
        }
    }
    """
    start_time = time.time()
    
    api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
    key_record = verify_api_key(api_key)
    
    if not key_record:
        return jsonify({
            "success": False,
            "error": "Ungültiger oder abgelaufener API-Schlüssel"
        }), 401
    
    product_id = request.args.get('product_id', type=int)
    if not product_id:
        return jsonify({
            "success": False,
            "error": "product_id ist erforderlich"
        }), 400
    
    date = request.args.get('date') or datetime.now().strftime('%Y-%m-%d')
    
    available = get_product_availability_for_date(product_id, date)
    
    response_time = int((time.time() - start_time) * 1000)
    log_api_usage(key_record['id'], '/api/v1/availability', 'GET', 200, response_time, request.remote_addr, request.headers.get('User-Agent'))
    
    return jsonify({
        'success': True,
        'data': {
            'product_id': product_id,
            'date': date,
            'available_quantity': available
        }
    })


@app.route('/api/v1/health', methods=['GET'])
def api_health():
    """Health-Check-Endpunkt"""
    return jsonify({
        'success': True,
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    # Datenbank auf neuesten Stand bringen
    init_db()
    app.run(debug=True, host="0.0.0.0", port=1234) 