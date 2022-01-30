from __future__ import annotations

from nerddiary.core.client.session.session import UserSession

from pydantic import BaseModel


class ChatContext(BaseModel):
    """Context used for chat_data within a single chat"""

    chat_id: int
    username: str | None
    diary_session: UserSession


class MessageContext(BaseModel):
    """Context used for particular message within a single chat."""

    chat_context: ChatContext
    from_callback: bool
    message_id: int


class ActivePollContext(MessageContext):
    poll_name: str
    cancelled: bool = False

    # def __init__(self, **data) -> None:
    #     super().__init__(**data)
    #     self.chat_context.active_messages[self.message_id] = self

    #     if not self.poll_workflow:
    #         self.reset_workflow()

    # def reset_workflow(self) -> None:
    #     self.poll_workflow = BotWorkflow(
    #         self.poll_config, self.chat_context.config  # type:ignore
    #     )

    # def replace_message(self, message_id: int):
    #     if self.message_id != message_id:
    #         self.chat_context.active_messages[message_id] = self
    #         del self.chat_context.active_messages[self.message_id]
    #         self.message_id = message_id
