import time
import uuid
from dataclasses import dataclass, field


@dataclass
class AgentMessage:
    from_agent: str
    to_agent: str
    thread_id: str       # LINE user_id（同一用戶的對話串）
    content: str
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)
