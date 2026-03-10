#!/usr/bin/env python3
"""
Flask web application with user authentication and session management.
Serves non-overlapping data samples to authenticated users.
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
from datetime import timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

db = SQLAlchemy(app)

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    user_number = db.Column(db.Integer, unique=True, nullable=True)  # 1-10 for data file mapping, null for admin
    current_index = db.Column(db.Integer, default=0)  # Track which sample user is currently on
    is_admin = db.Column(db.Boolean, default=False)  # Admin flag
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Model to store user answers
class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sample_index = db.Column(db.Integer, nullable=False)  # Index in user's data array
    answer = db.Column(db.String(10))  # "Yes" or "No"
    
    # Composite unique constraint: one answer per user per sample
    __table_args__ = (db.UniqueConstraint('user_id', 'sample_index', name='_user_sample_uc'),)

# Initialize database
with app.app_context():
    db.create_all()

def get_user_data(user_number):
    """Load user-specific data from their JSON file."""
    data_file = os.path.join('user_data', f'user_{user_number}_data.json')
    if os.path.exists(data_file):
        with open(data_file, 'r') as f:
            return json.load(f)
    return []

@app.route('/')
def index():
    """Home page - redirect to login if not authenticated."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and authentication handler."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session.permanent = True
            session['user_id'] = user.id
            session['username'] = user.username
            session['user_number'] = user.user_number
            session['is_admin'] = user.is_admin
            
            # Redirect admin to admin dashboard
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout handler."""
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    """Main dashboard - redirect to annotation page or admin dashboard."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Redirect admin to admin dashboard
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
    
    return redirect(url_for('annotate'))

@app.route('/annotate')
def annotate():
    """Annotation page - display one sample at a time with pagination."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session.get('user_id')
    user_number = session.get('user_number')
    
    # Get current user to check their progress
    user = User.query.get(user_id)
    current_index = user.current_index if user.current_index is not None else 0
    
    # Load user data
    user_data = get_user_data(user_number)
    total_samples = len(user_data)
    
    # Check if index is in URL params
    requested_index = request.args.get('index', type=int)
    if requested_index is not None and 0 <= requested_index < total_samples:
        current_index = requested_index
    
    # Get all answers for this user
    answers = Answer.query.filter_by(user_id=user_id).all()
    answer_map = {ans.sample_index: ans.answer for ans in answers}
    
    return render_template('annotate.html', 
                         username=session.get('username'),
                         user_number=user_number,
                         current_index=current_index,
                         total_samples=total_samples,
                         answer_map=answer_map)

@app.route('/api/sample/<int:index>')
def get_sample(index):
    """API endpoint to get a specific sample by index."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_number = session.get('user_number')
    user_data = get_user_data(user_number)
    
    if 0 <= index < len(user_data):
        sample = user_data[index]
        
        # Parse Facts and Query from Question field
        question_text = sample.get('Question', '')
        facts = ''
        query = ''
        
        if 'Facts:' in question_text and 'Query:' in question_text:
            parts = question_text.split('Query:')
            if len(parts) == 2:
                query = parts[1].strip()
                facts_part = parts[0]
                if 'Facts:' in facts_part:
                    facts = facts_part.split('Facts:')[1].strip()
        
        return jsonify({
            'index': index,
            'facts': facts,
            'query': query,
            'total': len(user_data)
        })
    else:
        return jsonify({'error': 'Invalid index'}), 404

@app.route('/api/save_answer', methods=['POST'])
def save_answer():
    """API endpoint to save user's answer for a sample."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session.get('user_id')
    data = request.get_json()
    
    sample_index = data.get('index')
    answer = data.get('answer')
    
    if sample_index is None or answer not in ['Yes', 'No']:
        return jsonify({'error': 'Invalid data'}), 400
    
    # Check if answer already exists
    existing_answer = Answer.query.filter_by(user_id=user_id, sample_index=sample_index).first()
    
    if existing_answer:
        existing_answer.answer = answer
    else:
        new_answer = Answer(user_id=user_id, sample_index=sample_index, answer=answer)
        db.session.add(new_answer)
    
    # Update user's current index
    user = User.query.get(user_id)
    user.current_index = sample_index
    
    db.session.commit()
    
    return jsonify({'success': True, 'index': sample_index, 'answer': answer})

@app.route('/api/get_answer/<int:index>')
def get_answer(index):
    """API endpoint to get saved answer for a specific sample."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session.get('user_id')
    answer_obj = Answer.query.filter_by(user_id=user_id, sample_index=index).first()
    
    if answer_obj:
        return jsonify({'answer': answer_obj.answer})
    else:
        return jsonify({'answer': None})

@app.route('/api/data')
def api_data():
    """API endpoint to get user's data as JSON."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_number = session.get('user_number')
    user_data = get_user_data(user_number)
    
    return jsonify({
        'username': session.get('username'),
        'user_number': user_number,
        'total_samples': len(user_data),
        'data': user_data
    })

@app.route('/admin')
def admin_dashboard():
    """Admin dashboard - shows all users and their progress."""
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))
    
    # Get all non-admin users
    users = User.query.filter_by(is_admin=False).order_by(User.user_number).all()
    
    # Get progress for each user
    user_progress = []
    for user in users:
        answers_count = Answer.query.filter_by(user_id=user.id).count()
        user_data = get_user_data(user.user_number)
        total_samples = len(user_data) if user_data else 0
        
        user_progress.append({
            'id': user.id,
            'username': user.username,
            'user_number': user.user_number,
            'answered': answers_count,
            'total': total_samples,
            'progress_percent': round((answers_count / total_samples * 100) if total_samples > 0 else 0, 1)
        })
    
    return render_template('admin_dashboard.html', 
                         username=session.get('username'),
                         users=user_progress)

@app.route('/admin/user/<int:user_id>')
def admin_view_user(user_id):
    """Admin view - shows detailed progress for a specific user."""
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))
    
    user = User.query.get_or_404(user_id)
    
    if user.is_admin:
        return "Cannot view admin users", 403
    
    # Get all answers for this user
    answers = Answer.query.filter_by(user_id=user_id).all()
    answer_map = {ans.sample_index: ans.answer for ans in answers}
    
    # Get user data
    user_data = get_user_data(user.user_number)
    
    # Build detailed progress
    samples_with_answers = []
    for idx, sample in enumerate(user_data):
        samples_with_answers.append({
            'index': idx,
            'answer': answer_map.get(idx, 'Not answered'),
            'question_preview': sample.get('Question', '')[:100] + '...' if len(sample.get('Question', '')) > 100 else sample.get('Question', '')
        })
    
    return render_template('admin_user_detail.html',
                         admin_username=session.get('username'),
                         user=user,
                         samples=samples_with_answers,
                         total_samples=len(user_data),
                         answered_count=len(answer_map))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=True, host='0.0.0.0', port=port)
