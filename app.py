import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from parser_solver import procesar_excel_solver, normalizar_nombre, evaluar_sla_ticket

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(32).hex()
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

DB_PATH = 'gestion_apple.db'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_num TEXT UNIQUE NOT NULL,
            tipo TEXT NOT NULL,
            direccion TEXT,
            responsable TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Pendiente',
            fecha_inicio TEXT,
            fecha_fin TEXT,
            tiempo_horas REAL DEFAULT 0,
            prioridad TEXT DEFAULT '5 - Planning',
            reasignaciones INTEGER DEFAULT 0,
            sla_estado TEXT DEFAULT 'Cumplido',
            sla_meta_horas REAL DEFAULT 24.0
        )
    """)
    # Migración segura si la BD existía de una versión anterior sin columnas SLA
    cols = [c[1] for c in cur.execute("PRAGMA table_info(tickets)").fetchall()]
    for col_sql in [
        ("prioridad", "ALTER TABLE tickets ADD COLUMN prioridad TEXT DEFAULT '5 - Planning'"),
        ("reasignaciones", "ALTER TABLE tickets ADD COLUMN reasignaciones INTEGER DEFAULT 0"),
        ("sla_estado", "ALTER TABLE tickets ADD COLUMN sla_estado TEXT DEFAULT 'Cumplido'"),
        ("sla_meta_horas", "ALTER TABLE tickets ADD COLUMN sla_meta_horas REAL DEFAULT 24.0")
    ]:
        if col_sql[0] not in cols:
            cur.execute(col_sql[1])

    cur.execute("SELECT id FROM users WHERE username = 'admin'")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ('admin', generate_password_hash('Admin2026!'), 'admin')
        )
    conn.commit()
    conn.close()


@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    row = conn.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if row:
        return User(row['id'], row['username'], row['role'])
    return None


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if row and check_password_hash(row['password_hash'], password):
            login_user(User(row['id'], row['username'], row['role']))
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='Usuario o contraseña incorrectos')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html')


@app.route('/api/tickets', methods=['GET'])
@login_required
def get_tickets():
    responsable = request.args.get('responsable', 'Todos')
    periodo = request.args.get('periodo', 'todos')

    conn = get_db()
    query = "SELECT * FROM tickets WHERE 1=1"
    params = []

    if responsable != 'Todos':
        query += " AND responsable = ?"
        params.append(responsable)

    if periodo != 'todos':
        max_row = conn.execute("SELECT MAX(fecha_inicio) as max_f FROM tickets").fetchone()
        ref_date = datetime.now()
        if max_row and max_row['max_f']:
            try:
                ref_date = datetime.strptime(max_row['max_f'][:16], '%Y-%m-%d %H:%M')
            except ValueError:
                pass
        deltas = {'dia': 1, 'semana': 7, 'mes': 30}
        if periodo in deltas:
            cutoff = (ref_date - timedelta(days=deltas[periodo])).strftime('%Y-%m-%d %H:%M')
            query += " AND fecha_inicio >= ?"
            params.append(cutoff)

    query += " ORDER BY fecha_inicio DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/tickets', methods=['POST'])
@login_required
def create_ticket():
    data = request.json or {}
    ticket_num = data.get('ticket_num', '').strip().upper()
    if not ticket_num:
        return jsonify({'error': 'El número de ticket es obligatorio'}), 400

    tipo = data.get('tipo', 'Incidente')
    f_ini = data.get('fecha_inicio', '').replace('T', ' ')
    f_fin = data.get('fecha_fin', '').replace('T', ' ')
    estado = 'Cerrado' if f_fin else 'Pendiente'
    horas = 0.0

    if f_ini and f_fin:
        try:
            dt1 = datetime.strptime(f_ini[:16], '%Y-%m-%d %H:%M')
            dt2 = datetime.strptime(f_fin[:16], '%Y-%m-%d %H:%M')
            horas = max(round((dt2 - dt1).total_seconds() / 3600.0, 2), 0.0)
        except ValueError:
            pass

    sla_estado, sla_meta = evaluar_sla_ticket(tipo, horas, 0, estado)
    prioridad = '5 - Planning' if tipo == 'Incidente' else '4 - Low'

    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO tickets (
                ticket_num, tipo, direccion, responsable, estado, fecha_inicio, fecha_fin,
                tiempo_horas, prioridad, reasignaciones, sla_estado, sla_meta_horas
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (
            ticket_num, tipo, data.get('direccion', ''),
            normalizar_nombre(data.get('responsable', '')), estado,
            f_ini, f_fin, horas, prioridad, sla_estado, sla_meta
        ))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': f'El ticket {ticket_num} ya existe en la base de datos'}), 409
    conn.close()
    return jsonify({'message': 'Ticket registrado correctamente'})


@app.route('/api/tickets/<int:ticket_id>/close', methods=['POST'])
@login_required
def close_ticket(ticket_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Ticket no encontrado'}), 404

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    horas = row['tiempo_horas']
    if row['fecha_inicio']:
        try:
            dt1 = datetime.strptime(row['fecha_inicio'][:16], '%Y-%m-%d %H:%M')
            dt2 = datetime.strptime(now_str, '%Y-%m-%d %H:%M')
            horas = max(round((dt2 - dt1).total_seconds() / 3600.0, 2), 0.0)
        except ValueError:
            pass

    sla_estado, sla_meta = evaluar_sla_ticket(row['tipo'], horas, row['reasignaciones'], 'Cerrado')

    conn.execute(
        "UPDATE tickets SET estado = 'Cerrado', fecha_fin = ?, tiempo_horas = ?, sla_estado = ?, sla_meta_horas = ? WHERE id = ?",
        (now_str, horas, sla_estado, sla_meta, ticket_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Ticket cerrado'})


@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No se adjuntó ningún archivo'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'Nombre de archivo vacío'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        registros = procesar_excel_solver(filepath)
    except Exception as e:
        return jsonify({'error': f'Error al leer estructura del archivo: {str(e)}'}), 400

    conn = get_db()
    insertados = 0
    actualizados = 0
    for r in registros:
        existe = conn.execute("SELECT id FROM tickets WHERE ticket_num = ?", (r['ticket_num'],)).fetchone()
        if existe:
            conn.execute("""
                UPDATE tickets
                SET tipo=?, direccion=?, responsable=?, estado=?, fecha_inicio=?, fecha_fin=?,
                    tiempo_horas=?, prioridad=?, reasignaciones=?, sla_estado=?, sla_meta_horas=?
                WHERE ticket_num=?
            """, (
                r['tipo'], r['direccion'], r['responsable'], r['estado'],
                r['fecha_inicio'], r['fecha_fin'], r['tiempo_horas'],
                r['prioridad'], r['reasignaciones'], r['sla_estado'], r['sla_meta_horas'],
                r['ticket_num']
            ))
            actualizados += 1
        else:
            conn.execute("""
                INSERT INTO tickets (
                    ticket_num, tipo, direccion, responsable, estado, fecha_inicio, fecha_fin,
                    tiempo_horas, prioridad, reasignaciones, sla_estado, sla_meta_horas
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r['ticket_num'], r['tipo'], r['direccion'], r['responsable'],
                r['estado'], r['fecha_inicio'], r['fecha_fin'], r['tiempo_horas'],
                r['prioridad'], r['reasignaciones'], r['sla_estado'], r['sla_meta_horas']
            ))
            insertados += 1
    conn.commit()
    conn.close()

    return jsonify({
        'message': f'Sincronización exitosa: {insertados} nuevos, {actualizados} actualizados (Total: {len(registros)}).'
    })


@app.route('/api/users', methods=['POST'])
@login_required
def create_user():
    if current_user.role != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'user')
    if not username or not password:
        return jsonify({'error': 'Datos incompletos'}), 400

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), role)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'El usuario ya existe'}), 409
    conn.close()
    return jsonify({'message': 'Usuario creado'})


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)

init_db()
