import yaml

class GCF:
    class server:
        ip = "127.0.0.1"
        port = 8000

def load_config(path="config.yaml"):
    with open(path, "r") as f:
        config = yaml.safe_load(f)

    for key, value in config.get("server", {}).items():
        setattr(GCF.server, key, value)