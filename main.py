import subprocess
import sys
import os
import signal
import time

def main():
    print(" Starting Veritas Lens (Local Mode)      ")

    # Ensure PYTHONPATH includes the root directory so 'ingestion' is resolvable
    env = os.environ.copy()
    project_root = os.path.abspath(".")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{project_root}:{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = project_root

    # 1. Initialize Database
    print("[1/3] Initializing Database (PostgreSQL + pgvector)...")
    try:
        subprocess.run([sys.executable, "-m", "ingestion.models.database"], env=env, check=True)
    except subprocess.CalledProcessError:
        print("\nFailed to initialize database.")
        print("Please ensure PostgreSQL is running and you have run ./setup_local_infra.sh")
        sys.exit(1)

    print("\n[2/3] Starting Celery Worker (Background tasks & Embeddings)...")
    worker_process = subprocess.Popen(
        [sys.executable, "-m", "celery", "-A", "ingestion.main.celery_app", "worker", "--loglevel=info"],
        env=env
    )

    # Small delay to let worker boot
    time.sleep(3)

    print("\n[3/3] Starting Celery Beat Scheduler (RSS feed polling)...")
    beat_process = subprocess.Popen(
        [sys.executable, "-m", "celery", "-A", "ingestion.main.celery_app", "beat", "--loglevel=info"],
        env=env
    )

    def signal_handler(sig, frame):
        print("\nShutting down Veritas Lens...")
        worker_process.terminate()
        beat_process.terminate()
        worker_process.wait()
        beat_process.wait()
        print("Shutdown complete. Goodbye!")
        sys.exit(0)

    # Catch Ctrl+C and termination signals to shut down child processes gracefully
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("\nVeritas Lens is now running. Press Ctrl+C to exit.")
    
    # Wait for processes to exit
    try:
        worker_process.wait()
        beat_process.wait()
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)

if __name__ == "__main__":
    main()
