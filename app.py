import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clave_secreta_super_segura_rotoblessing')

# Configuración de la base de datos (Compatible con PostgreSQL en Render y SQLite local)
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///rotoblessing.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MODELOS DE LA BASE DE DATOS ---

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(50), nullable=False, default='Comprador')

class Mensaje(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    emisor_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    receptor_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    contenido = db.Column(db.Text, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

# Crear las tablas automáticamente si no existen
with app.app_context():
    db.create_all()

# --- RUTAS DE NAVEGACIÓN Y AUTENTICACIÓN ---

@app.route('/')
def index():
    usuario_id = session.get('usuario_id')
    usuario = Usuario.query.get(usuario_id) if usuario_id else None
    return render_template('index.html', usuario=usuario)

@app.route('/registro', methods=['POST'])
def registro():
    nombre = request.form.get('nombre')
    email = request.form.get('email')
    password = request.form.get('password')
    rol = request.form.get('rol')
    codigo = request.form.get('codigo_verificacion', '').strip()

    # --- CLAVES SECRETAS DE VERIFICACIÓN ---
    CLAVE_VENDEDOR = "VENDEDOR2026"
    CLAVE_DUENO = "ADMIN2026"

    # Validación estricta en el servidor para Vendedor
    if rol == 'Vendedor' and codigo != CLAVE_VENDEDOR:
        flash('Código de verificación incorrecto para el rol de Vendedor.', 'danger')
        return redirect(url_for('index'))

    # Validación estricta en el servidor para Dueño / Administrador
    if rol == 'Dueno' and codigo != CLAVE_DUENO:
        flash('Código de verificación incorrecto para el rol de Dueño/Administrador.', 'danger')
        return redirect(url_for('index'))

    # Verificar si el correo ya existe
    usuario_existente = Usuario.query.filter_by(email=email).first()
    if usuario_existente:
        flash('El correo electrónico ya está registrado.', 'danger')
        return redirect(url_for('index'))

    nuevo_usuario = Usuario(nombre=nombre, email=email, password=password, rol=rol)
    db.session.add(nuevo_usuario)
    db.session.commit()

    flash('¡Registro exitoso! Ya puedes iniciar sesión.', 'success')
    return redirect(url_for('index'))

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')

    usuario = Usuario.query.filter_by(email=email, password=password).first()

    if usuario:
        session['usuario_id'] = usuario.id
        flash(f'¡Bienvenido de nuevo, {usuario.nombre}!', 'success')
    else:
        flash('Correo o contraseña incorrectos.', 'danger')

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

    # Redirige de vuelta al chat del cliente usando el parámetro que lee el HTML
    return redirect(url_for('centro_mensajes', cliente_id=receptor_id))

if __name__ == '__main__':
    app.run(debug=True)
