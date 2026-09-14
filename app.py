import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'rotoblessing_clave_secreta_super_segura_2026'

# --- CONFIGURACIÓN DE BASE DE DATOS ---
# Detecta automáticamente la variable de entorno DATABASE_URL de Render (PostgreSQL)
# O utiliza SQLite como respaldo para pruebas locales si no está definida
db_url = os.environ.get('DATABASE_URL', 'sqlite:///rotoblessing.db')

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- CLAVES SECRETAS DE VERIFICACIÓN PARA ROLES RESTRINGIDOS ---
CLAVE_VENDEDOR = "ROTO2026_VENDEDOR"
CLAVE_DUENO = "ROTO2026_DUENO"

# --- MODELOS DE BASE DE DATOS ---
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default='Comprador') # Roles: Comprador, Vendedor, Dueno

class Mensaje(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    emisor_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    receptor_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    contenido = db.Column(db.Text, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

    emisor = db.relationship('Usuario', foreign_keys=[emisor_id], backref='mensajes_enviados')
    receptor = db.relationship('Usuario', foreign_keys=[receptor_id], backref='mensajes_recibidos')

with app.app_context():
    db.create_all()

# --- RUTAS PRINCIPALES Y AUTENTICACIÓN ---

@app.route('/')
def index():
    usuario_actual = None
    if 'usuario_id' in session:
        usuario_actual = Usuario.query.get(session['usuario_id'])
    return render_template('index.html', usuario=usuario_actual)

@app.route('/registro', methods=['POST'])
def registro():
    nombre = request.form.get('nombre')
    email = request.form.get('email')
    password = request.form.get('password')
    rol = request.form.get('rol')
    codigo_verificacion = request.form.get('codigo_verificacion')

    if not email or not password or not nombre or not rol:
        flash('Por favor completa todos los campos requeridos.', 'danger')
        return redirect(url_for('index'))

    email = email.strip().lower()

    # Validar código de seguridad según el rol seleccionado
    if rol == 'Vendedor' and codigo_verificacion != CLAVE_VENDEDOR:
        flash('El código de verificación para Vendedor es incorrecto.', 'danger')
        return redirect(url_for('index'))

    if rol == 'Dueno' and codigo_verificacion != CLAVE_DUENO:
        flash('El código de verificación para Dueño / Administrador es incorrecto.', 'danger')
        return redirect(url_for('index'))

    if Usuario.query.filter_by(email=email).first():
        flash('El correo electrónico ya se encuentra registrado.', 'danger')
        return redirect(url_for('index'))

    hashed_pw = generate_password_hash(password, method='scrypt')
    nuevo_usuario = Usuario(nombre=nombre, email=email, password=hashed_pw, rol=rol)
    
    db.session.add(nuevo_usuario)
    db.session.commit()

    session.permanent = True
    session['usuario_id'] = nuevo_usuario.id

    flash(f'¡Cuenta creada exitosamente! Bienvenido, {nombre}.', 'success')
    return redirect(url_for('index'))

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')

    usuario = Usuario.query.filter_by(email=email).first()

    if usuario and check_password_hash(usuario.password, password):
        session.permanent = True
        session['usuario_id'] = usuario.id
        flash(f'Sesión iniciada correctamente. ¡Hola de nuevo, {usuario.nombre}!', 'success')
        return redirect(url_for('index'))
    else:
        flash('Correo electrónico o contraseña incorrectos.', 'danger')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('usuario_id', None)
    flash('Has cerrado sesión correctamente.', 'info')
    return redirect(url_for('index'))

# --- RUTAS DE MENSAJERÍA Y CHAT ---

@app.route('/mensajes')
@app.route('/mensajes/<int:contacto_id>')
def centro_mensajes(contacto_id=None):
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión para acceder al centro de mensajes.', 'warning')
        return redirect(url_for('index'))

    usuario_actual = Usuario.query.get(session['usuario_id'])
    contactos = Usuario.query.filter(Usuario.id != usuario_actual.id).all()
    
    contacto_seleccionado = None
    mensajes_chat = []

    if contacto_id:
        contacto_seleccionado = Usuario.query.get(contacto_id)
        if contacto_seleccionado:
            mensajes_chat = Mensaje.query.filter(
                ((Mensaje.emisor_id == usuario_actual.id) & (Mensaje.receptor_id == contacto_id)) |
                ((Mensaje.emisor_id == contacto_id) & (Mensaje.receptor_id == usuario_actual.id))
            ).order_by(Mensaje.fecha.asc()).all()

    return render_template(
        'mensajes.html',
        usuario=usuario_actual,
        contactos=contactos,
        contacto_seleccionado=contacto_seleccionado,
        mensajes_chat=mensajes_chat
    )

@app.route('/enviar_mensaje/<int:receptor_id>', methods=['POST'])
def enviar_mensaje(receptor_id):
    if 'usuario_id' not in session:
        return redirect(url_for('index'))

    contenido = request.form.get('contenido', '').strip()
    if contenido:
        nuevo_mensaje = Mensaje(
            emisor_id=session['usuario_id'],
            receptor_id=receptor_id,
            contenido=contenido
        )
        db.session.add(nuevo_mensaje)
        db.session.commit()

    return redirect(url_for('centro_mensajes', contacto_id=receptor_id))

if __name__ == '__main__':
    app.run(debug=True)
