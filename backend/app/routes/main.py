# file: backend/app/routes/main.py

from flask import Blueprint, jsonify

# Tạo một Blueprint tên là 'main'
main_bp = Blueprint('main_bp', __name__)

@main_bp.route('/api/healthcheck')
def health_check():
    """Route để kiểm tra xem server có hoạt động không."""
    return jsonify(status="ok", message="Backend is running!")