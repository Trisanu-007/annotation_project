#!/usr/bin/env python3
"""
Flask web application with user authentication and session management.
Serves non-overlapping data samples to authenticated users.
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
import logging
import traceback
from datetime import timedelta, datetime
from logging.handlers import RotatingFileHandler

# Configure logging before app initialization
def setup_logging():
    """Setup logging configuration with file and console handlers."""
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Create formatter with timestamp
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s (%(funcName)s:%(lineno)d): %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler - rotates at 10MB, keeps 10 backup files
    file_handler = RotatingFileHandler(
        'logs/app.log',
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    return root_logger

# Initialize logging
logger = setup_logging()
logger.info("=" * 80)
logger.info("Application starting up...")
logger.info("=" * 80)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')
database_url = os.environ.get('DATABASE_URL')
if not database_url:
    raise RuntimeError('DATABASE_URL is required. Configure your external Render Postgres URL.')

if database_url.startswith('postgres://'):
    # Railway/Heroku sometimes provide postgres://, SQLAlchemy expects postgresql://
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

logger.info(f"SECRET_KEY configured: {'***' if app.config['SECRET_KEY'] else 'NOT SET'}")
logger.info(f"Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")

db = SQLAlchemy(app)
logger.info("SQLAlchemy initialized")

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


# Model to store annotation samples per user in the database
class AnnotationSample(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_number = db.Column(db.Integer, nullable=False, index=True)
    sample_index = db.Column(db.Integer, nullable=False)
    question = db.Column(db.Text, nullable=True)
    payload = db.Column(db.JSON, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('user_number', 'sample_index', name='_user_sample_index_uc'),
    )

# Initialize database
logger.info("Initializing database...")
try:
    with app.app_context():
        db.create_all()
        user_count = User.query.count()
        admin_count = User.query.filter_by(is_admin=True).count()
        logger.info(f"Database initialized successfully. Users: {user_count}, Admins: {admin_count}")
        logger.info("Auto user/admin creation is disabled at app startup")
            
except Exception as e:
    logger.error(f"Database initialization failed: {str(e)}")
    logger.error(traceback.format_exc())

def get_user_data(user_number):
    """Load user-specific data from database only."""
    db_samples = AnnotationSample.query.filter_by(user_number=user_number).order_by(AnnotationSample.sample_index).all()
    if db_samples:
        records = []
        for sample in db_samples:
            if isinstance(sample.payload, dict):
                row = dict(sample.payload)
            else:
                row = {}

            if 'Question' not in row and sample.question:
                row['Question'] = sample.question

            records.append(row)
        return records

    return []

def load_instructions_text():
    """Load help text from instructions.txt in the project root."""
    instructions_path = os.path.join(app.root_path, 'instructions.txt')

    try:
        with open(instructions_path, 'r', encoding='utf-8') as instructions_file:
            return instructions_file.read().strip()
    except FileNotFoundError:
        logger.warning(f"instructions.txt not found at {instructions_path}")
        return 'Help text is unavailable because instructions.txt is missing.'

@app.route('/')
def index():
    """Home page - redirect to login if not authenticated."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/health')
def health_check():
    """Health check endpoint for Render and other uptime probes."""
    db_status = 'ok'
    status_code = 200

    try:
        db.session.execute(text('SELECT 1'))
    except Exception as e:
        db_status = 'error'
        status_code = 503
        logger.error(f"Health check DB probe failed: {str(e)}")

    return jsonify({
        'status': 'ok' if status_code == 200 else 'degraded',
        'database': db_status,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }), status_code

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and authentication handler."""
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        
        logger.info(f"Login attempt for username: {username} from IP: {request.remote_addr}")

        if not username:
            logger.warning("Login failed: Username is missing")
            return render_template('login.html', error='Username is required.')

        if not password:
            logger.warning(f"Login failed: Password is missing for user '{username}'")
            return render_template('login.html', error='Password is required.')
        
        try:
            user = User.query.filter_by(username=username).first()
            
            if not user:
                logger.warning(f"Login failed: User '{username}' not found in database")
                return render_template('login.html', error=f"User '{username}' was not found.")
            
            logger.debug(f"User found: ID={user.id}, is_admin={user.is_admin}, user_number={user.user_number}")
            
            if user.check_password(password):
                session.permanent = True
                session['user_id'] = user.id
                session['username'] = user.username
                session['user_number'] = user.user_number
                session['is_admin'] = user.is_admin
                
                logger.info(f"Login successful for user: {username} (ID: {user.id}, Admin: {user.is_admin})")
                
                # Redirect admin to admin dashboard
                if user.is_admin:
                    return redirect(url_for('admin_dashboard'))
                else:
                    return redirect(url_for('dashboard'))
            else:
                logger.warning(f"Login failed: Invalid password for user '{username}'")
                return render_template('login.html', error='Incorrect password. Please try again.')
        except Exception as e:
            logger.error(f"Exception during login for username '{username}': {str(e)}")
            logger.error(traceback.format_exc())
            return render_template('login.html', error='Login failed due to a server error. Please try again.')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout handler."""
    username = session.get('username', 'Unknown')
    logger.info(f"User {username} logged out")
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
                         answer_map=answer_map,
                         help_text=load_instructions_text())

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
        
        # Extract Predicted Proof Chain
        predicted_proof_chain = sample.get('Predicted_Proof_Chain', '')
        
        return jsonify({
            'index': index,
            'facts': facts,
            'query': query,
            'predicted_proof_chain': predicted_proof_chain,
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
        logger.warning(f"Unauthorized access attempt to admin dashboard from {request.remote_addr}")
        return redirect(url_for('login'))
    
    try:
        admin_username = session.get('username')
        logger.info(f"Admin {admin_username} accessing dashboard")
    
        # Get all non-admin users
        users = User.query.filter_by(is_admin=False).order_by(User.user_number).all()
        logger.debug(f"Found {len(users)} regular users")
    
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
        
        logger.debug(f"Rendering admin dashboard with {len(user_progress)} users")
        
        return render_template('admin_dashboard.html',
                             admin_username=admin_username,
                             users=user_progress)
    except Exception as e:
        logger.error(f"Error in admin dashboard: {str(e)}")
        logger.error(traceback.format_exc())
        return "An error occurred", 500

@app.route('/admin/user/<int:user_id>')
def admin_view_user(user_id):
    """Admin view - shows detailed progress for a specific user."""
    if 'user_id' not in session or not session.get('is_admin'):
        logger.warning(f"Unauthorized access attempt to view user {user_id} from {request.remote_addr}")
        return redirect(url_for('login'))
    
    try:
        admin_username = session.get('username')
        logger.info(f"Admin {admin_username} viewing user ID {user_id}")
        
        user = User.query.get_or_404(user_id)
        
        if user.is_admin:
            logger.warning(f"Admin {admin_username} attempted to view another admin user")
            return "Cannot view admin users", 403
        
        # Get all answers for this user
        answers = Answer.query.filter_by(user_id=user_id).all()
        answer_map = {ans.sample_index: ans.answer for ans in answers}
        
        # Get user data
        user_data = get_user_data(user.user_number)
        
        logger.debug(f"User {user.username}: {len(answer_map)}/{len(user_data)} answers")
        
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
    except Exception as e:
        logger.error(f"Error viewing user {user_id}: {str(e)}")
        logger.error(traceback.format_exc())
        return "An error occurred", 500

@app.route('/admin/user/<int:user_id>/download')
def admin_download_user_annotations(user_id):
    """Admin-only JSON download for a user's annotations."""
    if 'user_id' not in session or not session.get('is_admin'):
        logger.warning(f"Unauthorized download attempt for user {user_id} from {request.remote_addr}")
        return redirect(url_for('login'))

    try:
        admin_username = session.get('username')
        user = User.query.get_or_404(user_id)

        if user.is_admin:
            logger.warning(f"Admin {admin_username} attempted to download admin user data")
            return "Cannot download admin user data", 403

        answers = Answer.query.filter_by(user_id=user_id).all()
        answer_map = {ans.sample_index: ans.answer for ans in answers}
        user_data = get_user_data(user.user_number)

        annotations = []

        for idx, sample in enumerate(user_data):
            answer = answer_map.get(idx, '')
            status = 'answered' if answer else 'not_answered'
            annotations.append({
                'sample_index': idx,
                'answer': answer,
                'status': status,
                'sample': sample,
            })

        payload = {
            'username': user.username,
            'user_number': user.user_number,
            'total_samples': len(user_data),
            'answered_count': len(answer_map),
            'exported_at': datetime.utcnow().isoformat() + 'Z',
            'annotations': annotations,
        }

        filename = f"annotations_{user.username}.json"
        logger.info(f"Admin {admin_username} downloaded annotations for {user.username}")

        return Response(
            json.dumps(payload, ensure_ascii=False, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        logger.error(f"Error downloading annotations for user {user_id}: {str(e)}")
        logger.error(traceback.format_exc())
        return "An error occurred while preparing download", 500

if __name__ == '__main__':
    try:
        port = int(os.environ.get('PORT', 5001))
        logger.info(f"Starting Flask application on port {port}")
        logger.info(f"Debug mode: {True}")
        logger.info(f"Host: 0.0.0.0")
        app.run(debug=True, host='0.0.0.0', port=port)
    except Exception as e:
        logger.critical(f"Failed to start application: {str(e)}")
        logger.critical(traceback.format_exc())
        raise
