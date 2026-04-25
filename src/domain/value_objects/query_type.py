import enum


class QueryType(enum.StrEnum):
    SEARCH = "search"
    SUMMARY = "summary"
    DUPLICATE_CHECK = "duplicate_check"