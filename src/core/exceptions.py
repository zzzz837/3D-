"""核心层异常体系"""


class ModelImportError(Exception):
    """3D 模型导入失败。"""


class SchemaValidationError(ValueError):
    """JSON Schema 校验失败。"""


class CellBasketError(Exception):
    """Cell 篮子操作异常。"""
