
def get_user_by_id_by_email(db, email):

    from sqlalchemy import text

    query = text("""
        SELECT id
        FROM users
        WHERE email = :email
        LIMIT 1
    """)

    result = db.execute(
        query,
        {"email": email}
    )

    return result.mappings().first()