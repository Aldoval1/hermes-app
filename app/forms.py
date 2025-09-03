from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, TextAreaField, IntegerField, FloatField, DateField, TimeField, HiddenField
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms.validators import DataRequired, EqualTo, NumberRange

class LoginForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    role = SelectField('Tipo de Cuenta', choices=[('cliente', 'Cliente'), ('vendedor', 'Vendedor'), ('admin', 'Administrador')])
    submit = SubmitField('Iniciar Sesión')

class RegistrationForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    password2 = PasswordField('Repetir Contraseña', validators=[DataRequired(), EqualTo('password')])
    discord = StringField('Discord', validators=[DataRequired()])
    role = SelectField('Quiero ser', choices=[('cliente', 'Cliente'), ('vendedor', 'Vendedor')])
    submit = SubmitField('Registrarse')

class AddProductForm(FlaskForm):
    name = StringField('Nombre del Producto', validators=[DataRequired()])
    price = FloatField('Precio', validators=[DataRequired(), NumberRange(min=0)])
    category = SelectField('Categoría', choices=[('Armas', 'Armas'), ('Sustancias', 'Sustancias'), ('Minerales', 'Minerales'), ('Otros', 'Otros')], validators=[DataRequired()])
    description = TextAreaField('Descripción')
    stock = IntegerField('Stock', validators=[DataRequired(), NumberRange(min=0)])
    image = FileField('Imagen del Producto', validators=[FileRequired(), FileAllowed(['jpg', 'png', 'jpeg'], '¡Solo imágenes!')])
    meetup_date = DateField('Fecha de Encuentro', format='%Y-%m-%d', validators=[DataRequired()])
    meetup_time = TimeField('Hora de Encuentro', format='%H:%M', validators=[DataRequired()])
    meetup_location = HiddenField('Ubicación de Encuentro', validators=[DataRequired()])
    submit = SubmitField('Añadir Producto')

class EditProductForm(FlaskForm):
    name = StringField('Nombre del Producto', validators=[DataRequired()])
    price = FloatField('Precio', validators=[DataRequired(), NumberRange(min=0)])
    category = SelectField('Categoría', choices=[('Armas', 'Armas'), ('Sustancias', 'Sustancias'), ('Minerales', 'Minerales'), ('Otros', 'Otros')], validators=[DataRequired()])
    description = TextAreaField('Descripción')
    stock = IntegerField('Stock', validators=[DataRequired(), NumberRange(min=0)])
    image = FileField('Nueva Imagen (Opcional)', validators=[FileAllowed(['jpg', 'png', 'jpeg'], '¡Solo imágenes!')])
    meetup_date = DateField('Fecha de Encuentro', format='%Y-%m-%d', validators=[DataRequired()])
    meetup_time = TimeField('Hora de Encuentro', format='%H:%M', validators=[DataRequired()])
    meetup_location = HiddenField('Ubicación de Encuentro', validators=[DataRequired()])
    submit = SubmitField('Actualizar Producto')