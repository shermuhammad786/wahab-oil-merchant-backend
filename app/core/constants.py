from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"


class Status(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class PaymentMethod(str, Enum):
    CASH = "Cash"
    BANK = "Bank"
    OTHER = "Other"


class StockMovementType(str, Enum):
    MANUAL_IN = "manual_in"
    MANUAL_OUT = "manual_out"
    SALE_OUT = "sale_out"
    SALE_RETURN_IN = "sale_return_in"
    PURCHASE_IN = "purchase_in"
    PURCHASE_RETURN_OUT = "purchase_return_out"


class ExpenseCategory(str, Enum):
    HOME = "Home Expense"
    SHOP = "Shop Expense"
    POCKET = "Pocket Money"


class ExpenseSubtype(str, Enum):
    RENT = "Rent"
    UTILITIES = "Utilities"
    GROCERY = "Grocery"
    MAINTENANCE = "Maintenance"
    MEDICAL = "Medical"
    EDUCATION = "Education"
    SALARY = "Salary"
    TRANSPORT = "Transport"
    LOADING_UNLOADING = "Loading / Unloading"
    MAINTENANCE_REPAIR = "Maintenance / Repair"
    OFFICE_SUPPLIES = "Office Supplies"
    MISCELLANEOUS = "Miscellaneous"
    PERSONAL = "Personal"
    TRAVEL = "Travel"
    FOOD = "Food"
    SHOPPING = "Shopping"
    OTHER = "Other"
    OTHER_EXPENSE = "Other Expense"
    EXTRA_EXPENSE = "Extra Expense"


EXPENSE_SUBTYPES = {
    ExpenseCategory.HOME.value: frozenset({"Rent", "Utilities", "Maintenance", "Medical", "Education", "Other Expense", "Extra Expense"}),
    ExpenseCategory.SHOP.value: frozenset({"Salary", "Rent", "Utilities", "Maintenance / Repair", "Other Expense", "Extra Expense"}),
    ExpenseCategory.POCKET.value: frozenset({"Personal", "Travel", "Food", "Shopping", "Other Expense", "Extra Expense"}),
}
