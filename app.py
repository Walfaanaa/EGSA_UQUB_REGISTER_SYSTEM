
import re
import io
import json
import base64
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests
import pandas as pd
import streamlit as st


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
# APPLICATION CONFIGURATION
# =====================================================

CAPACITY = 10

CSV_COLUMNS = [
    "member_no",
    "full_name",
    "phone",
    "telegram_username",
    "registered_at"
]


# =====================================================
# GITHUB CONFIGURATION
# =====================================================

def github_config():

    return {
        "token": st.secrets["GITHUB_TOKEN"],
        "owner": st.secrets["GITHUB_OWNER"],
        "repo": st.secrets["GITHUB_REPO"],
        "branch": st.secrets.get("GITHUB_BRANCH", "main"),
        "csv_path": st.secrets.get(
            "GITHUB_CSV_PATH",
            "data/equb_members.csv"
        ),
        "settings_path": st.secrets.get(
            "GITHUB_SETTINGS_PATH",
            "data/equb_settings.json"
        )
    }


def github_headers():

    config = github_config()

    return {
        "Authorization": f"Bearer {config['token']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }


def github_url(path):

    config = github_config()

    encoded_path = quote(path, safe="/")

    return (
        f"https://api.github.com/repos/"
        f"{config['owner']}/{config['repo']}/contents/"
        f"{encoded_path}"
    )


# =====================================================
# READ FILE FROM GITHUB
# =====================================================

def github_read_file(path):

    response = requests.get(
        github_url(path),
        headers=github_headers(),
        params={
            "ref": github_config()["branch"]
        },
        timeout=20
    )

    if response.status_code == 404:
        return None, None

    response.raise_for_status()

    file_data = response.json()

    content = base64.b64decode(
        file_data["content"]
    )

    return content, file_data["sha"]


# =====================================================
# SAVE OR UPDATE FILE ON GITHUB
# =====================================================

def github_write_file(path, content, sha=None):

    config = github_config()

    payload = {
        "message": (
            "EGSA Digital Equb: Update registration records"
        ),
        "content": base64.b64encode(
            content.encode("utf-8")
        ).decode("utf-8"),
        "branch": config["branch"]
    }

    if sha:
        payload["sha"] = sha

    response = requests.put(
        github_url(path),
        headers=github_headers(),
        json=payload,
        timeout=30
    )

    response.raise_for_status()

    return response.json()


# =====================================================
# GROUP SETTINGS
# =====================================================

def get_group():

    path = github_config()["settings_path"]

    content, _ = github_read_file(path)

    if content is None:

        return {
            "group_name": "EGSA Digital Equb - Group 3",
            "capacity": CAPACITY,
            "is_open": True
        }

    settings = json.loads(
        content.decode("utf-8")
    )

    return {
        "group_name": settings.get(
            "group_name",
            "EGSA Digital Equb - Group 3"
        ),
        "capacity": CAPACITY,
        "is_open": settings.get(
            "is_open",
            True
        )
    }


def update_group_status(is_open):

    path = github_config()["settings_path"]

    for attempt in range(5):

        content, sha = github_read_file(path)

        if content is None:

            settings = {
                "group_name": "EGSA Digital Equb - Group 3",
                "capacity": CAPACITY,
                "is_open": is_open
            }

        else:

            settings = json.loads(
                content.decode("utf-8")
            )

            settings["is_open"] = is_open
            settings["capacity"] = CAPACITY

        try:

            github_write_file(
                path,
                json.dumps(
                    settings,
                    indent=4
                ),
                sha
            )

            return True

        except requests.HTTPError as error:

            if (
                error.response is not None
                and error.response.status_code == 409
                and attempt < 4
            ):

                time.sleep(0.5 * (attempt + 1))
                continue

            raise

    raise RuntimeError(
        "Unable to update registration settings."
    )


# =====================================================
# LOAD MEMBERS FROM GITHUB CSV
# =====================================================

def get_members():

    path = github_config()["csv_path"]

    content, _ = github_read_file(path)

    if content is None:
        return []

    df = pd.read_csv(
        io.BytesIO(content),
        dtype=str,
        keep_default_na=False
    )

    for column in CSV_COLUMNS:

        if column not in df.columns:
            df[column] = ""

    df = df[CSV_COLUMNS]

    return df.to_dict("records")


# =====================================================
# REGISTER MEMBER DIRECTLY TO GITHUB
# =====================================================

def register_member(name, phone, telegram):

    path = github_config()["csv_path"]

    for attempt in range(5):

        # Read latest registration settings

        group = get_group()

        if not group["is_open"]:
            return {"status": "closed"}

        # Always read the latest CSV from GitHub

        content, sha = github_read_file(path)

        if content is None:

            df = pd.DataFrame(
                columns=CSV_COLUMNS
            )

        else:

            df = pd.read_csv(
                io.BytesIO(content),
                dtype=str,
                keep_default_na=False
            )

            for column in CSV_COLUMNS:

                if column not in df.columns:
                    df[column] = ""

            df = df[CSV_COLUMNS]

        # Check duplicate phone number

        existing_phones = (
            df["phone"].astype(str).str.strip()
        )

        if phone in existing_phones.values:

            return {"status": "duplicate"}

        # Check maximum capacity

        if len(df) >= CAPACITY:

            return {"status": "full"}

        # Assign next member number

        if df.empty:

            member_no = 1

        else:

            numbers = pd.to_numeric(
                df["member_no"],
                errors="coerce"
            ).dropna()

            member_no = (
                int(numbers.max()) + 1
                if not numbers.empty
                else 1
            )

        if member_no > CAPACITY:

            return {"status": "full"}

        # Create new registration record

        new_member = {
            "member_no": str(member_no),
            "full_name": name,
            "phone": phone,
            "telegram_username": telegram or "",
            "registered_at": datetime.now(
                timezone.utc
            ).isoformat()
        }

        updated_df = pd.concat(
            [
                df,
                pd.DataFrame([new_member])
            ],
            ignore_index=True
        )

        try:

            # Save directly to GitHub

            github_write_file(
                path,
                updated_df.to_csv(index=False),
                sha
            )

            # Close registration when position 10 is filled

            if member_no == CAPACITY:

                try:
                    update_group_status(False)
                except Exception:
                    # Capacity check still prevents further registration.
                    pass

            return {
                "status": "registered",
                "member_no": member_no
            }

        except requests.HTTPError as error:

            # Retry if another registration updated
            # the same CSV file first.

            if (
                error.response is not None
                and error.response.status_code == 409
                and attempt < 4
            ):

                time.sleep(0.5 * (attempt + 1))
                continue

            raise

    raise RuntimeError(
        "Registration could not be saved. "
        "Please try again."
    )


# =====================================================
# PHONE VALIDATION
# =====================================================

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
# LOAD GROUP AND MEMBERS
# =====================================================

try:

    group = get_group()

    members = get_members()

except Exception as error:

    st.error(
        "GitHub storage connection failed."
    )

    st.subheader("Technical error")

    st.code(str(error))

    st.info(
        "Check GitHub token, repository name, "
        "branch name and repository permissions."
    )

    st.stop()


# =====================================================
# CALCULATE MEMBERSHIP STATUS
# =====================================================

registered = len(members)

available = max(
    CAPACITY - registered,
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


# =====================================================
# MEMBERSHIP DASHBOARD
# =====================================================

col1, col2, col3 = st.columns(3)

col1.metric(
    "Registered",
    f"{registered}/{CAPACITY}"
)

col2.metric(
    "Available",
    available
)

col3.metric(
    "Status",
    "OPEN" if registration_open else "CLOSED"
)

st.progress(
    min(registered / CAPACITY, 1.0)
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

            st.error(
                "Please enter your full name."
            )

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

                status = result.get("status")

                if status == "registered":

                    st.success(
                        "Your registration was saved successfully!"
                    )

                    st.balloons()

                    st.subheader(
                        f"Your Member Number: "
                        f"{result['member_no']}"
                    )

                    if result["member_no"] == CAPACITY:

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
                    "Unable to save your registration to GitHub."
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

                st.error(
                    "Incorrect administrator password."
                )

    else:

        st.success(
            "Administrator authenticated."
        )

        try:

            admin_members = get_members()

            st.subheader("Membership Management")

            st.metric(
                "Total Registered Members",
                f"{len(admin_members)} / {CAPACITY}"
            )

            if admin_members:

                df = pd.DataFrame(admin_members)

                df = df.rename(
                    columns={
                        "member_no": "Member Number",
                        "full_name": "Full Name",
                        "phone": "Phone",
                        "telegram_username": "Telegram Username",
                        "registered_at": "Registration Date"
                    }
                )

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

                st.info(
                    "No members registered yet."
                )

            st.divider()

            # REGISTRATION CONTROL

            st.subheader("Registration Control")

            if len(admin_members) >= CAPACITY:

                st.warning(
                    "The group is full. Registration cannot be reopened "
                    "unless the membership records are corrected."
                )

            allow_registration = st.checkbox(
                "Enable Registration",
                value=group["is_open"],
                disabled=(len(admin_members) >= CAPACITY)
            )

            if st.button(
                "Update Registration Status"
            ):

                update_group_status(
                    allow_registration
                )

                st.success(
                    "Registration status updated successfully."
                )

                st.rerun()

        except Exception as error:

            st.error(
                "Unable to load administrator information."
            )

            st.code(str(error))

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
