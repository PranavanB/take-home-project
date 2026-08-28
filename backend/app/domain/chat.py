from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictChatModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(StrictChatModel):
    message_id: UUID
    role: ChatRole
    content: str = Field(min_length=1, max_length=1_500)


class MatchChatRequest(StrictChatModel):
    match_result_id: UUID
    messages: list[ChatMessage] = Field(min_length=1, max_length=9)

    @model_validator(mode="after")
    def ends_with_one_user_question(self) -> "MatchChatRequest":
        if self.messages[-1].role != ChatRole.USER:
            raise ValueError("The final chat message must be from the user")
        for previous, current in zip(self.messages, self.messages[1:], strict=False):
            if previous.role == current.role:
                raise ValueError("Chat messages must alternate between user and assistant")
        return self


class MatchChatResponse(StrictChatModel):
    match_result_id: UUID
    message: ChatMessage
