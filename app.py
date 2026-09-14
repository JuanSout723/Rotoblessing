from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)

# Clave secreta fija para mantener la sesión iniciada correctamente
app.secret_key = 'rotoblessing_clave_secreta_super_segura_2026'

# Configuración de base de datos SQLite integrada
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'rotoblessing.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# 1. Modelo de Usuarios (Comprador, Vendedor, Dueño)
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(30), nullable=False, default='Comprador') # Comprador, Vendedor, Dueno

# 2. Modelo de Mensajes
class Mensaje(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    remitente_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    destinatario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True) # None = Mensaje general a la empresa
    contenido = db.Column(db.Text, nullable=False)
    fecha = db.Column(db.DateTime, default=db.func.now())

    remitente = db.relationship('Usuario', foreign_keys=[remitente_id])

with app.app_context():
    db.create_all()

# --- RUTAS DE LA APLICACIÓN ---

# Página Principal
@app.route('/')
def index():
    usuario_actual = None
    if 'usuario_id' in session:
        usuario_actual = Usuario.query.get(session['usuario_id'])
    return render_template('index.html', usuario=usuario_actual)

# REGISTRO DE USUARIOS
@app.route('/registro', methods=['POST'])
def registro():
    nombre = request.form.get('nombre')
    email = request.form.get('email')
    password = request.form.get('password')
    rol = request.form.get('rol') # Comprador, Vendedor o Dueno

    if not email or not password or not nombre:
        flash('Por favor completa todos los campos.', 'danger')
        return redirect(url_for('index'))

    # Limpieza de correo (convertir a minúsculas y quitar espacios)
    email = email.strip().lower()

    if Usuario.query.filter_by(email=email).first():
        flash('El correo ya está registrado.', 'danger')
        return redirect(url_for('index'))

    # Cifrado seguro de contraseña
    hashed_pw = generate_password_hash(password, method='scrypt')
    nuevo_usuario = Usuario(nombre=nombre, email=email, password=hashed_pw, rol=rol)
    
    db.session.add(nuevo_usuario)
    db.session.commit()

    # Iniciar sesión automáticamente tras registrarse
    session.permanent = True
    session['usuario_id'] = nuevo_usuario.id

    flash(f'¡Bienvenido {nombre}! Cuenta creada con éxito.', 'success')
    return redirect(url_for('index'))

# INICIO DE SESIÓN
@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')

    if not email or not password:
        flash('Ingresa tu correo y contraseña.', 'danger')
        return redirect(url_for('index'))

    email = email.strip().lower()
    user = Usuario.query.filter_by(email=email).first()

    if user and check_password_hash(user.password, password):
        session.permanent = True
        session['usuario_id'] = user.id
        flash(f'Hola de nuevo, {user.nombre}.', 'success')
    else:
        flash('Correo o contraseña incorrectos.', 'danger')

    return redirect(url_for('index'))

# CERRAR SESIÓN
@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada correctamente.', 'info')
    return redirect(url_for('index'))

# ENVIAR MENSAJE / RESPONDER
@app.route('/enviar_mensaje', methods=['POST'])
def enviar_mensaje():
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión para enviar mensajes.', 'warning')
        return redirect(url_for('index'))

    contenido = request.form.get('mensaje')
    destinatario_id = request.form.get('destinatario_id')

    if not contenido:
        return redirect(url_for('mensajes'))

    nuevo_msg = Mensaje(
        remitente_id=session['usuario_id'],
        destinatario_id=int(destinatario_id) if destinatario_id else None,
        contenido=contenido
    )
    db.session.add(nuevo_msg)
    db.session.commit()

    if destinatario_id:
        return redirect(url_for('mensajes', cliente_id=destinatario_id))
    return redirect(url_for('mensajes'))

# BANDEJA DE MENSAJES ESTILO WHATSAPP
@app.route('/mensajes')
def mensajes():
    if 'usuario_id' not in session:
        flash('Por favor inicia sesión para ingresar.', 'warning')
        return redirect(url_for('index'))

    user = Usuario.query.get(session['usuario_id'])
    if not user:
        session.clear()
        return redirect(url_for('index'))

    cliente_seleccionado = None
    conversacion = []
    lista_clientes = []

    if user.rol == 'Comprador':
        # El comprador ve su chat con la empresa
        conversacion = Mensaje.query.filter(
            (Mensaje.remitente_id == user.id) | (Mensaje.destinatario_id == user.id)
        ).order_by(Mensaje.fecha.asc()).all()
    else:
        # Vendedor / Dueño: Obtiene la lista de todos los compradores
        subquery = db.session.query(Mensaje.remitente_id).distinct()
        lista_clientes = Usuario.query.filter(Usuario.id.in_(subquery), Usuario.rol == 'Comprador').all()

        cliente_id = request.args.get('cliente_id')
        if cliente_id:
            cliente_seleccionado = Usuario.query.get(cliente_id)
            conversacion = Mensaje.query.filter(
                ((Mensaje.remitente_id == cliente_id) & (Mensaje.destinatario_id == None)) |
                ((Mensaje.remitente_id == cliente_id) & (Mensaje.destinatario_id == user.id)) |
                ((Mensaje.remitente_id == user.id) & (Mensaje.destinatario_id == cliente_id))
            ).order_by(Mensaje.fecha.asc()).all()

    return render_template(
        'mensajes.html', 
        usuario=user, 
        clientes=lista_clientes, 
        conversacion=conversacion, 
        cliente_actual=cliente_seleccionado
    )

if __name__ == '__main__':
    app.run(debug=True)
