from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    email = Column(String(100), unique=True)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)

    # Product number / code
    number = Column(String(50), unique=True, index=True, nullable=False)

    # Product name
    name = Column(String(100), nullable=False)

    # Purchase price
    purchase_price = Column(Float, nullable=False)

    # Current stock
    stock = Column(Integer, default=0)

    # Minimum stock level
    minimum_stock = Column(Integer, default=0)

    # Product active or inactive
    active = Column(Boolean, default=True)

    # Bank relationship
    bank_id = Column(Integer, ForeignKey("banks.id"), nullable=True)

    bank = relationship("Bank", back_populates="products")


class Bank(Base):
    __tablename__ = "banks"

    id = Column(Integer, primary_key=True, index=True)

    # Bank name: Meezan, Alfalah, etc.
    name = Column(String(100), unique=True, nullable=False)

    products = relationship("Product", back_populates="bank")
