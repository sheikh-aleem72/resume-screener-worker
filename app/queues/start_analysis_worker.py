import os
import subprocess
import sys
from dotenv import load_dotenv


load_dotenv()
# os.environ["HF_HOME"] = "/models/huggingface"
# os.environ["TRANSFORMERS_CACHE"] = "/models/transformers"
# os.environ["TORCH_HOME"] = "/models/torch"

WORKER_COUNT = int(os.getenv("ANALYSIS_WORKER_COUNT", "1"))

PYTHON_EXECUTABLE = sys.executable

print(f"🧠 Using Python executable: {PYTHON_EXECUTABLE}")
print(f"🧠 Starting {WORKER_COUNT} Analysis workers...")

processes = []

for i in range(WORKER_COUNT):
    print(f"👷 Launching analysis worker #{i+1}")
    p = subprocess.Popen(
        [PYTHON_EXECUTABLE, "-m", "app.queues.analysis_worker"]
    )
    processes.append(p)

print("Analysis workers started. Press CTRL+C to terminate.")

try:
    for p in processes:
        p.wait()
except KeyboardInterrupt:
    print("\n🛑 Stopping analysis workers...")
    for p in processes:
        p.terminate()
