from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
from config import Config
import MySQLdb.cursors
from datetime import datetime, date
#=====================================================
# CONFIG GENERAL
#=====================================================
app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = "STEELMAN_SUPER_KEY_2025"
mysql = MySQL(app)


#=====================================================
# CONTEXT PROCESSOR (Año dinámico)
#=====================================================
@app.context_processor
def inject_current_year():
    return {'current_year': datetime.now().year}


#=====================================================
# PÁGINAS PÚBLICAS
#=====================================================
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


#=====================================================
# LOGIN / AUTENTICACIÓN 
#=====================================================
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







#=====================================================
# PANEL PRIVADO - DASHBOARD 
#=====================================================
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

#=====================================================
# MODULOS DE BUSES
#=====================================================

@app.route("/panel/buses", methods=["GET", "POST"])
def panel_buses():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    
    id_supervisor_logueado = session['id']
    cursor = mysql.connection.cursor()
    

    cursor.execute("SELECT tipo_supervisor FROM supervisor WHERE id_empleado = %s", (id_supervisor_logueado,))
    rol_data = cursor.fetchone()
    rol_supervisor = rol_data['tipo_supervisor'] if rol_data else None
    

    buses = []
    modelos = []
    id_ruta_asignada = None
    bus_a_editar = None 


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


    if request.method == "POST":
        placa = request.form.get("placa")
        id_modelo_bus = request.form.get("id_modelo_bus")
        anio = request.form.get("anio") 
        revision = request.form.get("ultima_revision") 
        id_bus_editado = request.form.get("id_bus_editado") 

        if id_bus_editado:
            
            
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
                    
                    update_query = """
                        UPDATE bus 
                        SET placa = %s, 
                            año_fabricacion = %s, 
                            id_modelo_bus = %s
                    """
                    update_params = [placa, anio, id_modelo_bus]

                   
                    if rol_supervisor == 'General':
                        update_query += ", ultima_revision = %s"
                        update_params.append(revision)
                    
            
                    update_query += " WHERE id_bus = %s"
                    update_params.append(id_bus_editado)
                    
                    cursor.execute(update_query, update_params)
                    
                    mysql.connection.commit()
                    flash("✔️ Bus editado correctamente.", "success")
                except Exception as e:
                    mysql.connection.rollback()
                    flash(f"❌ Error al editar el bus: {str(e)}", "danger")

        else:
        
            if not id_ruta_asignada:
                flash("❌ No se puede registrar un bus sin tener una ruta asignada", "danger")
            else:
                cursor.execute("SELECT placa FROM bus WHERE placa=%s", (placa,))
                existe = cursor.fetchone()
                
                if existe:
                    flash("❌ Esa placa ya está registrada", "danger")
                else:
                    try:
                        
                        cursor.execute("""
                            INSERT INTO bus (placa, año_fabricacion, id_modelo_bus, id_almacen)
                            VALUES (%s, %s, %s, 1)
                        """, (placa, anio, id_modelo_bus))
                        
                       
                        cursor.execute("""
                            INSERT INTO bus_ruta (id_bus, id_ruta, fecha_asignacion)
                            VALUES (LAST_INSERT_ID(), %s, CURDATE())
                        """, (id_ruta_asignada,)) 
                        
                        mysql.connection.commit()
                        flash("✔️ Bus registrado y asignado a tu ruta correctamente", "success")
                    except Exception as e:
                        mysql.connection.rollback()
                        flash(f"❌ Error al registrar el bus: {str(e)}", "danger")

    if id_ruta_asignada:
        
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
        

        id_bus_editar = request.args.get('id_editar', type=int)

        if id_bus_editar:
   
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
              
                bus_a_editar = bus_a_editar_data
            else:
                 flash("❌ El bus solicitado no existe o no está en tu ruta activa.", "danger")


    cursor.close()

 
    return render_template("privado/buses.html", 
                           buses=buses, 
                           modelos=modelos, 
                           bus_a_editar=bus_a_editar,
                           rol_supervisor=rol_supervisor)


###############################################
############# ELIMINAR BOTON BUSES#############
###############################################

@app.route("/panel/buses/eliminar/<int:id_bus>")
def panel_buses_eliminar(id_bus):
    if 'usuario' not in session:
        return redirect(url_for('login'))
    

    id_supervisor_logueado = session['id']
    cursor = mysql.connection.cursor()

   
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




#==============================================================================
# MODULO DEL PERSONAL
#==============================================================================

@app.route("/panel/personal", methods=['GET'])
def panel_personal():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    return render_template("privado/personal.html")


######################################################
############# INTERFAZ PARA LOS CHOFERES #############
######################################################

@app.route("/panel/personal/choferes", methods=['GET'])
def panel_personal_choferes():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    id_supervisor = session['id']

 
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


######################################################
############# REGISTRAR CHOFERES #####################
######################################################

@app.route("/registrar_personal_chofer", methods=['POST'])
def registrar_personal_chofer():
    cursor = mysql.connection.cursor()

    try:
        mysql.connection.begin()

        
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

        
        cursor.execute("""
            INSERT INTO empleado(id_persona, sueldo, fecha_ingreso)
            VALUES (%s, %s, %s)
        """, (
            id_persona,
            request.form["sueldo"],
            request.form["fecha_ingreso"]
        ))
        id_empleado = cursor.lastrowid

        
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



######################################################
############# ACTUALIZAR CHOFERES ####################
######################################################

@app.route("/actualizar_personal_chofer", methods=['POST'])
def actualizar_personal_chofer():
    cursor = mysql.connection.cursor()
    try:
        mysql.connection.begin()
        id_empleado = request.form["id_empleado"]

        
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

        
        cursor.execute("""
            UPDATE empleado
            SET sueldo=%s
            WHERE id_empleado=%s
        """, (request.form["sueldo"], id_empleado))

        
        cursor.execute("""
            UPDATE chofer
            SET nro_licencia=%s,
                años_experiencia=%s,
                id_tipo_licencia=%s,
                historial_infracciones=%s
            WHERE id_empleado=%s
        """, (
            request.form["nro_licencia"],
            request.form["anos_experiencia"],
            request.form["id_tipo_licencia"],
            request.form["historial_infracciones"],
            id_empleado
        ))

        mysql.connection.commit()
        flash("✔ Datos del chofer actualizados.", "success")
    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error: {str(e)}", "danger")
    finally:
        cursor.close()

    return redirect(url_for("panel_personal_choferes"))




######################################################
############# INTERFAZ PARA COBRADORES ###############
######################################################

@app.route("/panel/personal/cobradores", methods=['GET'])
def panel_personal_cobradores():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    id_supervisor = session['id']

   
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

    
    cursor.execute("SELECT id_idioma, nombre FROM idioma")
    lista_idiomas = cursor.fetchall()

    editar_personal = None
    idiomas_asociados = []

    
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


######################################################
############# REGISTRAR COBRADORES ###################
######################################################

@app.route("/registrar_personal_cobrador", methods=['POST'])
def registrar_personal_cobrador():
    cursor = mysql.connection.cursor()

    try:
        mysql.connection.begin()

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

        cursor.execute("""
            INSERT INTO empleado(id_persona, sueldo, fecha_ingreso, tipo_empleado)
            VALUES (%s, %s, %s, 'COBRADOR')
        """, (
            id_persona,
            request.form["sueldo"],
            request.form["fecha_ingreso"]
        ))
        id_empleado = cursor.lastrowid

      
        cursor.execute("""
            INSERT INTO cobrador(id_empleado)
            VALUES (%s)
        """, (id_empleado,))

        
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


######################################################
############# ACTUALIZAR COBRADORES ##################
######################################################

@app.route("/actualizar_personal_cobrador", methods=['POST'])
def actualizar_personal_cobrador():
    cursor = mysql.connection.cursor()

    try:
        mysql.connection.begin()

        id_empleado = request.form["id_empleado"]

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

        cursor.execute("""
            UPDATE empleado
            SET sueldo=%s
            WHERE id_empleado=%s
        """, (request.form["sueldo"], id_empleado))

        
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





#=============================================
# MODULO DE INCIDENCIAS
#=============================================
@app.route("/panel/incidencias", methods=['GET'])
def panel_incidencias():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template("privado/incidencias.html")




######################################################
############# INCIDENCIAS DISCIPLINARIAS #############
######################################################

@app.route("/panel/incidencias/disciplinarias", methods=['GET'])
def panel_incidencias_disciplinarias():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    id_supervisor = session['id']

 
    cursor.execute("""
        SELECT id_ruta
        FROM supervisor_ruta
        WHERE id_empleado=%s AND fecha_fin IS NULL
    """, (id_supervisor,))
    row = cursor.fetchone()
    id_ruta = row['id_ruta'] if row else None


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

 
    editar_id = request.args.get('editar')
    editar_incidencia = None
    if editar_id:
        cursor.execute("""
            SELECT i.id_incidencia, i.fecha, i.descripcion, i.estado,
                   id.tipo_disciplinaria, id.sancion
            FROM incidencia i
            JOIN incidencia_disciplinaria id ON i.id_incidencia=id.id_incidencia
            WHERE i.id_incidencia=%s
        """, (editar_id,))
        editar_incidencia = cursor.fetchone()

    cursor.close()

    return render_template("privado/incidencias_disciplinarias.html",
                           incidencias=incidencias,
                           id_ruta=id_ruta,
                           hoy=date.today().isoformat(),
                           editar_incidencia=editar_incidencia)



################################################################
############# REGISTRAR INCIDENCIAS DISCIPLINARIAS #############
################################################################

@app.route("/registrar_incidencia_disciplinaria", methods=['POST'])
def registrar_incidencia_disciplinaria():
    cursor = mysql.connection.cursor()
    try:
        try:
            fecha_obj = datetime.strptime(request.form["fecha"], "%Y-%m-%d").date()
        except ValueError:
            flash("❌ Fecha inválida. Usa formato YYYY-MM-DD.", "danger")
            return redirect(url_for("panel_incidencias_disciplinarias"))

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



#################################################################
############# ACTUALIZAR INCIDENCIAS DISCIPLINARIAS #############
#################################################################

@app.route("/actualizar_incidencia_disciplinaria", methods=['POST'])
def actualizar_incidencia_disciplinaria():
    cursor = mysql.connection.cursor()
    try:
        id_incidencia = request.form["id_incidencia"]

        try:
            fecha_obj = datetime.strptime(request.form["fecha"], "%Y-%m-%d").date()
        except ValueError:
            flash("❌ Fecha inválida. Usa formato YYYY-MM-DD.", "danger")
            return redirect(url_for("panel_incidencias_disciplinarias"))

        if fecha_obj < date(2000, 1, 1) or fecha_obj > date.today():
            flash("❌ Fecha fuera del rango permitido (2000 hasta hoy).", "danger")
            return redirect(url_for("panel_incidencias_disciplinarias"))

        mysql.connection.begin()

        cursor.execute("""
            UPDATE incidencia
            SET fecha=%s, descripcion=%s, estado=%s
            WHERE id_incidencia=%s
        """, (
            fecha_obj,
            request.form["descripcion"],
            request.form["estado"],
            id_incidencia
        ))

        cursor.execute("""
            UPDATE incidencia_disciplinaria
            SET tipo_disciplinaria=%s, sancion=%s
            WHERE id_incidencia=%s
        """, (
            request.form["tipo_disciplinaria"],
            request.form["sancion"],
            id_incidencia
        ))

        mysql.connection.commit()
        flash("✔ Incidencia disciplinaria actualizada.", "success")
    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error: {str(e)}", "danger")
    finally:
        cursor.close()

    return redirect(url_for("panel_incidencias_disciplinarias"))


###############################################################
############# ELIMINAR INCIDENCIAS DISCIPLINARIAS #############
###############################################################

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






#=============================================
# INCIDENCIAS OPERATIVAS
#=============================================
@app.route("/panel/incidencias/operativas", methods=['GET'])
def panel_incidencias_operativas():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    id_supervisor = session['id']

    cursor.execute("""
        SELECT id_ruta
        FROM supervisor_ruta
        WHERE id_empleado=%s AND fecha_fin IS NULL
    """, (id_supervisor,))
    row = cursor.fetchone()
    id_ruta = row['id_ruta'] if row else None

    
    if id_ruta:
        cursor.execute("""
            SELECT i.id_incidencia, i.fecha, i.descripcion, i.estado,
                   io.gravedad, io.costo, io.requiere_seguro
            FROM incidencia i
            JOIN incidencia_operativa io ON i.id_incidencia=io.id_incidencia
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

    
    editar_id = request.args.get('editar')
    editar_incidencia = None
    if editar_id:
        cursor.execute("""
            SELECT i.id_incidencia, i.fecha, i.descripcion, i.estado,
                   io.gravedad, io.costo, io.requiere_seguro
            FROM incidencia i
            JOIN incidencia_operativa io ON i.id_incidencia=io.id_incidencia
            WHERE i.id_incidencia=%s
        """, (editar_id,))
        editar_incidencia = cursor.fetchone()

    cursor.close()

   
    return render_template("privado/incidencias_operativas.html",
                           incidencias=incidencias,
                           id_ruta=id_ruta,
                           hoy=date.today().isoformat(),
                           editar_incidencia=editar_incidencia)




############################################################
############# REGISTRAR INCIDENCIAS OPERATIVAS #############
############################################################

@app.route("/registrar_incidencia_operativa", methods=['POST'])
def registrar_incidencia_operativa():
    cursor = mysql.connection.cursor()
    try:
        try:
            fecha_obj = datetime.strptime(request.form["fecha"], "%Y-%m-%d").date()
        except ValueError:
            flash("❌ Fecha inválida. Usa formato YYYY-MM-DD.", "danger")
            return redirect(url_for("panel_incidencias_operativas"))

        if fecha_obj < date(2000, 1, 1) or fecha_obj > date.today():
            flash("❌ Fecha fuera del rango permitido (2000 hasta hoy).", "danger")
            return redirect(url_for("panel_incidencias_operativas"))

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

        requiere_seguro = 1 if request.form.get("requiere_seguro") == "on" else 0
        costo = request.form.get("costo") or 0

        cursor.execute("""
            INSERT INTO incidencia_operativa(id_incidencia, gravedad, costo, requiere_seguro)
            VALUES (%s, %s, %s, %s)
        """, (
            id_incidencia,
            request.form["gravedad"],
            costo,
            requiere_seguro
        ))

        mysql.connection.commit()
        flash("✔ Incidencia operativa registrada.", "success")
    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error: {str(e)}", "danger")
    finally:
        cursor.close()

    return redirect(url_for("panel_incidencias_operativas"))



#############################################################
############# ACTUALIZAR INCIDENCIAS OPERATIVAS #############
#############################################################

@app.route("/actualizar_incidencia_operativa", methods=['POST'])
def actualizar_incidencia_operativa():
    cursor = mysql.connection.cursor()
    try:
        id_incidencia = request.form["id_incidencia"]

        try:
            fecha_obj = datetime.strptime(request.form["fecha"], "%Y-%m-%d").date()
        except ValueError:
            flash("❌ Fecha inválida. Usa formato YYYY-MM-DD.", "danger")
            return redirect(url_for("panel_incidencias_operativas"))

        if fecha_obj < date(2000, 1, 1) or fecha_obj > date.today():
            flash("❌ Fecha fuera del rango permitido (2000 hasta hoy).", "danger")
            return redirect(url_for("panel_incidencias_operativas"))

        mysql.connection.begin()

        cursor.execute("""
            UPDATE incidencia
            SET fecha=%s, descripcion=%s, estado=%s
            WHERE id_incidencia=%s
        """, (
            fecha_obj,
            request.form["descripcion"],
            request.form["estado"],
            id_incidencia
        ))

        requiere_seguro = 1 if request.form.get("requiere_seguro") == "on" else 0
        costo = request.form.get("costo") or 0

        cursor.execute("""
            UPDATE incidencia_operativa
            SET gravedad=%s, costo=%s, requiere_seguro=%s
            WHERE id_incidencia=%s
        """, (
            request.form["gravedad"],
            costo,
            requiere_seguro,
            id_incidencia
        ))

        mysql.connection.commit()
        flash("✔ Incidencia operativa actualizada.", "success")
    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error: {str(e)}", "danger")
    finally:
        cursor.close()

    return redirect(url_for("panel_incidencias_operativas"))





############################################################
############# ELIMINAR INCIDENCIAS OPERATIVAS ##############
############################################################

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
    finally:
        cursor.close()

    return redirect(url_for("panel_incidencias_operativas"))







#=============================================
# PANEL DE CAJA
#=============================================

@app.route("/panel/caja", methods=['GET'])
def panel_caja():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor) 
    id_supervisor = session['id']

    cursor.execute("""
        SELECT id_ruta
        FROM supervisor_ruta
        WHERE id_empleado=%s AND fecha_fin IS NULL
    """, (id_supervisor,))
    row = cursor.fetchone()
    id_ruta = row['id_ruta'] if row else None

    cajas, empleados, buses = [], [], []

    if id_ruta:
       
        cursor.execute("""
            SELECT c.id_caja, c.fecha, c.monto_recaudado, c.observacion,
                   e.id_empleado, p.nombre, p.apellido, b.id_bus, b.placa
            FROM caja c
            JOIN empleado e ON c.id_empleado = e.id_empleado
            JOIN persona p ON e.id_persona = p.id_persona
            JOIN bus b ON c.id_bus = b.id_bus
            WHERE c.id_ruta=%s
            ORDER BY c.fecha DESC
        """, (id_ruta,))
        cajas = cursor.fetchall()


        cursor.execute("""
            (
                SELECT DISTINCT e.id_empleado, p.nombre, p.apellido
                FROM persona p
                JOIN empleado e ON e.id_persona = p.id_persona
                JOIN cobrador co ON e.id_empleado = co.id_empleado 
                WHERE e.id_empleado IN (
                    SELECT ab.id_empleado
                    FROM asignacion_bus ab
                    JOIN bus_ruta br ON ab.id_bus = br.id_bus
                    WHERE br.id_ruta = %s
                )
            )
            UNION
            (
                SELECT e.id_empleado, p.nombre, p.apellido
                FROM persona p
                JOIN empleado e ON e.id_persona = p.id_persona
                JOIN cobrador co ON e.id_empleado = co.id_empleado 
                WHERE e.id_empleado NOT IN (SELECT id_empleado FROM asignacion_bus)
            )
        """, (id_ruta,))
        empleados = cursor.fetchall()

       
        cursor.execute("""
            SELECT b.id_bus, b.placa
            FROM bus b
            JOIN bus_ruta br ON b.id_bus = br.id_bus
            WHERE br.id_ruta = %s
        """, (id_ruta,))
        buses = cursor.fetchall()

    cursor.close()
    hoy = datetime.today().strftime("%Y-%m-%d")

    return render_template("privado/caja.html",
                           cajas=cajas, 
                           empleados=empleados,
                           buses=buses,
                           id_ruta=id_ruta,
                           editar_caja=None,
                           hoy=hoy)




#################################################
############# REGISTRAR RECAUDACION #############
#################################################

@app.route("/registrar_caja", methods=['POST'])
def registrar_caja():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor) 
    id_supervisor = session['id']

    try:
        cursor.execute("""
            SELECT id_ruta
            FROM supervisor_ruta
            WHERE id_empleado=%s AND fecha_fin IS NULL
        """, (id_supervisor,))
        row = cursor.fetchone()
        id_ruta = row['id_ruta'] if row else None

        if not id_ruta:
            flash("❌ No tienes una ruta activa.", "danger")
            return redirect(url_for("panel_caja"))

        fecha = request.form.get("fecha")
        monto = request.form.get("monto")
        observacion = request.form.get("observacion")
        id_empleado = request.form.get("id_empleado")
        id_bus = request.form.get("id_bus")

        if not fecha or not monto or not id_empleado or not id_bus:
            flash("❌ Debes completar todos los campos obligatorios.", "danger")
            return redirect(url_for("panel_caja"))

        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
        monto = float(monto)

        mysql.connection.begin()
        cursor.execute("""
            INSERT INTO caja(id_empleado, id_ruta, id_bus, fecha, monto_recaudado, observacion)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (id_empleado, id_ruta, id_bus, fecha_obj, monto, observacion))
        mysql.connection.commit()
        flash("✔ Recaudación registrada correctamente.", "success")

    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error: {str(e)}", "danger")
    finally:
        cursor.close()

    return redirect(url_for("panel_caja"))



#################################################
############# ELIMINAR RECAUDACION #############
#################################################

@app.route("/eliminar_caja/<int:id_caja>", methods=['GET'])
def eliminar_caja(id_caja):
    if 'usuario' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor) 
    try:
        mysql.connection.begin()
        cursor.execute("DELETE FROM caja WHERE id_caja=%s", (id_caja,))
        mysql.connection.commit()
        flash("✔ Recaudación eliminada.", "success")
    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error: {str(e)}", "danger")
    finally:
        cursor.close()

    return redirect(url_for("panel_caja"))



#################################################
############# EDITAR RECAUDACION ################
#################################################

@app.route("/editar_caja/<int:id_caja>", methods=['GET'])
def editar_caja(id_caja):
    if 'usuario' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor) 
    id_supervisor = session['id']

    cursor.execute("""
        SELECT id_ruta
        FROM supervisor_ruta
        WHERE id_empleado=%s AND fecha_fin IS NULL
    """, (id_supervisor,))
    row = cursor.fetchone()
    id_ruta = row['id_ruta'] if row else None

    
    cursor.execute("SELECT * FROM caja WHERE id_caja=%s", (id_caja,))
    editar_caja = cursor.fetchone()

    
    cajas = []
    if id_ruta:
        cursor.execute("""
            SELECT c.id_caja, c.fecha, c.monto_recaudado, c.observacion,
                   e.id_empleado, p.nombre, p.apellido, b.id_bus, b.placa
            FROM caja c
            JOIN empleado e ON c.id_empleado = e.id_empleado
            JOIN persona p ON e.id_persona = p.id_persona
            JOIN bus b ON c.id_bus = b.id_bus
            WHERE c.id_ruta=%s
            ORDER BY c.fecha DESC
        """, (id_ruta,))
        cajas = cursor.fetchall()
    
    
    cursor.execute("""
        (
            SELECT DISTINCT e.id_empleado, p.nombre, p.apellido
            FROM persona p
            JOIN empleado e ON e.id_persona = p.id_persona
            JOIN cobrador co ON e.id_empleado = co.id_empleado 
            WHERE e.id_empleado IN (
                SELECT ab.id_empleado
                FROM asignacion_bus ab
                JOIN bus_ruta br ON ab.id_bus = br.id_bus
                WHERE br.id_ruta = %s
            )
        )
        UNION
        (
            SELECT e.id_empleado, p.nombre, p.apellido
            FROM persona p
            JOIN empleado e ON e.id_persona = p.id_persona
            JOIN cobrador co ON e.id_empleado = co.id_empleado 
            WHERE e.id_empleado NOT IN (SELECT id_empleado FROM asignacion_bus)
        )
    """, (id_ruta,)) 
    empleados = cursor.fetchall()

    cursor.execute("""
        SELECT b.id_bus, b.placa
        FROM bus b
        JOIN bus_ruta br ON b.id_bus = br.id_bus
        WHERE br.id_ruta = %s
    """, (id_ruta,))
    buses = cursor.fetchall()

    cursor.close()
    hoy = datetime.today().strftime("%Y-%m-%d")

    return render_template("privado/caja.html",
                           cajas=cajas,
                           empleados=empleados,
                           buses=buses,
                           id_ruta=id_ruta,
                           editar_caja=editar_caja,
                           hoy=hoy)



##################################################
############# ACTUALIZAR RECAUDACION #############
##################################################

@app.route("/actualizar_caja", methods=['POST'])
def actualizar_caja():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor) 
    try:
        id_caja = request.form["id_caja"]
        fecha = request.form["fecha"]
        monto = float(request.form["monto"])
        observacion = request.form["observacion"]
        id_empleado = request.form["id_empleado"]
        id_bus = request.form["id_bus"]

        mysql.connection.begin()
        cursor.execute("""
            UPDATE caja
            SET fecha=%s, monto_recaudado=%s, observacion=%s,
                id_empleado=%s, id_bus=%s
            WHERE id_caja=%s
        """, (fecha, monto, observacion, id_empleado, id_bus, id_caja))
        mysql.connection.commit()
        flash("✔ Recaudación actualizada correctamente.", "success")

    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error al actualizar: {str(e)}", "danger")
    finally:
        cursor.close()

    return redirect(url_for("panel_caja"))







@app.route("/panel/rutas")
def panel_rutas():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template("privado/rutas.html")

@app.route("/panel/reportes")
def panel_reportes():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template("privado/reportes.html")


#=====================================================
# CERRAR SESION
#=====================================================
@app.route('/logout')
def logout():
    session.clear()
    flash("Sesión cerrada correctamente", "info")
    return redirect(url_for('login'))


#=====================================================
# EJECUCIÓN DEL SERVIDOR
#=====================================================
if __name__ == '__main__':
    app.run(debug=True)
