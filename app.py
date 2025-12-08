from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
from config import Config
from datetime import datetime


# -----------------------------------------
# CONFIG GENERAL
# -----------------------------------------
app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = "STEELMAN_SUPER_KEY_2025"
mysql = MySQL(app)


# =====================================================
# CONTEXT PROCESSOR (Año dinámico)
# =====================================================
@app.context_processor
def inject_current_year():
    return {'current_year': datetime.now().year}


# =====================================================
# PÁGINAS PÚBLICAS
# =====================================================
@app.route('/')
def index():
    return render_template('publico/index.html')


@app.route('/rutas')
def rutas():
    return render_template('publico/rutas.html')


@app.route("/ruta/<string:codigo>")
def detalle_ruta(codigo):
    return render_template("publico/ruta_detalle.html", codigo=codigo)


@app.route('/contacto', methods=['GET','POST'])
def contacto():
    if request.method == 'POST':
        return render_template('publico/contacto.html',
                               enviado=True,
                               nombre=request.form.get('nombre'))
    return render_template('publico/contacto.html')


# =====================================================
# LOGIN / AUTH (Restaurado)
# =====================================================
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        clave = request.form.get('password')

        cursor = mysql.connection.cursor()
        cursor.execute("""
            SELECT id_empleado, tipo_supervisor, usuario
            FROM supervisor
            WHERE usuario=%s AND contraseña=%s
        """, (usuario, clave))

        cuenta = cursor.fetchone() 
        cursor.close()

        print("DEBUG consulta:", cuenta)

        if cuenta:
            session['id'] = cuenta['id_empleado'] 
            session['rol'] = cuenta['tipo_supervisor']
            session['usuario'] = cuenta['usuario']

            flash("✅ Bienvenido al sistema", "success")
            return redirect(url_for('panel'))

        flash("❌ Usuario o contraseña incorrectos", "danger")

    return render_template('autenticacion/login.html')


# =====================================================
# PANEL PRIVADO - DASHBOARD (Restaurado)
# =====================================================
@app.route('/panel')
def panel():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    return render_template(
        'privado/dashboard.html',
        nombre_supervisor=session['usuario'],
        tipo_supervisor=session['rol'],
        kpi_buses=5,
        kpi_incidencias=1,
        kpi_recaudacion="S/. 1500"
    )


# =====================================================
# MODULOS DEL SIDEBAR (SINGLE-PAGE CRUD)
# =====================================================

@app.route("/panel/buses", methods=["GET", "POST"])
def panel_buses():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    
    id_supervisor_logueado = session['id']
    cursor = mysql.connection.cursor()
    
    # Inicializar variables que se pasarán a la plantilla
    buses = []
    modelos = []
    id_ruta_asignada = None
    bus_a_editar = None # Contendrá los datos del bus si se activa el modo de edición

    # 1. OBTENER LA ID DE LA RUTA ASIGNADA AL SUPERVISOR
    cursor.execute("""
        SELECT sr.id_ruta 
        FROM supervisor_ruta sr
        WHERE sr.id_empleado = %s AND sr.fecha_fin IS NULL
    """, (id_supervisor_logueado,))
    
    resultado_ruta = cursor.fetchone() 
    
    if not resultado_ruta:
        flash("🚫 No tienes rutas activas asignadas. No se muestran buses ni se permite el registro/edición.", "warning")
    else:
        id_ruta_asignada = resultado_ruta['id_ruta']

    # --- 2. MANEJO DE POST (INSERTAR O ACTUALIZAR) ---
    if request.method == "POST":
        placa = request.form.get("placa")
        id_modelo_bus = request.form.get("id_modelo_bus")
        anio = request.form.get("anio") 
        revision = request.form.get("ultima_revision") # Campo usado en la edición
        id_bus_editado = request.form.get("id_bus_editado") # ID oculto si es una edición

        if id_bus_editado:
            # LÓGICA DE ACTUALIZACIÓN (UPDATE)
            
            # **1. Re-validación de propiedad (CRÍTICO)**
            cursor.execute("""
                SELECT b.id_bus
                FROM bus b
                JOIN bus_ruta br ON b.id_bus = br.id_bus
                JOIN supervisor_ruta sr ON br.id_ruta = sr.id_ruta
                WHERE b.id_bus = %s 
                  AND sr.id_empleado = %s 
                  AND sr.fecha_fin IS NULL 
                  AND br.fecha_desasignacion IS NULL
            """, (id_bus_editado, id_supervisor_logueado))
            
            if not cursor.fetchone():
                flash("❌ Error de seguridad: Intento de editar un bus no asignado a tu ruta.", "danger")
            else:
                try:
                    cursor.execute("""
                        UPDATE bus 
                        SET placa = %s, 
                            año_fabricacion = %s, 
                            id_modelo_bus = %s,
                            ultima_revision = %s
                        WHERE id_bus = %s
                    """, (placa, anio, id_modelo_bus, revision, id_bus_editado))
                    mysql.connection.commit()
                    flash("✔️ Bus editado correctamente.", "success")
                except Exception as e:
                    mysql.connection.rollback()
                    flash(f"❌ Error al editar el bus: {str(e)}", "danger")

        else:
            # LÓGICA DE INSERCIÓN (INSERT)
            if not id_ruta_asignada:
                flash("❌ No se puede registrar un bus sin tener una ruta asignada", "danger")
            else:
                cursor.execute("SELECT placa FROM bus WHERE placa=%s", (placa,))
                existe = cursor.fetchone()
                
                if existe:
                    flash("❌ Esa placa ya está registrada", "danger")
                else:
                    try:
                        # 3a. Insertar el nuevo bus
                        cursor.execute("""
                            INSERT INTO bus (placa, año_fabricacion, id_modelo_bus, id_almacen)
                            VALUES (%s, %s, %s, 1)
                        """, (placa, anio, id_modelo_bus))
                        
                        # 3b. Asignar el nuevo bus a la ruta del supervisor
                        cursor.execute("""
                            INSERT INTO bus_ruta (id_bus, id_ruta, fecha_asignacion)
                            VALUES (LAST_INSERT_ID(), %s, CURDATE())
                        """, (id_ruta_asignada,)) 
                        
                        mysql.connection.commit()
                        flash("✔️ Bus registrado y asignado a tu ruta correctamente", "success")
                    except Exception as e:
                        mysql.connection.rollback()
                        flash(f"❌ Error al registrar el bus: {str(e)}", "danger")

    # --- 3. MANEJO DE GET (MOSTRAR DATOS Y FORMULARIOS) ---
    if id_ruta_asignada:
        # Consulta de modelos (siempre se necesita)
        cursor.execute("SELECT id_modelo_bus AS id, nombre FROM modelo_bus")
        modelos = cursor.fetchall()

        # Consulta de buses
        cursor.execute("""
            SELECT 
                b.id_bus, 
                b.placa,
                m.nombre AS modelo,
                ma.nombre AS marca,
                b.año_fabricacion AS año,
                b.ultima_revision AS revision
            FROM bus b
            JOIN modelo_bus m ON b.id_modelo_bus = m.id_modelo_bus
            JOIN marca_bus ma ON m.id_marca_bus = ma.id_marca_bus
            JOIN bus_ruta br ON b.id_bus = br.id_bus   
            WHERE br.id_ruta = %s                    
              AND br.fecha_desasignacion IS NULL     
        """, (id_ruta_asignada,))
        buses = cursor.fetchall()
        
        # Modo de Edición: Si hay un ID en el URL (ej: /panel/buses?id_editar=5)
        id_bus_editar = request.args.get('id_editar', type=int)

        if id_bus_editar:
            # **Re-validación de propiedad (CRÍTICO)**
            cursor.execute("""
                SELECT b.id_bus, b.placa, b.año_fabricacion, b.id_modelo_bus, b.ultima_revision
                FROM bus b
                JOIN bus_ruta br ON b.id_bus = br.id_bus
                JOIN supervisor_ruta sr ON br.id_ruta = sr.id_ruta
                WHERE b.id_bus = %s 
                  AND sr.id_empleado = %s 
                  AND sr.fecha_fin IS NULL 
                  AND br.fecha_desasignacion IS NULL
            """, (id_bus_editar, id_supervisor_logueado))
            
            bus_a_editar_data = cursor.fetchone()
            
            if bus_a_editar_data:
                # Si el bus es válido y es de su ruta, lo pasamos al template
                bus_a_editar = bus_a_editar_data
            else:
                 flash("❌ El bus solicitado no existe o no está en tu ruta activa.", "danger")


    cursor.close()

    # 'bus_a_editar' se usa para activar el modal de edición en el template
    return render_template("privado/buses.html", buses=buses, modelos=modelos, bus_a_editar=bus_a_editar)


@app.route("/panel/buses/eliminar/<int:id_bus>")
def panel_buses_eliminar(id_bus):
    if 'usuario' not in session:
        return redirect(url_for('login'))
    
    id_supervisor_logueado = session['id']
    cursor = mysql.connection.cursor()

    # 1. VERIFICACIÓN DE RUTA (Seguridad)
    cursor.execute("""
        SELECT b.id_bus
        FROM bus b
        JOIN bus_ruta br ON b.id_bus = br.id_bus
        JOIN supervisor_ruta sr ON br.id_ruta = sr.id_ruta
        WHERE b.id_bus = %s 
          AND sr.id_empleado = %s 
          AND sr.fecha_fin IS NULL 
          AND br.fecha_desasignacion IS NULL
    """, (id_bus, id_supervisor_logueado))
    
    bus_valido = cursor.fetchone()

    if not bus_valido:
        flash("❌ Acceso denegado. El bus no está asignado a tu ruta activa.", "danger")
    else:
        try:
            # Eliminación Lógica: Desasignación de la ruta del supervisor
            cursor.execute("""
                UPDATE bus_ruta
                SET fecha_desasignacion = CURDATE()
                WHERE id_bus = %s AND fecha_desasignacion IS NULL
            """, (id_bus,))
            
            mysql.connection.commit()
            flash("✔️ Bus desasignado de tu ruta correctamente.", "success")
        except Exception as e:
            mysql.connection.rollback()
            flash(f"❌ Error al intentar desasignar el bus. {str(e)}", "danger")

    cursor.close()
    return redirect(url_for('panel_buses'))

@app.route("/panel/personal")
def panel_personal():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template("privado/personal.html")


@app.route("/panel/rutas")
def panel_rutas():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template("privado/rutas.html")


@app.route("/panel/caja")
def panel_caja():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template("privado/caja.html")


@app.route("/panel/incidencias")
def panel_incidencias():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template("privado/incidencias.html")


@app.route("/panel/reportes")
def panel_reportes():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template("privado/reportes.html")


# =====================================================
# LOGOUT
# =====================================================
@app.route('/logout')
def logout():
    session.clear()
    flash("Sesión cerrada correctamente", "info")
    return redirect(url_for('login'))


# =====================================================
# EJECUCIÓN DEL SERVIDOR
# =====================================================
if __name__ == '__main__':
    app.run(debug=True)
