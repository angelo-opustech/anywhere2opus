from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.client import ClientCreate, ClientList, ClientRead, ClientUpdate
from app.services.client_service import ClientService

router = APIRouter(prefix="/clients", tags=["Clients"])


def _svc(db: Session = Depends(get_db)) -> ClientService:
    return ClientService(db)


@router.get("", response_model=ClientList, summary="List all clients")
def list_clients(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    svc: ClientService = Depends(_svc),
):
    clients, total = svc.list_clients(skip=skip, limit=limit)
    return ClientList(total=total, items=[ClientRead.model_validate(c) for c in clients])


@router.post("", response_model=ClientRead, status_code=status.HTTP_201_CREATED,
             summary="Create a client")
def create_client(payload: ClientCreate, svc: ClientService = Depends(_svc)):
    client = svc.create_client(payload)
    return ClientRead.model_validate(client)


@router.get("/{client_id}", response_model=ClientRead, summary="Get a client by ID")
def get_client(client_id: int, svc: ClientService = Depends(_svc)):
    try:
        return ClientRead.model_validate(svc.get_client_or_raise(client_id))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/{client_id}", response_model=ClientRead, summary="Update a client")
def update_client(client_id: int, payload: ClientUpdate, svc: ClientService = Depends(_svc)):
    try:
        return ClientRead.model_validate(svc.update_client(client_id, payload))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete a client and all its providers")
def delete_client(client_id: int, svc: ClientService = Depends(_svc)):
    try:
        svc.delete_client(client_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
