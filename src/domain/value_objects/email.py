import re
from dataclasses import dataclass
from typing import final

from src.domain.exceptions import InvalidEmailException

_EMAIL_REGEX = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Email:
    
    value: str
    
    def __post_init__(self) -> None:
        if not _EMAIL_REGEX.match(self.value):
            raise InvalidEmailException("Invalid email")
    
    def __str__(self) -> str:
        return self.value