from flask import Flask, render_template, request, redirect, url_for
from flask_mysqldb import MySQL
from config import Config
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)

# Inicializa MySQL (no hace consultas automáticas aquí)
mysql = MySQL(app)

# context processor para pasar el año actual al footer
@app.context_processor
def inject_current_year():
    return {'current_year': datetime.now().year}

# ------------------ RUTAS PUBLICAS ------------------

@app.route('/')
def index():
    return render_template('publico/index.html')

@app.route('/rutas')
def rutas():
    return render_template('publico/rutas.html')

@app.route('/contacto', methods=['GET', 'POST'])
def contacto():
    if request.method == 'POST':
        # por ahora formulario es estático; si quieres podemos guardar el mensaje en BD luego
        nombre = request.form.get('nombre')
        email = request.form.get('email')
        mensaje = request.form.get('mensaje')
        # aquí podrías insertar en la BD si quieres
        return render_template('publico/contacto.html', enviado=True, nombre=nombre)
    return render_template('publico/contacto.html')

@app.route('/login', methods=['GET'])
def login():
    return render_template('autenticacion/login.html')

# ruta de prueba
@app.route('/ping')
def ping():
    return "pong!"

# ------------------ FUTURO: AUTH y PRIVADO ------------------
# más adelante añadiremos POST de /auth/login, validación y panel privado

if __name__ == '__main__':
    app.run(debug=True)
