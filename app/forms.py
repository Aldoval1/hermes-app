from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectField
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms.validators import DataRequired, EqualTo

class LoginForm(FlaskForm):
    dni = StringField('DNI', validators=[DataRequired()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    remember_me = BooleanField('Recordar datos')
    submit = SubmitField('Iniciar Sesión')

class RegistrationForm(FlaskForm):
    first_name = StringField('Nombre', validators=[DataRequired()])
    last_name = StringField('Apellido', validators=[DataRequired()])
    dni = StringField('DNI', validators=[DataRequired()])
    selfie = FileField('Foto Selfie', validators=[
        FileRequired(),
        FileAllowed(['jpg', 'png', 'jpeg'], 'Solo imágenes permitidas')
    ])
    dni_photo = FileField('Foto DNI', validators=[
        FileRequired(),
        FileAllowed(['jpg', 'png', 'jpeg'], 'Solo imágenes permitidas')
    ])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    confirm_password = PasswordField('Confirmar Contraseña', validators=[
        DataRequired(),
        EqualTo('password', message='Las contraseñas deben coincidir')
    ])
    submit = SubmitField('Registrarse')

class OfficialLoginForm(FlaskForm):
    badge_id = StringField('Placa de ID', validators=[DataRequired()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    remember_me = BooleanField('Recordar datos')
    submit = SubmitField('Entrar')

class OfficialRegistrationForm(FlaskForm):
    first_name = StringField('Nombre', validators=[DataRequired()])
    last_name = StringField('Apellido', validators=[DataRequired()])
    dni = StringField('DNI', validators=[DataRequired()])
    badge_id = StringField('Placa de ID', validators=[DataRequired()])
    department = SelectField('Departamento', choices=[
        ('Gobierno', 'Gobierno'),
        ('Policia', 'Policia'),
        ('SABES', 'SABES'),
        ('Sheriff', 'Sheriff'),
        ('LSFD', 'LSFD'),
        ('Universidad', 'Universidad')
    ], validators=[DataRequired()])
    photo = FileField('Foto Personal', validators=[
        FileRequired(),
        FileAllowed(['jpg', 'png', 'jpeg'], 'Solo imágenes permitidas')
    ])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    confirm_password = PasswordField('Confirmar Contraseña', validators=[
        DataRequired(),
        EqualTo('password', message='Las contraseñas deben coincidir')
    ])
    submit = SubmitField('Solicitar Registro')
