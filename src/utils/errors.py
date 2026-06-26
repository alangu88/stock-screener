class ScreenerError(Exception):
    pass


class DataFetchError(ScreenerError):
    pass


class UniverseLoadError(ScreenerError):
    pass
