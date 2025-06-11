import yaml
import os

class GCF:
    class server:
        ip = "127.0.0.1"
        port = 8000

def load_config(path="config.yaml"):
    if not os.path.isabs(path):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_dir, path)
    with open(path, "r") as f:
        config = yaml.safe_load(f)


    for key, value in config.get("server", {}).items():
        setattr(GCF.server, key, value)
