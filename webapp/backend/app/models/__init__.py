"""ORM model package.

Importing this package ensures that all model classes are registered with
the SQLAlchemy mapper.  Any module that needs ``Base.metadata`` (e.g.
``alembic/env.py`` for autogenerate) should import from here so that all
tables are visible before the metadata is inspected.
"""

from app.models.job import Job, JobStatus, ModelArch, PipelineType
from app.models.image_result import ImageResult
from app.models.user import User, UserRole
from app.models.oauth_account import OAuthAccount
from app.models.patient import Patient
from app.models.share_link import ShareLink

__all__ = [
    "Job",
    "JobStatus",
    "ModelArch",
    "PipelineType",
    "ImageResult",
    "User",
    "UserRole",
    "OAuthAccount",
    "Patient",
    "ShareLink",
]
