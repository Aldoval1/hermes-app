from app import create_app, db
from app.models import User
import sys

def seed_admin():
    app = create_app()
    with app.app_context():
        # Check if Admin exists
        admin = User.query.filter_by(dni='000').first()
        if admin:
            print("Admin account already exists.")
            return

        print("Creating Admin account (DNI 000, Pass 000)...")
        # Ensure upload folder exists for consistency (though admin might not have photo)

        admin = User(
            first_name='Admin',
            last_name='Gobierno',
            dni='000',
            badge_id='000', # Assuming badge matches DNI for simplicity or unique
            department='Gobierno',
            official_rank='Lider',
            official_status='Aprobado',
            selfie_filename='default_admin.jpg', # Needs to handle if file missing, but DB just stores string
            dni_photo_filename='default_admin.jpg'
        )
        admin.set_password('000')
        db.session.add(admin)
        db.session.commit()
        print("Admin account created successfully.")

if __name__ == '__main__':
    seed_admin()
