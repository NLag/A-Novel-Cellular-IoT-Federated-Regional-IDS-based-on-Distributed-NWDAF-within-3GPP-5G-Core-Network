# Run model training sequential
import subprocess
import sys
from pathlib import Path

scripts = [
    Path("DL_multiclass_centralize.py"),
    Path("DL_multiclass_regional_models.py"),
    Path("DL_multiclass_federated.py"),
    Path("DL_multiclass_Federated_Distillation.py")
]

for script in scripts:
    print(f"Running {script}...")

    result = subprocess.run(
        [sys.executable, str(script)],
        check=False,
    )

    if result.returncode != 0:
        print(f"{script} failed with exit code {result.returncode}")
        sys.exit(result.returncode)

print("All scripts completed successfully.")