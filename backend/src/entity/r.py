class R:
    """
        统一前端回复类
    """

    def __init__(self):
        self.code: int = 0
        self.mes: str = ""
        self.data = None

    @staticmethod
    def ok():
        r = R()
        r.code = 200
        r.mes = "success"
        return r

    @staticmethod
    def error():
        r = R()
        r.code = 400
        r.mes = "fail"
        return r

    @staticmethod
    def error_with_mes(mes: str):
        r = R()
        r.code = 500
        r.mes = mes
        return r

    @staticmethod
    def error_with_data(mes: str, data):
        r = R()
        r.code = 500
        r.mes = mes
        r.data = data
        return r

    @staticmethod
    def ok_with_mes(mes: str):
        r = R()
        r.code = 200
        r.mes = mes
        return r

    @staticmethod
    def ok_with_data(data):
        r = R()
        r.code = 200
        r.mes = "success"
        r.data = data
        return r

    @staticmethod
    def ok_with_mes_data(mes: str, data):
        r = R()
        r.code = 200
        r.mes = mes
        r.data = data
        return r

    def to_dict(self):
        return {
            'code': self.code,
            'mes': self.mes,
            'data': self.data
        }
