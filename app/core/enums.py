from enum import StrEnum


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class UserRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class WorkspaceRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"
