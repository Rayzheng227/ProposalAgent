class StreamMes:
    def __init__(self, proposal_id: str, step: int, content: str):
        self.proposal_id = proposal_id
        self.step = step
        self.content = content

    def to_dict(self):
        return {
            "proposalId": self.proposal_id,
            "step": self.step,
            "content": self.content
        }