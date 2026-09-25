from enum import Enum, auto

class PossibleFailure(Enum):
    # VALIDATION_ERROR = auto()
    PROVIDER_ERROR = auto()
    INPUT_ERROR = auto()
    AUTH_ERROR = auto()

    USER_ERROR = auto()

# Possible status for logging
class Status(Enum):
    PENDING = auto()
    FAILED = auto()
    SUCCESS = auto()
    PROCESSING = auto()