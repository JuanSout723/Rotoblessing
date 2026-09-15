import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clave_secreta_super_segura_rotoblessing')

# Configuración de carpeta para guardar las fotos de los comentarios
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Asegurarse de que la carpeta de subidas exista
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def archivo_permitido(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

class Comentario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    contenido = db.Column(db.Text, nullable=False)
    foto = db.Column(db.String(200), nullable=True) # Guarda la ruta de la foto opcional
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relación para acceder al autor fácilmente: {{ c.autor.nombre }}
    autor = db.relationship('Usuario', foreign_keys=[usuario_id])

# Crear las tablas automáticamente si no existen
with app.app_context():
    db.create_all()

# --- RUTAS DE NAVEGACIÓN Y AUTENTICACIÓN ---

@app.route('/')
def index():
    usuario_id = session.get('usuario_id')
    usuario = Usuario.query.get(usuario_id) if usuario_id else None
    
    # Recuperamos todos los comentarios ordenados del más reciente al más antiguo
    comentarios = Comentario.query.order_by(Comentario.fecha.desc()).all()
    
    return render_template('index.html', usuario=usuario, comentarios=comentarios)

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
        # SI ES VENDEDOR O DUEÑO: Buscamos únicamente los IDs de usuarios que tienen mensajes con el usuario actual
        mensajes_enviados = db.session.query(Mensaje.receptor_id).filter(Mensaje.emisor_id == usuario_actual.id)
        mensajes_recibidos = db.session.query(Mensaje.emisor_id).filter(Mensaje.receptor_id == usuario_actual.id)
        
        # Unimos ambas consultas para obtener los IDs únicos de las personas con las que se ha chateado
        ids_con_chat = mensajes_enviados.union(mensajes_recibidos).subquery()
        
        # Filtramos la lista de clientes para mostrar solo aquellos con los que hay historial de chat
        clientes = Usuario.query.filter(Usuario.id.in_(ids_con_chat)).all()
        
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

@app.route('/eliminar_chat/<int:cliente_id>', methods=['POST'])
def eliminar_chat(cliente_id):
    if 'usuario_id' not in session:
        return redirect(url_for('index'))

    usuario_actual = Usuario.query.get(session['usuario_id'])

    # Borra todos los mensajes cruzados entre el usuario actual y el cliente seleccionado
    Mensaje.query.filter(
        ((Mensaje.emisor_id == usuario_actual.id) & (Mensaje.receptor_id == cliente_id)) |
        ((Mensaje.emisor_id == cliente_id) & (Mensaje.receptor_id == usuario_actual.id))
    ).delete()
    
    db.session.commit()
    flash('El chat ha sido eliminado correctamente.', 'info')

    return redirect(url_for('centro_mensajes'))

# --- NUEVA RUTA API PARA ACTUALIZAR EL CHAT EN TIEMPO REAL ---
@app.route('/api/mensajes/<int:otro_usuario_id>')
def api_mensajes(otro_usuario_id):
    if 'usuario_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    usuario_actual_id = session['usuario_id']

    # Consultar los mensajes entre el usuario actual y el otro usuario indicado
    mensajes = Mensaje.query.filter(
        ((Mensaje.emisor_id == usuario_actual_id) & (Mensaje.receptor_id == otro_usuario_id)) |
        ((Mensaje.emisor_id == otro_usuario_id) & (Mensaje.receptor_id == usuario_actual_id))
    ).order_by(Mensaje.fecha.asc()).all()

    lista_mensajes = []
    for m in mensajes:
        lista_mensajes.append({
            'emisor_id': m.emisor_id,
            'contenido': m.contenido,
            'fecha': m.fecha.strftime('%d/%m/%Y %H:%M')
        })

    return jsonify(lista_mensajes)

# --- RUTAS DE COMENTARIOS Y EXPERIENCIAS ---

@app.route('/comentar', methods=['POST'])
def comentar():
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión para dejar una experiencia o comentario.', 'warning')
        return redirect(url_for('index'))

    usuario_actual = Usuario.query.get(session['usuario_id'])
    contenido = request.form.get('contenido', '').strip()
    foto_archivo = request.files.get('foto')
    
    ruta_foto = None

    # Procesar la imagen si el usuario subió una
    if foto_archivo and foto_archivo.filename != '':
        if archivo_permitido(foto_archivo.filename):
            filename = secure_filename(f"{datetime.utcnow().timestamp()}_{foto_archivo.filename}")
            foto_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            foto_archivo.save(foto_path)
            ruta_foto = filename # Guardamos el nombre del archivo para la BD
        else:
            flash('Formato de imagen no permitido. Usa JPG, PNG o WEBP.', 'danger')
            return redirect(url_for('index'))

    if contenido:
        nuevo_comentario = Comentario(
            usuario_id=usuario_actual.id,
            contenido=contenido,
            foto=ruta_foto
        )
        db.session.add(nuevo_comentario)
        db.session.commit()
        flash('¡Gracias por compartir tu experiencia con el tanque!', 'success')
    else:
        flash('El comentario no puede estar vacío.', 'danger')

    return redirect(url_for('index') + '#seccion-comentarios')


@app.route('/comentario/editar/<int:id>', methods=['POST'])
def editar_comentario(id):
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión.', 'danger')
        return redirect(url_for('index'))
        
    comentario = Comentario.query.get_or_404(id)
    usuario_actual = Usuario.query.get(session['usuario_id'])

    # Solo el autor del comentario puede editarlo
    if comentario.usuario_id == usuario_actual.id:
        nuevo_contenido = request.form.get('contenido', '').strip()
        if nuevo_contenido:
            comentario.contenido = nuevo_contenido
            db.session.commit()
            flash('Comentario actualizado correctamente.', 'success')
        else:
            flash('El contenido del comentario no puede estar vacío.', 'danger')
    else:
        flash('No tienes permiso para editar este comentario.', 'danger')
        
    return redirect(url_for('index') + '#seccion-comentarios')


@app.route('/comentario/eliminar/<int:id>', methods=['POST'])
def eliminar_comentario(id):
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión para realizar esta acción.', 'danger')
        return redirect(url_for('index'))
    
    comentario = Comentario.query.get_or_404(id)
    usuario_actual = Usuario.query.get(session['usuario_id'])

    # Permitir borrar si es el autor del comentario o si es el Administrador (Dueño)
    if comentario.usuario_id == usuario_actual.id or usuario_actual.rol == 'Dueno':
        # Borrar la foto física del servidor si la tiene adjunta
        if comentario.foto:
            ruta_foto = os.path.join(app.config['UPLOAD_FOLDER'], comentario.foto)
            if os.path.exists(ruta_foto):
                try:
                    os.remove(ruta_foto)
                except Exception as e:
                    print(f"Error al eliminar archivo de foto: {e}")
                
        db.session.delete(comentario)
        db.session.commit()
        flash('Comentario eliminado exitosamente.', 'success')
    else:
        flash('No tienes permisos para eliminar este comentario.', 'danger')
        
    return redirect(url_for('index') + '#seccion-comentarios')


if __name__ == '__main__':
    app.run(debug=True)
