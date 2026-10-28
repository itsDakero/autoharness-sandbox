"- The GPU must have compute capability 5.2 or greater.
- The server must have the official NVIDIA driver installed.
- The installed driver must be >= 545 (it must support CUDA 12.3)."
and "cuda = [
  \"onnxruntime-gpu>=1.27.1,<1.28\", # TODO: last ORT release supporting CUDA 12.2, also need to handle CUDA 13"