from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
from config import Config
from datetime import datetime

from datetime import datetime, date
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

    return render_template("privado/personal.html")


@app.route("/panel/personal/choferes", methods=['GET'])
def panel_personal_choferes():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    id_supervisor = session['id']

    # RUTA ACTIVA
    cursor.execute("""
        SELECT id_ruta
        FROM supervisor_ruta
        WHERE id_empleado=%s AND fecha_fin IS NULL
    """, (id_supervisor,))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        return render_template("privado/personal_choferes.html",
                               choferes_existentes=[], id_ruta=None,
                               tipos_licencia=[], editar_personal=None)

    id_ruta = row['id_ruta']

    # LISTA DE CHOFERES
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

    # EDITAR
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

    # ELIMINAR
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
        return redirect(url_for("panel_personal_choferes"))

    cursor.close()

    return render_template("privado/personal_choferes.html",
                           choferes_existentes=choferes,
                           id_ruta=id_ruta,
                           tipos_licencia=tipos_licencia,
                           editar_personal=editar_personal)


# ======================= REGISTRAR CHOFER =======================

@app.route("/registrar_personal_chofer", methods=['POST'])
def registrar_personal_chofer():
    cursor = mysql.connection.cursor()

    try:
        mysql.connection.begin()

        # persona
        cursor.execute("""
            INSERT INTO persona(nombre, apellido, dni, telefono)
            VALUES (%s, %s, %s, %s)
        """, (
            request.form["nombre"],
            request.form["apellido"],
            request.form["dni"],
            request.form["telefono"]
        ))
        id_persona = cursor.lastrowid

        # empleado
        cursor.execute("""
            INSERT INTO empleado(id_persona, sueldo, fecha_ingreso)
            VALUES (%s, %s, %s)
        """, (
            id_persona,
            request.form["sueldo"],
            request.form["fecha_ingreso"]
        ))
        id_empleado = cursor.lastrowid

        # chofer
        cursor.execute("""
            INSERT INTO chofer(id_empleado, nro_licencia, años_experiencia,
                               id_tipo_licencia, historial_infracciones)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            id_empleado,
            request.form["nro_licencia"],
            request.form["anos_experiencia"],
            request.form["id_tipo_licencia"],
            request.form["historial_infracciones"]
        ))

        mysql.connection.commit()
        flash("✔ Chofer registrado correctamente.", "success")

    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error: {str(e)}", "danger")

    cursor.close()
    return redirect(url_for("panel_personal_choferes"))

## COBRADORES

@app.route("/panel/personal/cobradores", methods=['GET'])
def panel_personal_cobradores():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    id_supervisor = session['id']

    # detectar ruta activa
    cursor.execute("""
        SELECT id_ruta
        FROM supervisor_ruta
        WHERE id_empleado=%s AND fecha_fin IS NULL
    """, (id_supervisor,))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        return render_template("privado/personal_cobradores.html",
                               cobradores_existentes=[], id_ruta=None,
                               editar_personal=None,
                               lista_idiomas=[],
                               idiomas_asociados=[])

    id_ruta = row['id_ruta']

    # obtener cobradores vinculados a la ruta o libres sin asignación
    cursor.execute("""
        (
            SELECT e.id_empleado, p.nombre, p.apellido, p.dni, p.telefono, e.sueldo
            FROM empleado e
            JOIN persona p ON e.id_persona=p.id_persona
            JOIN cobrador c ON c.id_empleado=e.id_empleado
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
            SELECT e.id_empleado, p.nombre, p.apellido, p.dni, p.telefono, e.sueldo
            FROM empleado e
            JOIN persona p ON e.id_persona=p.id_persona
            JOIN cobrador c ON c.id_empleado=e.id_empleado
            WHERE e.id_empleado NOT IN (SELECT id_empleado FROM asignacion_bus)
        )
    """, (id_ruta,))
    
    cobradores = cursor.fetchall()

    # obtener idiomas disponibles
    cursor.execute("SELECT id_idioma, nombre FROM idioma")
    lista_idiomas = cursor.fetchall()

    editar_personal = None
    idiomas_asociados = []

    # editar
    if "editar" in request.args:
        cursor.execute("""
            SELECT e.id_empleado, p.nombre, p.apellido, p.dni, p.telefono,
                   e.sueldo
            FROM empleado e
            JOIN persona p ON e.id_persona=p.id_persona
            JOIN cobrador c ON c.id_empleado=e.id_empleado
            WHERE e.id_empleado=%s
        """, (request.args["editar"],))
        editar_personal = cursor.fetchone()

        cursor.execute("""
            SELECT id_idioma
            FROM cobrador_idioma
            WHERE id_empleado=%s
        """, (editar_personal["id_empleado"],))
        idiomas_asociados = [row["id_idioma"] for row in cursor.fetchall()]

    # eliminar
    if "eliminar" in request.args:
        try:
            mysql.connection.begin()
            id_empleado = request.args["eliminar"]

            cursor.execute("DELETE FROM cobrador_idioma WHERE id_empleado=%s", (id_empleado,))
            cursor.execute("DELETE FROM cobrador WHERE id_empleado=%s", (id_empleado,))
            cursor.execute("DELETE FROM empleado WHERE id_empleado=%s", (id_empleado,))

            mysql.connection.commit()
            flash("✔ Registro eliminado.", "success")

        except Exception as e:
            mysql.connection.rollback()
            flash(f"❌ Error: {str(e)}", "danger")

        cursor.close()
        return redirect(url_for("panel_personal_cobradores"))

    cursor.close()

    # agregar idiomas a cada cobrador para mostrar
    for c in cobradores:
        cursor2 = mysql.connection.cursor()
        cursor2.execute("""
            SELECT i.nombre
            FROM cobrador_idioma ci
            JOIN idioma i ON ci.id_idioma=i.id_idioma
            WHERE ci.id_empleado=%s
        """, (c["id_empleado"],))
        idiomas = [row["nombre"] for row in cursor2.fetchall()]
        c["idiomas"] = ", ".join(idiomas)
        cursor2.close()

    return render_template("privado/personal_cobradores.html",
                           cobradores_existentes=cobradores,
                           id_ruta=id_ruta,
                           editar_personal=editar_personal,
                           lista_idiomas=lista_idiomas,
                           idiomas_asociados=idiomas_asociados)


@app.route("/registrar_personal_cobrador", methods=['POST'])
def registrar_personal_cobrador():
    cursor = mysql.connection.cursor()

    try:
        mysql.connection.begin()

        # persona
        cursor.execute("""
            INSERT INTO persona(nombre, apellido, dni, telefono)
            VALUES (%s, %s, %s, %s)
        """, (
            request.form["nombre"],
            request.form["apellido"],
            request.form["dni"],
            request.form["telefono"]
        ))
        id_persona = cursor.lastrowid

        # empleado
        cursor.execute("""
            INSERT INTO empleado(id_persona, sueldo, fecha_ingreso, tipo_empleado)
            VALUES (%s, %s, %s, 'COBRADOR')
        """, (
            id_persona,
            request.form["sueldo"],
            request.form["fecha_ingreso"]
        ))
        id_empleado = cursor.lastrowid

        # cobrador
        cursor.execute("""
            INSERT INTO cobrador(id_empleado)
            VALUES (%s)
        """, (id_empleado,))

        # registrar idiomas seleccionados
        idiomas = request.form.getlist("idiomas")
        for id_idioma in idiomas:
            cursor.execute("""
                INSERT INTO cobrador_idioma(id_empleado, id_idioma)
                VALUES (%s, %s)
            """, (id_empleado, id_idioma))

        mysql.connection.commit()
        flash("✔ Cobrador registrado correctamente.", "success")

    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error: {str(e)}", "danger")

    cursor.close()
    return redirect(url_for("panel_personal_cobradores"))


@app.route("/actualizar_personal_cobrador", methods=['POST'])
def actualizar_personal_cobrador():
    cursor = mysql.connection.cursor()

    try:
        mysql.connection.begin()

        id_empleado = request.form["id_empleado"]

        # actualizar persona
        cursor.execute("""
            UPDATE persona p
            JOIN empleado e ON p.id_persona=e.id_persona
            SET p.nombre=%s, p.apellido=%s, p.dni=%s, p.telefono=%s
            WHERE e.id_empleado=%s
        """, (
            request.form["nombre"],
            request.form["apellido"],
            request.form["dni"],
            request.form["telefono"],
            id_empleado
        ))

        # actualizar empleado sueldo
        cursor.execute("""
            UPDATE empleado
            SET sueldo=%s
            WHERE id_empleado=%s
        """, (request.form["sueldo"], id_empleado))

        # actualizar idiomas
        cursor.execute("DELETE FROM cobrador_idioma WHERE id_empleado=%s", (id_empleado,))
        idiomas = request.form.getlist("idiomas")
        for id_idioma in idiomas:
            cursor.execute("""
                INSERT INTO cobrador_idioma(id_empleado, id_idioma)
                VALUES (%s, %s)
            """, (id_empleado, id_idioma))

        mysql.connection.commit()
        flash("✔ Datos de cobrador actualizados.", "success")

    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error: {str(e)}", "danger")

    cursor.close()
    return redirect(url_for("panel_personal_cobradores"))


# =============================================
# PANEL GENERAL DE INCIDENCIAS
# =============================================
@app.route("/panel/incidencias", methods=['GET'])
def panel_incidencias():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template("privado/incidencias.html")


# =============================================
# INCIDENCIAS DISCIPLINARIAS
# =============================================
@app.route("/panel/incidencias/disciplinarias", methods=['GET'])
def panel_incidencias_disciplinarias():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    id_supervisor = session['id']

    # Detectar ruta activa del supervisor
    cursor.execute("""
        SELECT id_ruta
        FROM supervisor_ruta
        WHERE id_empleado=%s AND fecha_fin IS NULL
    """, (id_supervisor,))
    row = cursor.fetchone()
    id_ruta = row['id_ruta'] if row else None

    # Obtener incidencias disciplinarias
    if id_ruta:
        cursor.execute("""
            SELECT i.id_incidencia, i.fecha, i.descripcion, i.estado,
                   id.tipo_disciplinaria, id.sancion
            FROM incidencia i
            JOIN incidencia_disciplinaria id ON i.id_incidencia=id.id_incidencia
            ORDER BY i.fecha DESC
        """)
    else:
        cursor.execute("""
            SELECT i.id_incidencia, i.fecha, i.descripcion, i.estado,
                   id.tipo_disciplinaria, id.sancion
            FROM incidencia i
            JOIN incidencia_disciplinaria id ON i.id_incidencia=id.id_incidencia
            ORDER BY i.fecha DESC
        """)
    incidencias = cursor.fetchall()
    cursor.close()

    # Pasar fecha actual para limitar input en HTML
    return render_template("privado/incidencias_disciplinarias.html",
                           incidencias=incidencias,
                           id_ruta=id_ruta,
                           hoy=date.today().isoformat())


# Crear nueva incidencia disciplinaria
@app.route("/registrar_incidencia_disciplinaria", methods=['POST'])
def registrar_incidencia_disciplinaria():
    cursor = mysql.connection.cursor()
    try:
        # VALIDAR FECHA CON datetime.strptime
        try:
            fecha_obj = datetime.strptime(request.form["fecha"], "%Y-%m-%d").date()
        except ValueError:
            flash("❌ Fecha inválida. Usa formato YYYY-MM-DD.", "danger")
            return redirect(url_for("panel_incidencias_disciplinarias"))

        # VALIDAR RANGO DE FECHA
        if fecha_obj < date(2000, 1, 1) or fecha_obj > date.today():
            flash("❌ Fecha fuera del rango permitido (2000 hasta hoy).", "danger")
            return redirect(url_for("panel_incidencias_disciplinarias"))

        mysql.connection.begin()

        cursor.execute("""
            INSERT INTO incidencia(fecha, descripcion, estado)
            VALUES (%s, %s, %s)
        """, (
            fecha_obj,
            request.form["descripcion"],
            request.form["estado"]
        ))
        id_incidencia = cursor.lastrowid

        cursor.execute("""
            INSERT INTO incidencia_disciplinaria(id_incidencia, tipo_disciplinaria, sancion)
            VALUES (%s, %s, %s)
        """, (
            id_incidencia,
            request.form["tipo_disciplinaria"],
            request.form["sancion"]
        ))

        mysql.connection.commit()
        flash("✔ Incidencia disciplinaria registrada.", "success")
    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error: {str(e)}", "danger")
    finally:
        cursor.close()

    return redirect(url_for("panel_incidencias_disciplinarias"))


# Eliminar incidencia disciplinaria
@app.route("/eliminar_incidencia_disciplinaria/<int:id_incidencia>", methods=['GET'])
def eliminar_incidencia_disciplinaria(id_incidencia):
    cursor = mysql.connection.cursor()
    try:
        mysql.connection.begin()
        cursor.execute("DELETE FROM incidencia_disciplinaria WHERE id_incidencia=%s", (id_incidencia,))
        cursor.execute("DELETE FROM incidencia WHERE id_incidencia=%s", (id_incidencia,))
        mysql.connection.commit()
        flash("✔ Incidencia disciplinaria eliminada.", "success")
    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error: {str(e)}", "danger")
    finally:
        cursor.close()

    return redirect(url_for("panel_incidencias_disciplinarias"))

# =============================================
# INCIDENCIAS OPERATIVAS
# =============================================
@app.route("/panel/incidencias/operativas", methods=['GET'])
def panel_incidencias_operativas():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    id_supervisor = session['id']

    # Detectar ruta activa del supervisor
    cursor.execute("""
        SELECT id_ruta
        FROM supervisor_ruta
        WHERE id_empleado=%s AND fecha_fin IS NULL
    """, (id_supervisor,))
    row = cursor.fetchone()
    id_ruta = row['id_ruta'] if row else None

    # Obtener incidencias operativas
    if id_ruta:
        cursor.execute("""
            SELECT i.id_incidencia, i.fecha, i.descripcion, i.estado,
                   io.gravedad, io.costo, io.requiere_seguro
            FROM incidencia i
            JOIN incidencia_operativa io ON i.id_incidencia=io.id_incidencia
            -- Se pueden filtrar por buses asignados a la ruta si aplica
            ORDER BY i.fecha DESC
        """)
    else:
        cursor.execute("""
            SELECT i.id_incidencia, i.fecha, i.descripcion, i.estado,
                   io.gravedad, io.costo, io.requiere_seguro
            FROM incidencia i
            JOIN incidencia_operativa io ON i.id_incidencia=io.id_incidencia
            ORDER BY i.fecha DESC
        """)
    incidencias = cursor.fetchall()
    cursor.close()

    return render_template("privado/incidencias_operativas.html",
                           incidencias=incidencias,
                           id_ruta=id_ruta)

# Crear nueva incidencia operativa
@app.route("/registrar_incidencia_operativa", methods=['POST'])
def registrar_incidencia_operativa():
    cursor = mysql.connection.cursor()
    try:
        mysql.connection.begin()

        cursor.execute("""
            INSERT INTO incidencia(fecha, descripcion, estado)
            VALUES (%s, %s, %s)
        """, (
            request.form["fecha"],
            request.form["descripcion"],
            request.form["estado"]
        ))
        id_incidencia = cursor.lastrowid

        cursor.execute("""
            INSERT INTO incidencia_operativa(id_incidencia, gravedad, costo, requiere_seguro)
            VALUES (%s, %s, %s, %s)
        """, (
            id_incidencia,
            request.form["gravedad"],
            request.form["costo"],
            1 if request.form.get("requiere_seguro") else 0
        ))

        mysql.connection.commit()
        flash("✔ Incidencia operativa registrada.", "success")
    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error: {str(e)}", "danger")
    cursor.close()
    return redirect(url_for("panel_incidencias_operativas"))

# Eliminar incidencia operativa
@app.route("/eliminar_incidencia_operativa/<int:id_incidencia>", methods=['GET'])
def eliminar_incidencia_operativa(id_incidencia):
    cursor = mysql.connection.cursor()
    try:
        mysql.connection.begin()
        cursor.execute("DELETE FROM incidencia_operativa WHERE id_incidencia=%s", (id_incidencia,))
        cursor.execute("DELETE FROM incidencia WHERE id_incidencia=%s", (id_incidencia,))
        mysql.connection.commit()
        flash("✔ Incidencia operativa eliminada.", "success")
    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error: {str(e)}", "danger")
    cursor.close()
    return redirect(url_for("panel_incidencias_operativas"))




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
