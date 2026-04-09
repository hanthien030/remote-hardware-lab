# file: backend/app/routes/auth.py (phiên bản cập nhật)

from flask import Blueprint, request, jsonify, session
from app.services import user_service
from app.auth_decorator import require_auth
from app.logger import log_action
import jwt
from datetime import datetime, timedelta
import os

auth_bp = Blueprint('auth_bp', __name__)

SECRET_KEY = os.getenv('SECRET_KEY', 'default-secret-key')

@auth_bp.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify(ok=False, error="Thiếu username hoặc password"), 400

    if user_service.get_user_by_username(username):
        log_action(username, 'User Register Attempt', success=False, details={'reason': 'Username exists'})
        return jsonify(ok=False, error="Username đã tồn tại"), 409

    email = data.get('email')
    full_name = data.get('full_name')
    success, message = user_service.create_user(username, password, email, full_name)
    
    if success:
        log_action(username, 'User Register', success=True)
        return jsonify(ok=True, message="Đăng ký thành công"), 201
    else:
        log_action(username, 'User Register', success=False, details={'error': message})
        return jsonify(ok=False, error=f"Đăng ký thất bại: {message}"), 500

@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify(ok=False, error="Thiếu username hoặc password"), 400

    user = user_service.get_user_by_username(username)

    if not user or not user_service.check_password(user['password'], password):
        log_action(username, 'User Login Attempt', success=False, details={'reason': 'Invalid credentials'})
        return jsonify(ok=False, message="Sai username hoặc password"), 401

    # Create JWT token
    payload = {
        'user_id': user['id'],
        'username': user['username'],
        'role': user['role'],
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    access_token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')

    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    
    log_action(username, 'User Login', success=True)
    return jsonify(
        ok=True,
        message="Đăng nhập thành công",
        access_token=access_token,
        user={
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'full_name': user['full_name'],
            'role': user['role']
        }
    ), 200

@auth_bp.route('/api/auth/logout', methods=['POST'])
@require_auth()
def logout():
    username = session.get('username')
    session.clear()
    log_action(username, 'User Logout', success=True)
    return jsonify(ok=True, message="Đăng xuất thành công")

@auth_bp.route('/api/auth/profile', methods=['GET'])
@require_auth()
def profile():
    username = session.get('username')
    user = user_service.get_user_by_username(username)
    
    log_action(username, 'View Profile', success=True)
    
    if user:
        return jsonify(
            ok=True,
            user={
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'full_name': user['full_name'],
                'role': user['role']
            }
        )
    return jsonify(ok=False, error="Không tìm thấy thông tin người dùng"), 404
