import yaml
import os

class ServerConfig:
    """
    服务器配置
    """

    def __init__(self, load_config: bool = True):
        if load_config:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            yaml_path = os.path.join(current_dir, '..', '..', 'resource', 'config.yaml')
            self.load_config(yaml_path)
        else:
            self.ip = "127.0.0.1"
            self.port = 8000

    def load_config(self, config_path: str):
        """
        加载配置文件
        """
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        server_config = config.get("server", {})
        for key, value in server_config.items():
            setattr(self, key, value)
