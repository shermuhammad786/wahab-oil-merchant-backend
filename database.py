from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL="mysql+pymysql://leositso_shafqat_kazmi:kazmiLeos@144.76.111.139:3306/leositso_wahab_oil_merchant"
engine = create_engine(
    DATABASE_URL,
    echo=True
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()