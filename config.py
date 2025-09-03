import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'una-clave-secreta-muy-segura'
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'img')
    
    # Esta línea es la clave: usa la base de datos de Railway si existe,
    # si no, usa la base de datos local SQLite.
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'hermes.db')
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False