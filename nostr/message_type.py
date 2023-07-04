class ClientMessageType:
    EVENT = "EVENT"
    REQUEST = "REQ"
    CLOSE = "CLOSE"


class RelayMessageType:
    EVENT = "EVENT"
    NOTICE = "NOTICE"
    END_OF_STORED_EVENTS = "EOSE"
    COMMAND_RESULT = "OK"

    @staticmethod
    def is_valid(type: str) -> bool:
        if (
            type == RelayMessageType.EVENT
            or type == RelayMessageType.NOTICE
            or type == RelayMessageType.END_OF_STORED_EVENTS
            or type == RelayMessageType.COMMAND_RESULT
        ):
            return True
        return False
