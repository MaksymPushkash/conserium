import enum


class DocumentType(enum.StrEnum):
    PDF = "pdf"
    URL = "url"
    YOUTUBE = "youtube"
    AUDIO = "audio"
    IMAGE = "image"
    TEXT = "text"
    MARKDOWN = "markdown"