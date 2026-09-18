from fastapi import FastAPI

from routers.users import router as users_router
from routers.products import router as products_router


app = FastAPI(
    title="FastAPI MySQL API",
    description="FastAPI API using XAMPP MySQL",
    version="1.0.0"
)


app.include_router(users_router)

app.include_router(products_router)


@app.get("/")
def home():

    return {
        "message": "FastAPI is running"
    }