# file: backend/app/auth_decorator.py

from functools import wraps
from flask import session, jsonify, request
import jwt
import os

SECRET_KEY = os.getenv('SECRET_KEY', 'default-secret-key')


def _extract_user_from_request():
    """Extract user info from JWT token or session. Returns dict or None."""
    # Check JWT token first (preferred for API clients)
    auth_header = request.headers.get('Authorization')
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0] == 'Bearer':
            try:
                token = parts[1]
                payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
                return {
                    'user_id': payload.get('user_id'),
                    'username': payload.get('username'),
                    'role': payload.get('role', 'user'),
                }
            except jwt.ExpiredSignatureError:
                return 'expired'
            except jwt.InvalidTokenError:
                return 'invalid'

    # Fallback: session
    if 'username' in session:
        return {
            'user_id': session.get('user_id'),
            'username': session.get('username'),
            'role': session.get('role', 'user'),
        }

    return None


def require_auth(f_or_role=None, role=None):
    """
    Flexible decorator — supports:
      @require_auth                    → no parens, defaults role='user'
      @require_auth(role='admin')      → keyword arg
    Injects request.current_user = {'username', 'role', 'user_id'}
    """
    # Determine the effective required role
    effective_role = role or ('user' if not isinstance(f_or_role, str) else f_or_role)

    if callable(f_or_role):
        # Used as @require_auth (no parens) — f_or_role IS the function
        return _make_wrapper(f_or_role, required_role='user')
    else:
        # Used as @require_auth(...) — return a decorator
        def decorator(f):
            return _make_wrapper(f, required_role=effective_role)
        return decorator


def _make_wrapper(f, required_role='user'):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = _extract_user_from_request()

        if user == 'expired':
            return jsonify(ok=False, error="Token hết hạn"), 401
        if user == 'invalid':
            return jsonify(ok=False, error="Token không hợp lệ"), 401
        if not user:
            return jsonify(ok=False, error="Yêu cầu đăng nhập"), 401

        if required_role == 'admin' and user.get('role') != 'admin':
            return jsonify(ok=False, error="Admin access required"), 403

        # Inject into request so route handlers can access it
        request.current_user = user
        # Keep session for backward compat (existing routes use session)
        session['user_id'] = user['user_id']
        session['username'] = user['username']
        session['role'] = user['role']

        return f(*args, **kwargs)
    return decorated_function
