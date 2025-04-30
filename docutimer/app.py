from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from flask_cors import CORS
import re
import os

# app = Flask(__name__)
# 
# # Create the instance directory
# os.makedirs('instance', exist_ok=True)
# 
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/docutimer.db'
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# app.config['JWT_SECRET_KEY'] = 'your-secret-key'  # Change this in production
# app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)
# db = SQLAlchemy(app)
# jwt = JWTManager(app)

# Create Flask app
app = Flask(__name__)
CORS(app)

# Get absolute path for the database
basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, 'instance')

# Create instance directory if it doesn't exist
os.makedirs(instance_path, exist_ok=True)

# Configure Flask app
app.config.update(
    SQLALCHEMY_DATABASE_URI=f'sqlite:///{os.path.join(instance_path, "docutimer.db")}',
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    JWT_SECRET_KEY='your-secret-key',  # Change this in production
    JWT_ACCESS_TOKEN_EXPIRES=timedelta(hours=24)
)


# Initialize extensions
db = SQLAlchemy(app)
jwt = JWTManager(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

class Entry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    cost = db.Column(db.String(20))
    currency = db.Column(db.String(10))
    frequency = db.Column(db.String(20))
    start_date = db.Column(db.String(10), nullable=False)
    end_date = db.Column(db.String(10), nullable=False)
    is_document = db.Column(db.Boolean, nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)
    user = db.relationship('User', backref=db.backref('entries', lazy=True))

# Create database
with app.app_context():
    db.create_all()

# Helper function to validate email
def is_valid_email(email):
    return re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email) is not None

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/tracker')
@jwt_required(optional=True)
def tracker():
    current_user = get_jwt_identity()
    return render_template('tracker.html', is_authenticated=bool(current_user))

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'message': 'Email and password are required'}), 400
    if not is_valid_email(email):
        return jsonify({'message': 'Invalid email format'}), 400
    if len(password) < 6:
        return jsonify({'message': 'Password must be at least 6 characters'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'message': 'Email already registered'}), 400

    password_hash = generate_password_hash(password)
    user = User(email=email, password_hash=password_hash)
    db.session.add(user)
    db.session.commit()

    # Convert user.id to string
    access_token = create_access_token(identity=str(user.id))
    return jsonify({'access_token': access_token, 'message': 'Registration successful'}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'message': 'Invalid email or password'}), 401

    # Convert user.id to string
    access_token = create_access_token(identity=str(user.id))
    return jsonify({'access_token': access_token, 'message': 'Login successful'}), 200

@app.route('/api/entries', methods=['GET', 'POST'])
@jwt_required()
def handle_entries():
    user_id = int(get_jwt_identity())
    print(f"GET /api/entries - User ID: {user_id}")
    if request.method == 'GET':
        entries = Entry.query.filter_by(user_id=user_id).all()
        print(f"Found {len(entries)} entries for user {user_id}")
        return jsonify([{
            'id': e.id,
            'type': e.type,
            'description': e.description,
            'cost': e.cost,
            'currency': e.currency,
            'frequency': e.frequency,
            'startDate': e.start_date,
            'endDate': e.end_date,
            'isDocument': e.is_document,
            'transactionType': e.transaction_type
        } for e in entries]), 200
    elif request.method == 'POST':
        try:
            data = request.get_json()
            print("Received POST data:", data)
            required_fields = ['type', 'startDate', 'endDate', 'isDocument', 'transactionType']
            
            # Check for missing required fields
            missing_fields = [field for field in required_fields if field not in data or data[field] is None]
            if missing_fields:
                return jsonify({'message': f'Missing required fields: {", ".join(missing_fields)}'}), 422

            # Validate dates
            try:
                start_date = datetime.strptime(data['startDate'], '%Y-%m-%d')
                end_date = datetime.strptime(data['endDate'], '%Y-%m-%d')
                if start_date >= end_date:
                    return jsonify({'message': 'Start date must be before end date'}), 422
            except ValueError as e:
                print("Date validation error:", str(e))
                return jsonify({'message': 'Invalid date format, expected YYYY-MM-DD'}), 422

            # Validate cost and frequency only for subscriptions
            cost = data.get('cost', '')
            frequency = data.get('frequency', '')
            currency = data.get('currency', '')
            if not data['isDocument']:
                if not cost or not frequency:
                    return jsonify({'message': 'Cost and frequency are required for subscriptions'}), 422
                try:
                    float(cost)
                except ValueError:
                    return jsonify({'message': 'Cost must be a valid number'}), 422
            else:
                cost = ''
                frequency = ''
                currency = ''

            # Validate description for documents
            description = data.get('description', '').strip()
            if data['isDocument'] and not description:
                return jsonify({'message': 'Description is required for documents'}), 422

            # Normalize type and description for duplicate check
            normalized_type = data['type'].lower()
            normalized_description = description.lower()

            # Check for duplicates (case-insensitive)
            existing = Entry.query.filter(
                Entry.user_id == user_id,
                db.func.lower(Entry.type) == normalized_type,
                db.func.lower(Entry.description) == normalized_description,
                Entry.start_date == data['startDate'],
                Entry.end_date == data['endDate']
            ).first()
            if existing:
                return jsonify({'message': 'Duplicate entry exists'}), 422

            print("Creating entry with data:", {
                'user_id': user_id,
                'type': data['type'],
                'description': description,
                'cost': cost,
                'currency': currency,
                'frequency': frequency,
                'start_date': data['startDate'],
                'end_date': data['endDate'],
                'is_document': data['isDocument'],
                'transaction_type': data['transactionType']
            })

            entry = Entry(
                user_id=user_id,
                type=data['type'],
                description=description,
                cost=cost,
                currency=currency,
                frequency=frequency,
                start_date=data['startDate'],
                end_date=data['endDate'],
                is_document=data['isDocument'],
                transaction_type=data['transactionType']
            )
            db.session.add(entry)
            db.session.commit()
            return jsonify({'message': 'Entry added', 'id': entry.id}), 201
        except Exception as e:
            print("Error in /api/entries POST:", str(e))
            return jsonify({'message': f'Server error: {str(e)}'}), 500
            
@app.errorhandler(Exception)
def handle_exception(e):
    print(f"Unhandled error: {str(e)}")  # Debug log
    return jsonify({'message': f'Server error: {str(e)}'}), 500

@app.route('/api/entries/<int:id>', methods=['PUT', 'DELETE'])
@jwt_required()
def handle_entry(id):
    user_id = int(get_jwt_identity())
    entry = Entry.query.filter_by(id=id, user_id=user_id).first()
    if not entry:
        return jsonify({'message': 'Entry not found'}), 404

    if request.method == 'PUT':
        data = request.get_json()
        required_fields = ['type', 'startDate', 'endDate', 'isDocument', 'transactionType']
        if not all(field in data for field in required_fields):
            return jsonify({'message': 'Missing required fields'}), 400

        # Validate dates
        try:
            start_date = datetime.strptime(data['startDate'], '%Y-%m-%d')
            end_date = datetime.strptime(data['endDate'], '%Y-%m-%d')
            if start_date >= end_date:
                return jsonify({'message': 'Start date must be before end date'}), 400
        except ValueError:
            return jsonify({'message': 'Invalid date format'}), 400

        # Validate cost if not a document
        if not data['isDocument']:
            if not data.get('cost') or not data.get('frequency'):
                return jsonify({'message': 'Cost and frequency are required for subscriptions'}), 400
            try:
                float(data['cost'])
            except ValueError:
                return jsonify({'message': 'Invalid cost format'}), 400

        # Normalize type and description for duplicate check
        description = data.get('description', '').strip()
        normalized_type = data['type'].lower()
        normalized_description = description.lower()

        # Check for duplicates (case-insensitive, excluding current entry)
        existing = Entry.query.filter(
            Entry.id != id,
            Entry.user_id == user_id,
            db.func.lower(Entry.type) == normalized_type,
            db.func.lower(Entry.description) == normalized_description,
            Entry.start_date == data['startDate'],
            Entry.end_date == data['endDate']
        ).first()
        if existing:
            return jsonify({'message': 'Duplicate entry exists'}), 400

        entry.type = data['type']
        entry.description = description
        entry.cost = data.get('cost', '')
        entry.currency = data.get('currency', '')
        entry.frequency = data.get('frequency', '')
        entry.start_date = data['startDate']
        entry.end_date = data['endDate']
        entry.is_document = data['isDocument']
        entry.transaction_type = data['transactionType']
        db.session.commit()
        return jsonify({'message': 'Entry updated'}), 200

    elif request.method == 'DELETE':
        db.session.delete(entry)
        db.session.commit()
        return jsonify({'message': 'Entry deleted'}), 200

if __name__ == '__main__':
    app.run(debug=True)