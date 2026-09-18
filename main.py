from fastapi import FastAPI

from routers.users import router as users_router


app = FastAPI(
    title="FastAPI MySQL API",
    description="FastAPI API using XAMPP MySQL",
    version="1.0.0"
)


app.include_router(users_router)


@app.get("/")
def home():

    return {
        "message": "FastAPI is running"
    }