from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64))
    dni = db.Column(db.String(20), index=True, unique=True)
    selfie_filename = db.Column(db.String(128))
    dni_photo_filename = db.Column(db.String(128))
    password_hash = db.Column(db.String(128))

    # Official fields
    badge_id = db.Column(db.String(20), index=True, unique=True, nullable=True)
    department = db.Column(db.String(50), nullable=True)
    official_rank = db.Column(db.String(20), default='Miembro') # 'Lider', 'Miembro'
    official_status = db.Column(db.String(20), default=None) # 'Pendiente', 'Aprobado', 'Rechazado'

    # Relationships
    police_reports = db.relationship('PoliceReport', foreign_keys='PoliceReport.user_id', backref='citizen', lazy=True)
    traffic_fines = db.relationship('TrafficFine', foreign_keys='TrafficFine.user_id', backref='citizen', lazy=True)
    licenses = db.relationship('License', backref='citizen', lazy=True)
    criminal_records = db.relationship('CriminalRecord', foreign_keys='CriminalRecord.user_id', backref='citizen', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class PoliceReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    author = db.relationship('User', foreign_keys=[author_id])

class TrafficFine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(200), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Pendiente')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    author = db.relationship('User', foreign_keys=[author_id])

class License(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False) # Conducir, Armas, Caza, Pesca...
    status = db.Column(db.String(20), default='Activa')
    expiration_date = db.Column(db.Date, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class CriminalRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    crime = db.Column(db.String(100), nullable=False)
    penal_code = db.Column(db.String(50))
    report_text = db.Column(db.Text)
    subject_photo = db.Column(db.String(128))
    evidence_photo = db.Column(db.String(128))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    author = db.relationship('User', foreign_keys=[author_id])
