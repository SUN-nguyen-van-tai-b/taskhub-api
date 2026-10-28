from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
    )


class PageSchema[ItemT](BaseModel):
    items: list[ItemT]
    total: int
    page: int
    page_size: int
    total_pages: int
