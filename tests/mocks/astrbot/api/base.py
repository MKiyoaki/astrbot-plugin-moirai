import logging

logger = logging.getLogger("astrbot_mock")

class Plain:
    def __init__(self, text: str):
        self.text = text
    def __repr__(self):
        return f"Plain({self.text})"

class AstrMessageEvent:
    pass

class ProviderRequest:
    pass

class ProviderResponse:
    pass

class CommandResult:
    def __init__(self, success: bool = True, message: str = "", **kwargs):
        self.success = success
        self.message = message
