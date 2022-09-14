"""Sitreps excpetions."""


class SitrepsException(Exception):
    """Sitreps releated exceptions."""


class SitrepsError(SitrepsException):
    """Sitreps related  errors."""


class DownloadFailed(SitrepsException):
    """Raise for fail downloading file."""


class CodeCoverageError(SitrepsException):
    """Exception for code Coverage."""


class IssuesError(SitrepsException):
    """Error in issues jira/bugzilla"""
