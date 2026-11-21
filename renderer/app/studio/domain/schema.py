"""Base versionada dos contratos persistidos (``schema_version``), isolada de ``contracts``.

Extraída de ``contracts.py`` para romper o ciclo de importação: o contrato persistido
``Video`` passa a referenciar o ``QaReport`` versionado de ``domain.qa_report`` — que por
sua vez precisa de ``_Model``/``SCHEMA_VERSION``. Com a base num módulo próprio,
``qa_report`` não importa ``contracts`` e ``contracts`` pode importar ``qa_report`` sem
ciclo, em qualquer ordem de importação.
"""
from pydantic import BaseModel, ConfigDict, field_validator

SCHEMA_VERSION = 1


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = SCHEMA_VERSION

    @field_validator("schema_version")
    @classmethod
    def _known_version(cls, value: int) -> int:
        if value != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {value!r}; expected {SCHEMA_VERSION}")
        return value
