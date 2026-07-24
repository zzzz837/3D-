class ModelLoadError(Exception):
    pass


class STPConversionError(ModelLoadError):
    pass


class DecimationError(ModelLoadError):
    pass


class BridgeError(Exception):
    pass
