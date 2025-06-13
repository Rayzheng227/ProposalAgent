import yaml
import os


class ServerConfig:
    """
    服务器配置
    """

    def __init__(self, load_config: bool = True):
        if load_config:
            self.load_config()
        else:
            self.ip = "127.0.0.1"
            self.port = 8000

    def load_config(self, config_path: str = os.path.join(os.path.dirname(__file__), "../../resource/config.yaml")):
        """
        加载配置文件
        """
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        server_config = config.get("server", {})
        for key, value in server_config.items():
            setattr(self, key, value)
