from typing_extensions import override


class StreamMes:
    def __init__(self, proposal_id: str, content: str, is_finish: bool = False):
        self.proposal_id = proposal_id
        self.content = content
        self.is_finish = is_finish

    def to_dict(self) -> dict:
        pass

class StreamAnswerMes(StreamMes):
    def __init__(self, proposal_id: str, step: int, title: str, content: str, is_finish: bool = False):
        super().__init__(proposal_id, content, is_finish)
        self.step = step
        self.title = title
        self.is_answer = True

    @override
    def to_dict(self):
        return {
            "isAnswer": self.is_answer,
            "proposalId": self.proposal_id,
            "isFinish": self.is_finish,
            "step": self.step,
            "title": self.title,
            "content": self.content
        }


class StreamClarifyMes(StreamMes):

    def __init__(self, proposal_id: str, content: str, is_finish: bool = False):
        super().__init__(proposal_id, content, is_finish)
        self.is_answer = False

    @override
    def to_dict(self):
        return {
            "isAnswer": self.is_answer,
            "proposalId": self.proposal_id,
            "isFinish": self.is_finish,
            "content": self.content
        }