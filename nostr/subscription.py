class Subscription:
    def __init__(self, id: str, filters: list[str] | None = None) -> None:
        self.id = id
        self.filters = filters
