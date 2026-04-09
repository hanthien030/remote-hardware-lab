# file: backend/app/services/docker_manager.py

import docker
import logging
import os
from config import Config

# Cấu hình logging
logger = logging.getLogger(__name__)

def create_user_container(username):
    """
    Tạo một container và volume riêng cho người dùng.
    Container này sẽ tồn tại lâu dài để lưu trữ file của người dùng.
    """
    try:
        client = docker.from_env()
        
        container_name = f"remotelab_user_{username}"

        # --- LOGIC MỚI CHO BIND MOUNT ---
        # Tạo đường dẫn thư mục cho user trên máy chủ
        host_user_dir = os.path.join(Config.USER_DATA_ROOT, username)
        os.makedirs(host_user_dir, exist_ok=True)
        # --- KẾT THÚC LOGIC MỚI ---

        # Kiểm tra xem container đã tồn tại chưa
        try:
            client.containers.get(container_name)
            logger.warning(f"Container '{container_name}' đã tồn tại, bỏ qua việc tạo mới.")
            return True, "Container already exists."
        except docker.errors.NotFound:
            # Container chưa tồn tại, tiếp tục xử lý
            pass

        # THAY THẾ LOGIC TẠO VOLUME BẰNG BIND MOUNT
        container = client.containers.run(
            image="python:3.9-slim",
            name=container_name,
            # volumes giờ sẽ là một bind mount
            volumes={host_user_dir: {'bind': '/workspace', 'mode': 'rw'}},
            detach=True,
            restart_policy={"Name": "unless-stopped"},
            command="tail -f /dev/null"
        )
        
        logger.info(f"Đã tạo thành công container '{container_name}' (ID: {container.id}) cho user '{username}'.")
        return True, container.id

    except docker.errors.APIError as e:
        logger.error(f"Lỗi Docker API khi tạo container cho user '{username}': {e}")
        return False, str(e)
    except Exception as e:
        logger.error(f"Lỗi không xác định khi tạo container cho user '{username}': {e}")
        return False, str(e)

def delete_user_container(username):
    """
    Dừng và xoá container của user.
    Trả về (True, message) nếu thành công hoặc container không tồn tại.
    Trả về (False, error) nếu có lỗi Docker thực sự.
    """
    try:
        client = docker.from_env()
        container_name = f"remotelab_user_{username}"

        try:
            container = client.containers.get(container_name)
            container.stop(timeout=5)
            container.remove(force=True)
            logger.info(f"Đã xoá container '{container_name}' của user '{username}'.")
            return True, f"Container {container_name} deleted."
        except docker.errors.NotFound:
            # Container không tồn tại → coi như đã xoá, không phải lỗi
            logger.warning(f"Container '{container_name}' không tồn tại, bỏ qua.")
            return True, "Container not found, skipped."

    except docker.errors.APIError as e:
        logger.error(f"Lỗi Docker API khi xoá container của user '{username}': {e}")
        return False, str(e)
    except Exception as e:
        logger.error(f"Lỗi không xác định khi xoá container của user '{username}': {e}")
        return False, str(e)
