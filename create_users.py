#!/usr/bin/env python3
"""
Script to create 10 user accounts in the backend.
This is run once to set up the user database.
"""

from app import app, db, User

def create_users():
    """Create 10 user accounts with default passwords."""
    with app.app_context():
        # Clear existing users (optional)
        User.query.delete()
        
        # Create 10 users
        for i in range(1, 11):
            username = f'user{i}'
            password = f'password{i}'  # Change these in production!
            
            user = User(username=username, user_number=i)
            user.set_password(password)
            db.session.add(user)
            print(f"Created user: {username} (password: {password})")
        
        db.session.commit()
        print("\nAll 10 users created successfully!")
        print("\nUser credentials:")
        print("-" * 40)
        for i in range(1, 11):
            print(f"Username: user{i}, Password: password{i}")

if __name__ == '__main__':
    create_users()
