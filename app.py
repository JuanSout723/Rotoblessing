import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clave_secreta_super_segura_rotoblessing')

# Carpeta donde se guardarán las fotos de forma segura
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def archivo_permitido(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Asegurar que la carpeta de subidas exista
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configuración de la base de datos (Compatible con PostgreSQL en Render y SQLite local)
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///rotoblessing.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MODELOS DE LA BASE DE DATOS ---

class Usuario(db.Model):
    __tablename__ = 'usuario'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(50), nullable=False, default='Comprador')

    # --- CAMPOS DE PERFIL Y CONFIANZA ---
    telefono = db.Column(db.String(30), nullable=True)
    whatsapp = db.Column(db.String(30), nullable=True)
    facebook = db.Column(db.String(150), nullable=True)
    instagram = db.Column(db.String(150), nullable=True)
    biografia = db.Column(db.Text, nullable=True)
    
    # Almacena el nombre del archivo de la foto
    foto_perfil = db.Column(db.String(200), nullable=True)

    comentarios = db.relationship('Comentario', backref='autor_ref', cascade='all, delete-orphan', passive_deletes=True)

class Comentario(db.Model):
    __tablename__ = 'comentario'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id', ondelete='CASCADE'), nullable=False)
    contenido = db.Column(db.Text, nullable=False)
    
    # Almacena el nombre del archivo de la foto del comentario
    foto = db.Column(db.String(200), nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    
    autor = db.relationship('Usuario', foreign_keys=[usuario_id])

with app.app_context():
    try:
        db.create_all()
        # Sincronizar columnas por si la base de datos ya existía
        with db.engine.connect() as connection:
            connection.execute(db.text("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS telefono VARCHAR(30);"))
            connection.execute(db.text("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS whatsapp VARCHAR(30);"))
            connection.execute(db.text("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS facebook VARCHAR(150);"))
            connection.execute(db.text("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS instagram VARCHAR(150);"))
            connection.execute(db.text("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS biografia TEXT;"))
            connection.execute(db.text("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS foto_perfil VARCHAR(200);"))
            connection.execute(db.text("ALTER TABLE comentario ADD COLUMN IF NOT EXISTS foto VARCHAR(200);"))
            connection.commit()
        print("Tablas y columnas sincronizadas correctamente.")
    except Exception as e:
        print(f"Nota al sincronizar base de datos: {e}")

# --- RUTAS DE NAVEGACIÓN Y AUTENTICACIÓN ---

@app.route('/')
def index():
    usuario_id = session.get('usuario_id')
    usuario = Usuario.query.get(usuario_id) if usuario_id else None
    comentarios = Comentario.query.order_by(Comentario.fecha.desc()).all()
    vendedores = Usuario.query.filter(Usuario.rol.in_(['Vendedor', 'Dueno'])).all()
    
    return render_template(
        'index.html', 
        usuario=usuario, 
        comentarios=comentarios, 
        vendedores=vendedores
    )

@app.route('/registro', methods=['POST'])
def registro():
    nombre = request.form.get('nombre')
    email = request.form.get('email')
    password = request.form.get('password')
    rol = request.form.get('rol')
    codigo = request.form.get('codigo_verificacion', '').strip()

    CLAVE_VENDEDOR = "VENDEDOR2026"
    CLAVE_DUENO = "ADMIN2026"

    if rol == 'Vendedor' and codigo != CLAVE_VENDEDOR:
        flash('Código de verificación incorrecto para el rol de Vendedor.', 'danger')
        return redirect(url_for('index'))

    if rol == 'Dueno' and codigo != CLAVE_DUENO:
        flash('Código de verificación incorrecto para el rol de Dueño/Administrador.', 'danger')
        return redirect(url_for('index'))

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

# --- RUTAS DE GESTIÓN DE PERFIL PROFESIONAL Y ELIMINACIÓN DE CUENTA ---

@app.route('/perfil/editar', methods=['GET', 'POST'])
def editar_perfil():
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión.', 'danger')
        return redirect(url_for('index'))
        
    usuario = Usuario.query.get(session['usuario_id'])
    if not usuario:
        flash('Usuario no encontrado.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'GET':
        return redirect(url_for('index'))
    
    usuario.telefono = request.form.get('telefono', '').strip()
    usuario.whatsapp = request.form.get('whatsapp', '').strip()
    usuario.facebook = request.form.get('facebook', '').strip()
    usuario.instagram = request.form.get('instagram', '').strip()
    usuario.biografia = request.form.get('biografia', '').strip()
    
    foto_archivo = request.files.get('foto_perfil')
    if foto_archivo and foto_archivo.filename != '':
        if archivo_permitido(foto_archivo.filename):
            filename = secure_filename(foto_archivo.filename)
            nombre_unico = f"user_{usuario.id}_{int(datetime.utcnow().timestamp())}_{filename}"
            foto_path = os.path.join(app.config['UPLOAD_FOLDER'], nombre_unico)
            foto_archivo.save(foto_path)
            usuario.foto_perfil = nombre_unico
        else:
            flash('Formato de imagen de perfil no permitido. Usa JPG, PNG o WEBP.', 'danger')
            return redirect(url_for('index'))

    db.session.commit()
    flash('¡Tu perfil profesional ha sido actualizado con éxito!', 'success')
    return redirect(url_for('index'))

@app.route('/perfil/eliminar', methods=['POST'])
def eliminar_cuenta():
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión.', 'danger')
        return redirect(url_for('index'))
        
    usuario_id = session['usuario_id']
    usuario = Usuario.query.get(usuario_id)
    
    if usuario:
        db.session.delete(usuario)
        db.session.commit()
        session.clear()
        flash('Tu cuenta ha sido eliminada permanentemente del sistema.', 'info')
        
    return redirect(url_for('index'))

@app.route('/admin/eliminar_usuario/<int:id>', methods=['POST'])
def admin_eliminar_usuario(id):
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión.', 'danger')
        return redirect(url_for('index'))
        
    usuario_actual = Usuario.query.get(session['usuario_id'])
    
    if not usuario_actual or usuario_actual.rol != 'Dueno':
        flash('No tienes permisos de Administrador/Dueño para realizar esta acción.', 'danger')
        return redirect(url_for('index'))
        
    usuario_a_eliminar = Usuario.query.get_or_404(id)
    
    if usuario_a_eliminar.id == usuario_actual.id:
        flash('No puedes eliminar tu propia cuenta desde el panel de control.', 'warning')
        return redirect(url_for('index'))

    nombre_borrado = usuario_a_eliminar.nombre
    db.session.delete(usuario_a_eliminar)
    db.session.commit()
    
    flash(f'El miembro del equipo {nombre_borrado} ha sido eliminado exitosamente.', 'success')
    return redirect(url_for('index'))

# --- RUTAS DE COMENTARIOS Y EXPERIENCIAS ---

@app.route('/comentar', methods=['POST'])
def comentar():
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión para dejar una experiencia o comentario.', 'warning')
        return redirect(url_for('index'))

    usuario_actual = Usuario.query.get(session['usuario_id'])
    contenido = request.form.get('contenido', '').strip()
    foto_archivo = request.files.get('foto')
    nombre_foto = None

    if foto_archivo and foto_archivo.filename != '':
        if archivo_permitido(foto_archivo.filename):
            filename = secure_filename(foto_archivo.filename)
            nombre_foto = f"comentario_{usuario_actual.id}_{int(datetime.utcnow().timestamp())}_{filename}"
            foto_path = os.path.join(app.config['UPLOAD_FOLDER'], nombre_foto)
            foto_archivo.save(foto_path)
        else:
            flash('Formato de imagen no permitido. Usa JPG, PNG o WEBP.', 'danger')
            return redirect(url_for('index'))

    if contenido:
        nuevo_comentario = Comentario(
            usuario_id=usuario_actual.id,
            contenido=contenido,
            foto=nombre_foto
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

    if comentario.usuario_id == usuario_actual.id or usuario_actual.rol == 'Dueno':
        db.session.delete(comentario)
        db.session.commit()
        flash('Comentario eliminado exitosamente.', 'success')
    else:
        flash('No tienes permisos para eliminar este comentario.', 'danger')
        
    return redirect(url_for('index') + '#seccion-comentarios')

if __name__ == '__main__':
    app.run(debug=True)
