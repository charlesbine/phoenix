"""
Simple HTTP server for serving data preprocessed by the python code
to be read by the starlark code. Config for this server is in 
main_config.toml under the [server] heading
"""

from pathlib import Path
import subprocess
from typing import Optional

import tomli


def run_server(background: bool = False) -> Optional[subprocess.Popen]:
    root = Path(__file__).parent
    config_file = root / "main_config.toml"
    config = tomli.loads(config_file.read_text())["server"]

    host = config["hostname"]
    port = config["port"]
    directory = root / config["directory"]

    args = ["python", "-m", "http.server", str(port), "--directory", str(directory), 
            "--bind", host]
    
    if background:
        proc = subprocess.Popen(args)
        return proc
    else:
        subprocess.run(args, check=True)
        return None

if __name__ == "__main__":
    run_server()