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
    
    # 0. OBTENER ROL DEL SUPERVISOR (NUEVO: Necesario para controlar permisos)
    cursor.execute("SELECT tipo_supervisor FROM supervisor WHERE id_empleado = %s", (id_supervisor_logueado,))
    rol_data = cursor.fetchone()
    rol_supervisor = rol_data['tipo_supervisor'] if rol_data else None
    
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
        revision = request.form.get("ultima_revision") # Campo usado en la edición (solo visible para General)
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
                    # Query base: Siempre actualiza Placa, Año y Modelo
                    update_query = """
                        UPDATE bus 
                        SET placa = %s, 
                            año_fabricacion = %s, 
                            id_modelo_bus = %s
                    """
                    update_params = [placa, anio, id_modelo_bus]

                    # CONDICIONAL: Solo actualiza ultima_revision si el supervisor es 'General'
                    if rol_supervisor == 'General':
                        update_query += ", ultima_revision = %s"
                        update_params.append(revision)
                    
                    # Finalizar query
                    update_query += " WHERE id_bus = %s"
                    update_params.append(id_bus_editado)
                    
                    cursor.execute(update_query, update_params)
                    
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
        
        # Consulta de modelos: Devolvemos el nombre del modelo y su marca 
        cursor.execute("""
            SELECT 
                mb.id_modelo_bus AS id, 
                mb.nombre AS modelo_nombre,
                ma.nombre AS marca_nombre
            FROM modelo_bus mb
            JOIN marca_bus ma ON mb.id_marca_bus = ma.id_marca_bus
            ORDER BY ma.nombre, mb.nombre
        """)
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
    # Se pasa el rol para control de permisos en el HTML
    return render_template("privado/buses.html", 
                           buses=buses, 
                           modelos=modelos, 
                           bus_a_editar=bus_a_editar,
                           rol_supervisor=rol_supervisor) # <--- ¡IMPORTANTE!


@app.route("/panel/buses/eliminar/<int:id_bus>")
def panel_buses_eliminar(id_bus):
    if 'usuario' not in session:
        return redirect(url_for('login'))
    
    # ... (el resto de la función es idéntico a tu versión y funciona correctamente)
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



# app.py (Secciones de código a reemplazar o añadir)

# app.py (Reemplaza las siguientes funciones en tu archivo existente)

# ==============================================================================
# PANEL DE GESTIÓN (Ruta Principal: Choferes Filtrados + Choferes Disponibles)
# ==============================================================================

@app.route("/panel/personal", methods=['GET'])
def panel_personal():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    id_supervisor = session['id']

    # ========== Ruta del supervisor ==========
    cursor.execute("""
        SELECT id_ruta
        FROM supervisor_ruta
        WHERE id_empleado=%s AND fecha_fin IS NULL
    """, (id_supervisor,))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        return render_template("privado/personal.html",
                               choferes_existentes=[], id_ruta=None,
                               tipos_licencia=[], editar_personal=None)

    id_ruta = row['id_ruta']

    # ========== Choferes visibles ==========
    cursor.execute("""
        (
            SELECT e.id_empleado, p.nombre, p.apellido, p.dni,
                   ch.nro_licencia, tl.categoria, ch.años_experiencia
            FROM empleado e
            JOIN persona p ON e.id_persona=p.id_persona
            JOIN chofer ch ON e.id_empleado=ch.id_empleado
            JOIN tipo_licencia tl ON tl.id_tipo_licencia=ch.id_tipo_licencia
            WHERE e.id_empleado IN (
                SELECT DISTINCT ab.id_empleado
                FROM asignacion_bus ab
                JOIN bus b ON ab.id_bus=b.id_bus
                JOIN bus_ruta br ON b.id_bus=br.id_bus
                WHERE br.id_ruta=%s
            )
        )
        UNION
        (
            SELECT e.id_empleado, p.nombre, p.apellido, p.dni,
                   ch.nro_licencia, tl.categoria, ch.años_experiencia
            FROM empleado e
            JOIN persona p ON e.id_persona=p.id_persona
            JOIN chofer ch ON e.id_empleado=ch.id_empleado
            JOIN tipo_licencia tl ON tl.id_tipo_licencia=ch.id_tipo_licencia
            WHERE e.id_empleado NOT IN (SELECT id_empleado FROM asignacion_bus)
        )
    """, (id_ruta,))

    choferes = cursor.fetchall()

    cursor.execute("SELECT * FROM tipo_licencia ORDER BY categoria")
    tipos_licencia = cursor.fetchall()

    editar_personal = None

    # ====== Si el request pide editar ==========
    if "editar" in request.args:
        cursor.execute("""
            SELECT e.id_empleado, p.nombre, p.apellido, p.dni, p.telefono,
                   e.sueldo,
                   ch.nro_licencia, ch.años_experiencia, ch.id_tipo_licencia,
                   ch.historial_infracciones
            FROM empleado e
            JOIN persona p ON e.id_persona=p.id_persona
            JOIN chofer ch ON ch.id_empleado=e.id_empleado
            WHERE e.id_empleado=%s
        """, (request.args["editar"],))
        editar_personal = cursor.fetchone()

    # ====== Si el request pide eliminar ==========
    if "eliminar" in request.args:
        try:
            mysql.connection.begin()

            id_empleado = request.args["eliminar"]

            cursor.execute("DELETE FROM chofer WHERE id_empleado=%s", (id_empleado,))
            cursor.execute("DELETE FROM empleado WHERE id_empleado=%s", (id_empleado,))

            mysql.connection.commit()
            flash("✔ Registro eliminado.", "success")

        except Exception as e:
            mysql.connection.rollback()
            flash(f"❌ Error: {str(e)}", "danger")

        cursor.close()
        return redirect(url_for("panel_personal"))

    cursor.close()

    return render_template("privado/personal.html",
                           choferes_existentes=choferes,
                           id_ruta=id_ruta,
                           tipos_licencia=tipos_licencia,
                           editar_personal=editar_personal)


@app.route("/actualizar_personal", methods=['POST'])
def actualizar_personal():

    cursor = mysql.connection.cursor()
    id_empleado = request.form["id_empleado"]

    try:
        mysql.connection.begin()

        # persona
        cursor.execute("""
            UPDATE persona p
            JOIN empleado e ON e.id_persona=p.id_persona
            SET p.nombre=%s, p.apellido=%s, p.dni=%s, p.telefono=%s
            WHERE e.id_empleado=%s
        """, (
            request.form["nombre"],
            request.form["apellido"],
            request.form["dni"],
            request.form["telefono"],
            id_empleado
        ))

        # empleado
        cursor.execute("""
            UPDATE empleado
            SET sueldo=%s
            WHERE id_empleado=%s
        """, (request.form["sueldo"], id_empleado))

        # chofer
        cursor.execute("""
            UPDATE chofer
            SET nro_licencia=%s, años_experiencia=%s,
                id_tipo_licencia=%s, historial_infracciones=%s
            WHERE id_empleado=%s
        """, (
            request.form["nro_licencia"],
            request.form["anos_experiencia"],
            request.form["id_tipo_licencia"],
            request.form["historial_infracciones"],
            id_empleado
        ))

        mysql.connection.commit()
        flash("✔ Datos actualizados.", "success")

    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error: {str(e)}", "danger")

    cursor.close()
    return redirect(url_for("panel_personal"))





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
