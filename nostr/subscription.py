from typing import List


class Subscription:
    def __init__(self, id: str, filters: List[str] = None) -> None:
        self.id = id
        self.filters = filters
