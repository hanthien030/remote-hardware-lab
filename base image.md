## Lưu ý compiler service

Base image chứa Arduino CLI + ESP32 toolchain (~11GB) được host tại:
`hanthien030/remote-lab-compiler-base:latest`

Nếu cần rebuild base image từ đầu (ví dụ update Arduino CLI version):
  docker build -f compiler/Dockerfile.base -t hanthien030/remote-lab-compiler-base:latest .
  docker push hanthien030/remote-lab-compiler-base:latest