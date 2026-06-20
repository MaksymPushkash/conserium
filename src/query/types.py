import enum


class QueryType(enum.StrEnum):
    SEARCH = "SEARCH"
    SUMMARY = "SUMMARY"
    DUPLICATE_CHECK = "DUPLICATE_CHECK"