from dataclasses import dataclass


@dataclass
class Packet:
    from_token: int
    to_token: int
    text: str
    metadata: str

    @staticmethod
    def deserial(data: dict) -> "Packet":
        return Packet(
            from_token=data["from_token"],
            to_token=data["to_token"],
            text=data["text"],
            metadata=data["metadata"],
        )

    def serial(self) -> dict:
        return {
            "from_token": self.from_token,
            "to_token": self.to_token,
            "text": self.text,
            "metadata": self.metadata,
        }
