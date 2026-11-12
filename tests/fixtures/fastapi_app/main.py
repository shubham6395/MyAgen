from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Item, User

app = FastAPI(title="Inventory API")


def get_current_user(token: str = "") -> str:
    if not token:
        raise HTTPException(status_code=401, detail="missing token")
    return token


@app.get("/items")
def list_items(db: Session = Depends(get_db)):
    return db.query(Item).all()


@app.post("/items")
def create_item(name: str, db: Session = Depends(get_db)):
    item = Item(name=name)
    db.add(item)
    db.commit()
    return item


@app.get("/items/{item_id}")
def get_item(item_id: int, db: Session = Depends(get_db)):
    return db.query(Item).get(item_id)


@app.put("/items/{item_id}")
def update_item(item_id: int, name: str, db: Session = Depends(get_db)):
    item = db.query(Item).get(item_id)
    item.name = name
    db.commit()
    return item


@app.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).get(item_id)
    db.delete(item)
    db.commit()
    return {"deleted": item_id}


@app.get("/users/me")
def read_me(user: str = Depends(get_current_user)):
    return {"user": user}
