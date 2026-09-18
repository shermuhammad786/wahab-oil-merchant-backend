from sqlalchemy import text


def create_user(db, name, address, phone,type):

    query = text("""
        INSERT INTO users
        (name, address, phone,type)
        VALUES
        (:name, :address, :phone, :type)
    """)

    result = db.execute(
        query,
        {
            "name": name,
            "address": address,
            "phone": phone,
            "type":type
        }
    )

    db.commit()

    return result.lastrowid


def get_all_users(db):

    query = text("""
        SELECT
            id,
            name,
            address,
            phone,
            type,
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
            address,
            phone,
            type,
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


def delete_user_by_id(db, user_id):

    query = text("""
       DELETE FROM users
       WHERE id = :user_id
    """)

    result = db.execute(
        query,
        {"user_id": user_id}
    )
    db.commit()

    return result

def update_user_by_id(
    db,
    user_id,
    name,
    address,
    phone,
    type
):
    query = text("""
        UPDATE users
        SET
            name = :name,
            address = :address,
            phone = :phone,
            type = :type
        WHERE id = :user_id
    """)

    result = db.execute(
        query,
        {
            "user_id": user_id,
            "name": name,
            "address": address,
            "phone": phone,
            "type": type
        }
    )

    print("USER ID:", user_id)
    print("ROWS UPDATED:", result.rowcount)

    db.commit()

    return result.rowcount