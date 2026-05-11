import enum


class DocumentType(enum.StrEnum):
    PDF = "PDF"
    URL = "URL"
    YOUTUBE = "YOUTUBE"
    IMAGE = "IMAGE"
    TEXT = "TEXT"
    MARKDOWN = "MARKDOWN"
