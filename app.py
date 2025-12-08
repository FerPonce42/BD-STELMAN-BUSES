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
# LOGIN / AUTH
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
# PANEL PRIVADO - DASHBOARD
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
# MODULOS DEL SIDEBAR
# =====================================================

@app.route("/panel/buses", methods=["GET", "POST"])
def panel_buses():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()

    ### INSERTAR BUS
    if request.method == "POST":
        placa = request.form.get("placa")
        id_modelo_bus = request.form.get("id_modelo_bus")

        cursor.execute("SELECT placa FROM bus WHERE placa=%s", (placa,))
        existe = cursor.fetchone()

        if existe:
            flash("❌ Esa placa ya está registrada", "danger")
        else:
            cursor.execute("""
                INSERT INTO bus (placa, año_fabricacion, id_modelo_bus, id_almacen)
                VALUES (%s, YEAR(NOW()), %s, 1)
            """, (placa, id_modelo_bus))
            mysql.connection.commit()
            flash("✔️ Bus registrado correctamente", "success")

    ### CONSULTAR MODELOS PARA SELECT
    cursor.execute("SELECT id_modelo_bus AS id, nombre FROM modelo_bus")
    modelos = cursor.fetchall()

    ### CONSULTAR buses reales
    cursor.execute("""
        SELECT 
            b.placa,
            m.nombre AS modelo,
            ma.nombre AS marca,
            b.año_fabricacion AS año,
            b.ultima_revision AS revision
        FROM bus b
        JOIN modelo_bus m ON b.id_modelo_bus = m.id_modelo_bus
        JOIN marca_bus ma ON m.id_marca_bus = ma.id_marca_bus
    """)
    buses = cursor.fetchall()

    cursor.close()

    return render_template("privado/buses.html", buses=buses, modelos=modelos)



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
