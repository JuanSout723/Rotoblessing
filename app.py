from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = 'rotoblessing_clave_secreta_super_segura'

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

# REGISTRO DE USUARIOS (Guarda si es Comprador, Vendedor o Dueño)
@app.route('/registro', methods=['POST'])
def registro():
    nombre = request.form.get('nombre')
    email = request.form.get('email')
    password = request.form.get('password')
    rol = request.form.get('rol') # Comprador, Vendedor o Dueno

    if Usuario.query.filter_by(email=email).first():
        flash('El correo ya está registrado.', 'danger')
        return redirect(url_for('index'))

    # Cifrado seguro de contraseña
    hashed_pw = generate_password_hash(password, method='scrypt')
    nuevo_usuario = Usuario(nombre=nombre, email=email, password=hashed_pw, rol=rol)
    
    db.session.add(nuevo_usuario)
    db.session.commit()

    # Iniciar sesión automáticamente tras registrarse
    session['usuario_id'] = nuevo_usuario.id
    session['usuario_nombre'] = nuevo_usuario.nombre
    session['usuario_rol'] = nuevo_usuario.rol

    flash(f'¡Bienvenido {nombre}! Cuenta creada con éxito.', 'success')
    return redirect(url_for('index'))

# INICIO DE SESIÓN
@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')

    user = Usuario.query.filter_by(email=email).first()

    if user and check_password_hash(user.password, password):
        session['usuario_id'] = user.id
        session['usuario_nombre'] = user.nombre
        session['usuario_rol'] = user.rol
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

# ENVIAR MENSAJE
@app.route('/enviar_mensaje', methods=['POST'])
def enviar_mensaje():
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión para enviar mensajes.', 'warning')
        return redirect(url_for('index'))

    contenido = request.form.get('mensaje')

    nuevo_msg = Mensaje(
        remitente_id=session['usuario_id'],
        contenido=contenido
    )
    db.session.add(nuevo_msg)
    db.session.commit()

    flash('Mensaje enviado al equipo.', 'success')
    return redirect(url_for('mensajes'))

# BANDEJA DE MENSAJES ESTILO WHATSAPP
@app.route('/mensajes')
def mensajes():
    if 'usuario_id' not in session:
        flash('Por favor inicia sesión para ingresar.', 'warning')
        return redirect(url_for('index'))

    user = Usuario.query.get(session['usuario_id'])
    cliente_seleccionado = None
    conversacion = []
    lista_clientes = []

    if user.rol == 'Comprador':
        # El comprador solo ve su chat con la empresa
        conversacion = Mensaje.query.filter(
            (Mensaje.remitente_id == user.id) | (Mensaje.destinatario_id == user.id)
        ).order_by(Mensaje.fecha.asc()).all()
    else:
        # Vendedor / Dueño: Obtiene la lista de todos los compradores que han escrito
        subquery = db.session.query(Mensaje.remitente_id).distinct()
        lista_clientes = Usuario.query.filter(Usuario.id.in_(subquery), Usuario.rol == 'Comprador').all()

        # Obtener el cliente seleccionado de la URL (ej: /mensajes?cliente_id=2)
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
    
    # Comprador: Ve solo sus mensajes enviados y recibidos
    if user.rol == 'Comprador':
        lista_mensajes = Mensaje.query.filter(
            (Mensaje.remitente_id == user.id) | (Mensaje.destinatario_id == user.id)
        ).order_by(Mensaje.fecha.asc()).all()
    else:
        # Vendedores / Dueños: Ven todos los mensajes recibidos de los clientes
        lista_mensajes = Mensaje.query.order_by(Mensaje.fecha.asc()).all()

    return render_template('mensajes.html', usuario=user, mensajes=lista_mensajes)

if __name__ == '__main__':
    app.run(debug=True)
