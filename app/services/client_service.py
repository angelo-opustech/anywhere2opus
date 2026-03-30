from typing import List, Optional, Tuple

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.client import Client
from app.schemas.client import ClientCreate, ClientUpdate

logger = structlog.get_logger(__name__)


class DuplicateClientNameError(ValueError):
    pass


class ClientService:
    def __init__(self, db: Session):
        self.db = db

    def _normalize_name(self, name: str) -> str:
        return name.strip()

    def _find_by_normalized_name(
        self, name: str, exclude_client_id: Optional[int] = None
    ) -> Optional[Client]:
        normalized_name = self._normalize_name(name)
        query = self.db.query(Client).filter(
            func.lower(func.trim(Client.name)) == normalized_name.lower()
        )
        if exclude_client_id is not None:
            query = query.filter(Client.id != exclude_client_id)
        return query.first()

    def list_clients(
        self, skip: int = 0, limit: int = 200
    ) -> Tuple[List[Client], int]:
        query = self.db.query(Client).order_by(Client.name)
        total = query.count()
        return query.offset(skip).limit(limit).all(), total

    def get_client(self, client_id: int) -> Optional[Client]:
        return self.db.query(Client).filter(Client.id == client_id).first()

    def get_client_or_raise(self, client_id: int) -> Client:
        client = self.get_client(client_id)
        if client is None:
            raise ValueError(f"Client {client_id} not found")
        return client

    def create_client(self, data: ClientCreate) -> Client:
        normalized_name = self._normalize_name(data.name)
        if self._find_by_normalized_name(normalized_name) is not None:
            raise DuplicateClientNameError(
                f"Client name '{normalized_name}' already exists"
            )

        client = Client(name=normalized_name, description=data.description)
        self.db.add(client)
        self.db.commit()
        self.db.refresh(client)
        logger.info("client_created", client_id=client.id, name=client.name)
        return client

    def update_client(self, client_id: int, data: ClientUpdate) -> Client:
        client = self.get_client_or_raise(client_id)
        if data.name is not None:
            normalized_name = self._normalize_name(data.name)
            if self._find_by_normalized_name(normalized_name, exclude_client_id=client_id) is not None:
                raise DuplicateClientNameError(
                    f"Client name '{normalized_name}' already exists"
                )
            client.name = normalized_name
        if data.description is not None:
            client.description = data.description
        self.db.commit()
        self.db.refresh(client)
        logger.info("client_updated", client_id=client_id)
        return client

    def delete_client(self, client_id: int) -> None:
        client = self.get_client_or_raise(client_id)
        self.db.delete(client)
        self.db.commit()
        logger.info("client_deleted", client_id=client_id)
