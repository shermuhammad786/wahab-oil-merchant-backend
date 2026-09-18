from sqlalchemy import text


def create_user(db, name, email, password, age, phone):

    query = text("""
        INSERT INTO users
        (name, email, password, age, phone)
        VALUES
        (:name, :email, :password, :age, :phone)
    """)

    result = db.execute(
        query,
        {
            "name": name,
            "email": email,
            "password": password,
            "age": age,
            "phone": phone
        }
    )

    db.commit()

    return result.lastrowid


def get_all_users(db):

    query = text("""
        SELECT
            id,
            name,
            email,
            age,
            phone,
            is_active,
            created_at,
            updated_at
        FROM users
        ORDER BY id DESC
    """)

    result = db.execute(query)

    return result.mappings().all()


def get_user_by_id(db, user_id):

    query = text("""
        SELECT
            id,
            name,
            email,
            age,
            phone,
            is_active,
            created_at,
            updated_at
        FROM users
        WHERE id = :user_id
    """)

    result = db.execute(
        query,
        {"user_id": user_id}
    )

    return result.mappings().first()


def get_user_by_email(db, email):

    query = text("""
        SELECT
            id,
            name,
            email,
            age,
            phone,
            is_active,
            created_at,
            updated_at
        FROM users
        WHERE email = :email
    """)

    result = db.execute(
        query,
        {"email": email}
    )

    return result.mappings().first()