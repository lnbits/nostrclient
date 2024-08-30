from typing import Optional


class Subscription:
    def __init__(self, id: str, filters: Optional[list[str]] = None) -> None:
        self.id = id
        self.filters = filters
