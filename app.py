
import re
import io
import pandas as pd
import streamlit as st
from supabase import create_client


# =====================================================
# PAGE CONFIGURATION
# =====================================================

st.set_page_config(
    page_title="EGSA Digital Equb",
    page_icon="🤝",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
.main .block-container {
    max-width: 850px;
    padding-top: 2rem;
}
.hero {
    padding: 22px;
    border-radius: 14px;
    background: rgba(120,120,120,0.10);
    margin-bottom: 15px;
}
.stButton button {
    border-radius: 9px;
    min-height: 45px;
}
</style>
""", unsafe_allow_html=True)


# =====================================================
# DATABASE CONNECTION
# =====================================================

@st.cache_resource
def get_public_db():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_ANON_KEY"]
    )


@st.cache_resource
def get_admin_db():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
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

    return response.data[0] if response.data else None


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


def normalize_phone(phone):

    return re.sub(
        r"[\s()\-]",
        "",
        phone.strip()
    )


def valid_phone(phone):

    return bool(
        re.fullmatch(
            r"(09|07)\d{8}|\+251(9|7)\d{8}",
            phone
        )
    )


# =====================================================
# LOAD GROUP INFORMATION
# =====================================================

try:

    group = get_group()

    if not group:
        st.error("No Equb group configured.")
        st.stop()

    members = get_members(group["id"])

except Exception as error:

    st.error(
        "Database connection failed. "
        "Please check your Supabase configuration."
    )

    st.caption(str(error))
    st.stop()


# =====================================================
# CALCULATE MEMBERSHIP STATUS
# =====================================================

capacity = 10

registered = len(members)

available = max(
    capacity - registered,
    0
)

registration_open = (
    group["is_open"] and available > 0
)


# =====================================================
# PUBLIC REGISTRATION PAGE
# =====================================================

st.title("🤝 EGSA DIGITAL EQUB")

st.caption(
    "Official EGSA Digital Equb Membership Registration"
)

st.markdown(
    f"""
    <div class="hero">
        <h2>{group['group_name']}</h2>
        <h3>ETB 10,000 / Month</h3>
        <p>Limited membership: Exactly 10 people</p>
    </div>
    """,
    unsafe_allow_html=True
)


# Membership dashboard

col1, col2, col3 = st.columns(3)

col1.metric(
    "Registered",
    f"{registered}/10"
)

col2.metric(
    "Available",
    available
)

col3.metric(
    "Status",
    "OPEN" if registration_open else "CLOSED"
)


# Progress bar

st.progress(
    min(registered / capacity, 1.0)
)

st.caption(
    f"{registered} members registered. "
    f"{available} positions remaining."
)

st.divider()


# =====================================================
# REGISTRATION FORM
# =====================================================

if registration_open:

    st.success("Registration is OPEN")

    st.subheader("Register Your Membership")

    with st.form(
        "equb_registration",
        clear_on_submit=True
    ):

        full_name = st.text_input(
            "Full Name *",
            placeholder="Enter your full name"
        )

        phone = st.text_input(
            "Mobile Phone Number *",
            placeholder="0912345678"
        )

        telegram = st.text_input(
            "Telegram Username",
            placeholder="@username (optional)"
        )

        confirmation = st.checkbox(
            "I confirm that my information is correct "
            "and I agree to participate in EGSA Digital Equb."
        )

        submitted = st.form_submit_button(
            "REGISTER NOW",
            type="primary",
            use_container_width=True
        )

    if submitted:

        phone = normalize_phone(phone)

        if not full_name.strip():

            st.error("Please enter your full name.")

        elif not valid_phone(phone):

            st.error(
                "Please enter a valid Ethiopian phone number."
            )

        elif not confirmation:

            st.warning(
                "Please confirm your participation."
            )

        else:

            try:

                result = register_member(
                    full_name.strip(),
                    phone,
                    telegram.strip()
                )

                if isinstance(result, list):
                    result = result[0]

                status = result.get("status")

                if status == "registered":

                    st.success(
                        "Your registration was successful!"
                    )

                    st.balloons()

                    st.subheader(
                        f"Your Member Number: "
                        f"{result['member_no']}"
                    )

                    if result["member_no"] == 10:

                        st.warning(
                            "All 10 positions are now filled. "
                            "Registration is closed."
                        )

                    st.rerun()

                elif status == "duplicate":

                    st.warning(
                        "This phone number is already registered."
                    )

                elif status == "full":

                    st.error(
                        "Registration closed. "
                        "All 10 positions have been filled."
                    )

                elif status == "closed":

                    st.error(
                        "Registration is currently closed."
                    )

                else:

                    st.error(
                        f"Registration unsuccessful: {status}"
                    )

            except Exception as error:

                st.error(
                    "Unable to complete registration. "
                    "Please try again."
                )

                st.caption(str(error))


# =====================================================
# CLOSED REGISTRATION MESSAGE
# =====================================================

else:

    st.error("🔒 REGISTRATION CLOSED")

    st.subheader(
        "All membership positions are unavailable."
    )

    st.info(
        "Thank you for your interest in EGSA Digital Equb. "
        "Please contact the Equb administrator for "
        "information about future registration."
    )


# =====================================================
# ADMINISTRATOR DASHBOARD
# =====================================================

st.divider()

with st.expander("🔐 Administrator Login"):

    if not st.session_state.get(
        "admin_logged_in",
        False
    ):

        password = st.text_input(
            "Administrator Password",
            type="password"
        )

        if st.button("Login"):

            if password == st.secrets["ADMIN_PASSWORD"]:

                st.session_state["admin_logged_in"] = True

                st.rerun()

            else:

                st.error("Incorrect administrator password.")

    else:

        st.success("Administrator authenticated.")

        admin_members = get_members(group["id"])

        st.subheader("Membership Management")

        st.metric(
            "Total Registered Members",
            f"{len(admin_members)} / 10"
        )

        if admin_members:

            df = pd.DataFrame(admin_members)

            df.columns = [
                "Member Number",
                "Full Name",
                "Phone",
                "Telegram Username",
                "Registration Date"
            ]

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True
            )

            # CSV EXPORT

            csv_data = df.to_csv(
                index=False
            ).encode("utf-8-sig")

            st.download_button(
                "📥 Download CSV",
                data=csv_data,
                file_name="EGSA_Equb_Members.csv",
                mime="text/csv"
            )

            # EXCEL EXPORT

            excel_buffer = io.BytesIO()

            with pd.ExcelWriter(
                excel_buffer,
                engine="openpyxl"
            ) as writer:

                df.to_excel(
                    writer,
                    index=False,
                    sheet_name="Members"
                )

            st.download_button(
                "📊 Download Excel",
                data=excel_buffer.getvalue(),
                file_name="EGSA_Equb_Members.xlsx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                )
            )

        else:

            st.info("No members registered yet.")

        st.divider()

        # ADMIN REGISTRATION CONTROL

        st.subheader("Registration Control")

        allow_registration = st.checkbox(
            "Enable Registration",
            value=group["is_open"]
        )

        if st.button("Update Registration Status"):

            get_admin_db().table(
                "equb_groups"
            ).update(
                {
                    "is_open": allow_registration
                }
            ).eq(
                "id",
                group["id"]
            ).execute()

            st.success("Registration status updated.")

            st.rerun()

        if st.button("Logout"):

            st.session_state["admin_logged_in"] = False

            st.rerun()


# =====================================================
# FOOTER
# =====================================================

st.divider()

st.caption(
    "EGSA Digital Equb | Membership Registration Portal"
)

st.caption(
    "This application manages registrations only. "
    "It does not collect or transfer Equb contributions."
)
