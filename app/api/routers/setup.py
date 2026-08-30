from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.app_state import AppState

router = APIRouter(prefix="/api/setup", tags=["setup"])


def is_setup_completed(session: Session) -> bool:
    row = session.get(AppState, "setup_completed")
    return row is not None and row.value == "true"


@router.get("/state")
def state(session: Session = Depends(get_session)):
    completed = is_setup_completed(session)
    return {"setup_required": not completed}


@router.post("/complete")
def complete(payload: dict, session: Session = Depends(get_session)):
    # The actual key save happens via settings endpoint.
    # This just flips the flag.
    if not payload.get("acknowledged"):
        return {"ok": False, "error": "must acknowledge"}
    state_row = session.get(AppState, "setup_completed")
    if state_row is None:
        state_row = AppState(key="setup_completed", value="true")
        session.add(state_row)
    else:
        state_row.value = "true"
    session.commit()
    return {"ok": True}