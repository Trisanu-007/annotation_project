# Annotation Project - Web Application

A Flask-based web application for annotating logical reasoning questions with user authentication, progress tracking, and admin dashboard.

## Features

- ✅ **User Authentication**: 10 pre-created user accounts with username/password login
- ✅ **Session Management**: Sessions persist across browser restarts (7-day expiry)
- ✅ **Data Partitioning**: Each user gets 20 unique, non-overlapping samples
- ✅ **Annotation Interface**: Clean UI with Facts/Rules/Query display, Yes/No options
- ✅ **Progress Tracking**: Auto-save answers, visual progress bar, keyboard shortcuts
- ✅ **Admin Dashboard**: Monitor all users' progress and view their answers
- ✅ **Secure**: Password hashing, session security, authentication required

## Quick Start

### Local Development
```bash
conda activate trial
python3 app.py
# Visit http://localhost:5001
```

### User Credentials
- Users: user1-user10 / password1-password10
- Admin: admin / admin123

## Deployment

**Netlify won't work** for this Flask app. Use these instead:

1. **Railway** (Recommended) - Free, easy GitHub integration
2. **Heroku** - GitHub Student Pack includes credits
3. **DigitalOcean** - $200 credit with GitHub Student Pack
4. **Render** - Free tier available

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions.

## Project Structure

```
.
├── app.py                          # Main Flask application
├── create_users.py                 # Script to create user accounts
├── split_data.py                   # Script to split parquet data
├── users.db                        # SQLite database (auto-created)
├── templates/
│   ├── login.html                  # Login page
│   └── dashboard.html              # User dashboard
├── user_data/
│   ├── metadata.json               # Data partition metadata
│   ├── user_1_data.json           # User 1's 20 samples
│   ├── user_2_data.json           # User 2's 20 samples
│   └── ...                         # (10 total)
└── alice_test_depth0-50_complete.parquet  # Source data file
```

## Setup Instructions

### 1. Activate Conda Environment
```bash
conda activate trial
```

### 2. Install Dependencies
```bash
pip install flask flask-sqlalchemy pandas pyarrow
```

### 3. Split Data (Already Done)
```bash
python3 split_data.py
```

### 4. Create User Accounts (Already Done)
```bash
python3 create_users.py
```

## Running the Application

### Start the Flask Server
```bash
python3 app.py
```

The application will be available at: **http://localhost:5000**

## User Credentials

| Username | Password   | Data File            |
|----------|-----------|----------------------|
| user1    | password1 | user_1_data.json    |
| user2    | password2 | user_2_data.json    |
| user3    | password3 | user_3_data.json    |
| user4    | password4 | user_4_data.json    |
| user5    | password5 | user_5_data.json    |
| user6    | password6 | user_6_data.json    |
| user7    | password7 | user_7_data.json    |
| user8    | password8 | user_8_data.json    |
| user9    | password9 | user_9_data.json    |
| user10   | password10| user_10_data.json   |

## Features

### Authentication System
- No registration - accounts are created in the backend
- Username/password authentication
- Password hashing using werkzeug.security
- Session-based authentication with 7-day persistence

### Data Management
- **Total samples**: 200 (from parquet file with 2550 rows)
- **Per user**: 20 non-overlapping samples
- **Users**: 10 accounts
- Each user's data is stored in a separate JSON file
- Metadata tracking for user assignments

### API Endpoints

#### Web Pages
- `GET /` - Home page (redirects to login or dashboard)
- `GET /login` - Login page
- `POST /login` - Authentication handler
- `GET /logout` - Logout and session clear
- `GET /dashboard` - User dashboard (authenticated)

#### API
- `GET /api/data` - Get user's data as JSON (authenticated)

### Session Management
- Sessions are permanent with 7-day lifetime
- Session data includes: user_id, username, user_number
- Sessions persist across browser restarts
- Secure session cookies with secret key

## Data Partitioning

The parquet file has been split into 10 separate JSON files:
- Each file contains exactly 20 samples
- Samples are sequential and non-overlapping
- User 1 gets samples 0-19
- User 2 gets samples 20-39
- ... and so on

## Development Notes

### Database
- SQLite database (`users.db`) stores user accounts
- User model includes: id, username, password_hash, user_number

### Security Notes
- Change `SECRET_KEY` in production!
- Update default passwords before deployment
- Consider adding HTTPS in production
- Current setup is for development/testing

## Next Steps (Pending User Input)

The backend and data management system is complete. Ready for UI specifications:
1. ✅ User authentication with session persistence
2. ✅ Non-overlapping data assignment (10 users × 20 samples)
3. ⏳ Custom UI design (awaiting specifications)

## Troubleshooting

### Import Errors
Make sure all dependencies are installed:
```bash
pip install flask flask-sqlalchemy pandas pyarrow
```

### Database Issues
To reset the database:
```bash
rm users.db
python3 create_users.py
```

### Data Files Missing
Re-run the split script:
```bash
python3 split_data.py
```
