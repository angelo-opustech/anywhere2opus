from typing import List, Optional, Tuple

import structlog
from sqlalchemy.orm import Session

from app.models.client import Client
from app.schemas.client import ClientCreate, ClientUpdate

logger = structlog.get_logger(__name__)


class ClientService:
    def __init__(self, db: Session):
        self.db = db

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
        client = Client(name=data.name, description=data.description)
        self.db.add(client)
        self.db.commit()
        self.db.refresh(client)
        logger.info("client_created", client_id=client.id, name=client.name)
        return client

    def update_client(self, client_id: int, data: ClientUpdate) -> Client:
        client = self.get_client_or_raise(client_id)
        if data.name is not None:
            client.name = data.name
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
