#!/usr/bin/env python3
"""
Create admin user for the annotation project.
"""

from app import app, db, User

def create_admin():
    with app.app_context():
        # Check if admin already exists
        admin = User.query.filter_by(username='admin').first()
        
        if admin:
            print("Admin user already exists!")
            print(f"Username: admin")
            return
        
        # Create admin user
        admin = User(
            username='admin',
            user_number=None,  # Admin doesn't have a user number
            is_admin=True
        )
        admin.set_password('admin123')  # You can change this password
        
        db.session.add(admin)
        db.session.commit()
        
        print("✓ Admin user created successfully!")
        print("\nAdmin credentials:")
        print("----------------------------------------")
        print("Username: admin")
        print("Password: admin123")
        print("----------------------------------------")
        print("\nYou can now login with these credentials to access the admin dashboard.")

if __name__ == '__main__':
    create_admin()
