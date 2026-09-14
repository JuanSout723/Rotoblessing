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
    
    # Relación para que el HTML pueda leer {{ msg.remitente.nombre }} sin errores
    remitente = db.relationship('Usuario', foreign_keys=[emisor_id])

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
def centro_mensajes():
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión para acceder al centro de mensajes.', 'warning')
        return redirect(url_for('index'))

    usuario_actual = Usuario.query.get(session['usuario_id'])
    
    clientes = []
    cliente_actual = None
    conversacion = []

    if usuario_actual.rol == 'Comprador':
        # SI ES COMPRADOR: Le asignamos automáticamente el primer vendedor/dueño disponible
        vendedor_principal = Usuario.query.filter(Usuario.rol != 'Comprador').first()
        if vendedor_principal:
            cliente_actual = vendedor_principal
            conversacion = Mensaje.query.filter(
                ((Mensaje.emisor_id == usuario_actual.id) & (Mensaje.receptor_id == vendedor_principal.id)) |
                ((Mensaje.emisor_id == vendedor_principal.id) & (Mensaje.receptor_id == usuario_actual.id))
            ).order_by(Mensaje.fecha.asc()).all()
    else:
        # SI ES VENDEDOR O DUEÑO: Muestra la lista de los demás usuarios y el chat del cliente seleccionado
        clientes = Usuario.query.filter(Usuario.id != usuario_actual.id).all()
        
        cliente_id = request.args.get('cliente_id')
        if cliente_id:
            cliente_actual = Usuario.query.get(cliente_id)
            if cliente_actual:
                conversacion = Mensaje.query.filter(
                    ((Mensaje.emisor_id == usuario_actual.id) & (Mensaje.receptor_id == cliente_id)) |
                    ((Mensaje.emisor_id == cliente_id) & (Mensaje.receptor_id == usuario_actual.id))
                ).order_by(Mensaje.fecha.asc()).all()

    return render_template(
        'mensajes.html',
        usuario=usuario_actual,
        clientes=clientes,
        cliente_actual=cliente_actual,
        conversacion=conversacion
    )

@app.route('/enviar_mensaje', methods=['POST'])
def enviar_mensaje():
    if 'usuario_id' not in session:
        return redirect(url_for('index'))

    usuario_actual = Usuario.query.get(session['usuario_id'])
    contenido = request.form.get('contenido', '').strip()
    
    destinatario_id = None

    if usuario_actual.rol == 'Comprador':
        # Si es comprador, el destinatario por defecto es el primer vendedor/dueño disponible
        vendedor_principal = Usuario.query.filter(Usuario.rol != 'Comprador').first()
        if vendedor_principal:
            destinatario_id = vendedor_principal.id
    else:
        # Si es vendedor/dueño, lee el input oculto del formulario HTML
        destinatario_id = request.form.get('destinatario_id')

    if contenido and destinatario_id:
        try:
            nuevo_mensaje = Mensaje(
                emisor_id=usuario_actual.id,
                receptor_id=destinatario_id,
                contenido=contenido
            )
            db.session.add(nuevo_mensaje)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error al guardar el mensaje: {e}")
            flash("Hubo un error al enviar el mensaje.", "danger")

    # Redirección inteligente adaptada al rol
    if usuario_actual.rol == 'Comprador':
        return redirect(url_for('centro_mensajes'))
    else:
        return redirect(url_for('centro_mensajes', cliente_id=destinatario_id))

if __name__ == '__main__':
    app.run(debug=True)
