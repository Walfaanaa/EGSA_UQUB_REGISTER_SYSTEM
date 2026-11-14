
# =====================================================
# DATABASE CONNECTION
# =====================================================

@st.cache_resource
def get_public_db():
    return create_client(
        st.secrets["SUPABASE_URL"].strip(),
        st.secrets["SUPABASE_ANON_KEY"].strip()
    )


@st.cache_resource
def get_admin_db():
    return create_client(
        st.secrets["SUPABASE_URL"].strip(),
        st.secrets["SUPABASE_SERVICE_ROLE_KEY"].strip()
    )


# =====================================================
# DATABASE FUNCTIONS
# =====================================================

def get_group():

    response = (
        get_admin_db()
        .table("equb_groups")
        .select("*")
        .eq("is_default", True)
        .limit(1)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]


def get_members(group_id):

    response = (
        get_admin_db()
        .table("equb_members")
        .select(
            "member_no,full_name,phone,"
            "telegram_username,registered_at"
        )
        .eq("group_id", group_id)
        .order("member_no")
        .execute()
    )

    return response.data or []


def register_member(name, phone, telegram):

    response = get_public_db().rpc(
        "register_equb_member",
        {
            "p_full_name": name,
            "p_phone": phone,
            "p_telegram_username": telegram or None
        }
    ).execute()

    return response.data


# =====================================================
# LOAD GROUP INFORMATION
# =====================================================

try:

    group = get_group()

    if not group:
        st.error("No default Equb group found.")
        st.stop()

    members = get_members(group["id"])

except Exception as error:

    st.error("Supabase database connection failed.")

    st.subheader("Technical error")

    st.code(str(error))

    st.info(
        "Check your Supabase URL, API keys, "
        "database tables and SQL configuration."
    )

    st.stop()
