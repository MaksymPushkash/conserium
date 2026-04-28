import enum


class DocumentType(enum.StrEnum):
    PDF = "PDF"
    URL = "URL"
    YOUTUBE = "YOUTUBE"
    AUDIO = "AUDIO"
    IMAGE = "IMAGE"
    TEXT = "TEXT"
    MARKDOWN = "MARKDOWN"