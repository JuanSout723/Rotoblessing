import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import urllib.parse
import requests

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clave_secreta_super_segura_rotoblessing')

# Carpeta donde se guardarán las fotos de los comentarios de forma segura
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

# --- VARIABLES Y SISTEMA DE OBTENCIÓN DE TASA BCV AUTOMÁTICA ---
_tasa_cache = 0.0
_ultima_actualizacion_tasa = datetime.min

def obtener_tasa_bcv_en_linea():
    """
    Obtiene la tasa oficial del dólar BCV consultando varias APIs de respaldo.
    Usa caché por 2 horas para optimizar el rendimiento del servidor en Render.
    """
    global _tasa_cache, _ultima_actualizacion_tasa
    
    # Si ya tenemos una tasa válida obtenida hace menos de 2 horas, la reutilizamos
    if _tasa_cache > 0 and (datetime.utcnow() - _ultima_actualizacion_tasa < timedelta(hours=2)):
        return _tasa_cache

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    # Lista de fuentes públicas en orden de prioridad
    fuentes_api = [
        # Fuente 1: DolarApi Venezuela (Muy rápida y estable)
        ("https://ve.dolarapi.com/v1/dolares/oficial", lambda d: float(d.get("promedio", 0))),
        # Fuente 2: PyDolarVenezuela
        ("https://pydolarvenezuela-api.vercel.app/api/v1/dollar/bcv", lambda d: float(d.get("monitors", {}).get("usd", {}).get("price", 0))),
        # Fuente 3: Rates DolarVzla
        ("https://rates.dolarvzla.com/bcv/current.json", lambda d: float(d.get("current", {}).get("usd", 0)))
    ]

    for url, funcion_parseo in fuentes_api:
        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                tasa_detectada = funcion_parseo(response.json())
                if tasa_detectada > 0:
                    _tasa_cache = round(tasa_detectada, 2)
                    _ultima_actualizacion_tasa = datetime.utcnow()
                    print(f"Tasa BCV actualizada desde {url}: {_tasa_cache} Bs.")
                    return _tasa_cache
        except Exception as e:
            print(f"Intento fallido en {url}: {e}")

    # Si todas las APIs fallan pero teníamos un valor previo en memoria, lo usamos
    if _tasa_cache > 0:
        return _tasa_cache

    return 36.00  # Valor de respaldo predeterminado si todo falla

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
    
    # Obtener la tasa oficial del BCV actualizada automáticamente
    tasa_bcv = obtener_tasa_bcv_en_linea()

    # Catálogo de productos con sus precios base en dólares
    productos = [
        {
            "nombre": "Tanque Cónico 1100 litros", 
            "precio_usd": 105.0, 
            "imagen": "tanque1100.jpeg", 
            "desc": "Ideal para espacios reducidos, hogares pequeños y negocios. Protección UV integrada."
        },
        {
            "nombre": "Tanque Cónico 900 Litros", 
            "precio_usd": 90.0, 
            "imagen": "tanque900.jpeg", 
            "desc": "El estándar más buscado por las familias para garantizar reserva óptima de agua potable."
        },
        {
            "nombre": "Tanque Cilindro 1050 Litros", 
            "precio_usd": 105.0, 
            "imagen": "tanque1050.jpeg", 
            "desc": "Mayor capacidad estructural con capa antibacteriana interna. Máxima seguridad y calidad."
        },
        {
            "nombre": "Tanque Cilindro 540 Litros", 
            "precio_usd": 90.0, 
            "imagen": "tanque540.jpeg", 
            "desc": "Ideal para espacios reducidos, hogares pequeños y negocios. Protección UV integrada."
        }
    ]
    
    return render_template(
        'index.html', 
        usuario=usuario, 
        comentarios=comentarios, 
        vendedores=vendedores,
        tasa_bcv=tasa_bcv,
        productos=productos
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

# --- CONSULTAR A UN ASESOR ESPECÍFICO ---

@app.route('/consultar/<int:vendedor_id>', methods=['POST'])
def consultar_a(vendedor_id):
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión para realizar una consulta.', 'warning')
        return redirect(url_for('index'))

    vendedor = Usuario.query.get_or_404(vendedor_id)
    
    if vendedor.rol not in ['Vendedor', 'Dueno']:
        flash('El usuario seleccionado no es un asesor válido.', 'danger')
        return redirect(url_for('index'))

    if not vendedor.whatsapp:
        flash(f'Lo sentimos, el asesor {vendedor.nombre} aún no ha configurado su número de WhatsApp.', 'warning')
        return redirect(url_for('index'))

    mensaje_usuario = request.form.get('mensaje', '').strip()
    usuario_actual = Usuario.query.get(session['usuario_id'])

    if not mensaje_usuario:
        mensaje_usuario = f"Hola {vendedor.nombre}, soy {usuario_actual.nombre}. Me gustaría consultar sobre sus productos y disponibilidad."
    else:
        mensaje_usuario = f"Hola {vendedor.nombre}, soy {usuario_actual.nombre}. Consulta: {mensaje_usuario}"

    whatsapp_num = ''.join(filter(str.isdigit, vendedor.whatsapp))
    mensaje_codificado = urllib.parse.quote(mensaje_usuario)
    link_whatsapp = f"https://wa.me/{whatsapp_num}?text={mensaje_codificado}"

    return redirect(link_whatsapp)

# --- GESTIÓN DE PERFIL Y ELIMINACIÓN DE CUENTA ---

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
        
    usuario_a_modificar = Usuario.query.get_or_404(id)
    
    if usuario_a_modificar.id == usuario_actual.id:
        flash('No puedes modificar tu propia cuenta desde el panel de control.', 'warning')
        return redirect(url_for('index'))

    nombre_usuario = usuario_a_modificar.nombre
    
    usuario_a_modificar.rol = 'Comprador'
    usuario_a_modificar.telefono = None
    usuario_a_modificar.whatsapp = None
    usuario_a_modificar.facebook = None
    usuario_a_modificar.instagram = None
    usuario_a_modificar.biografia = None

    db.session.commit()
    
    flash(f'El usuario {nombre_usuario} ha sido retirado del equipo de asesores exitosamente.', 'success')
    return redirect(url_for('index'))

# --- COMENTARIOS Y EXPERIENCIAS ---

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

# --- RUTA PARA DESCARGAR EL APK DE FORMA SEGURA ---
@app.route('/static/rotoblessing.apk')
def descargar_apk():
    return send_from_directory('static', 'rotoblessing.apk', as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
