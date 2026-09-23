"""Server-owned points, purchases and optional room decoration contracts."""

from typing import Annotated, Literal

from pydantic import StringConstraints

from .models import APIModel

RewardSlot = Literal["background", "poster", "plant", "lamp"]
ItemId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class RewardItem(APIModel):
    id: str
    name: str
    description: str
    cost: int
    slot: RewardSlot
    style: str


class RewardTransaction(APIModel):
    id: str
    kind: Literal["project_reward", "purchase"]
    amount: int
    label: str
    createdAt: str
    proposalId: str | None
    itemId: str | None


class RewardEquipment(APIModel):
    background: str | None = None
    poster: str | None = None
    plant: str | None = None
    lamp: str | None = None


class TeamRewards(APIModel):
    teamId: str
    balance: int
    totalEarned: int
    completedProjects: int
    items: list[RewardItem]
    ownedItemIds: list[str]
    equipped: RewardEquipment
    history: list[RewardTransaction]


class RewardPurchaseInput(APIModel):
    itemId: ItemId


class RewardEquipInput(APIModel):
    slot: RewardSlot
    itemId: ItemId | None
