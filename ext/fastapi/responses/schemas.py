from pydantic import BaseModel


class IBaseResponse(BaseModel):
    """
    Base response model for API responses.

    Attributes:
        message (str): A message providing additional information about the response.
    """

    message: str


class IResponse[DataType, MetaType](IBaseResponse):
    """
    Base response model for API responses.

    Attributes:
        message (str): A message providing additional information about the response.
        data (DataType | None): The main data payload of the response, which can be of any type `DataType`.
        metadata (MetaType | None): Additional metadata about the response.
    """

    data: DataType | None = None
    metadata: MetaType | None = None
