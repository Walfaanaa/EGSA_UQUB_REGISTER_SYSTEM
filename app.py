
import base64
import io
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st


# ============================================================
# 1. PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="EGSA Digital Equb",
    page_icon="🤝",
    layout="centered",
)

st.title("🤝 EGSA Digital Equb")
st.subheader("Group 3 – Member Registration")

st.markdown(
    """
    Welcome to the EGSA Digital Equb registration platform.

    - **Group capacity:** 10 members
    - **Monthly contribution:** ETB 10,000 per member
    - **Registration:** Open until all 10 positions are filled
    """
)

st.info(
    "This application manages member registration only. "
    "It does not collect, hold, or transfer Equb contributions."
)


# ============================================================
# 2. CONFIGURATION
# ============================================================

CSV_COLUMNS = [
    "member_no",
    "full_name",
    "phone",
    "telegram_username",
    "registered_at",
]

DEFAULT_SETTINGS = {
    "group_name": "EGSA Digital Equb - Group 3",
    "capacity": 10,
    "is_open": True,
}


def get_config():
    """Read GitHub and admin credentials from Streamlit secrets."""

    required = [
        "GITHUB_TOKEN",
        "GITHUB_OWNER",
        "GITHUB_REPO",
        "ADMIN_PASSWORD",
    ]

    missing = [
        key for key in required
        if not st.secrets.get(key)
    ]

    if missing:
        st.error(
            "Missing application secrets: "
            + ", ".join(missing)
        )
        st.info(
            "Configure these values in "
            "Streamlit Cloud → App settings → Secrets, "
            "or in .streamlit/secrets.toml for local testing."
        )
        st.stop()

    return {
        "token": st.secrets["GITHUB_TOKEN"],
        "owner": st.secrets["GITHUB_OWNER"],
        "repo": st.secrets["GITHUB_REPO"],
        "branch": st.secrets.get("GITHUB_BRANCH", "main"),
        "csv_path": st.secrets.get(
            "GITHUB_CSV_PATH",
            "data/equb_members.csv",
        ),
        "settings_path": st.secrets.get(
            "GITHUB_SETTINGS_PATH",
            "data/equb_settings.json",
        ),
        "admin_password": st.secrets["ADMIN_PASSWORD"],
    }


CONFIG = get_config()


# ============================================================
# 3. GITHUB API FUNCTIONS
# ============================================================

class GitHubAPIError(Exception):
    def __init__(self, status_code, message):
        self.status_code = status_code
        super().__init__(message)


def github_headers():
    return {
        "Authorization": f"Bearer {CONFIG['token']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_url(path):
    encoded_path = quote(path, safe="/")

    return (
        f"https://api.github.com/repos/"
        f"{CONFIG['owner']}/{CONFIG['repo']}/contents/"
        f"{encoded_path}"
    )


def github_read_file(path):
    """Read a file from the configured GitHub branch."""

    response = requests.get(
        github_url(path),
        headers=github_headers(),
        params={"ref": CONFIG["branch"]},
        timeout=20,
    )

    if response.status_code == 404:
        return None, None

    if response.status_code != 200:
        raise GitHubAPIError(
            response.status_code,
            response.text,
        )

    result = response.json()
    content = base64.b64decode(
        result["content"]
    ).decode("utf-8")

    return content, result["sha"]


def github_write_file(path, content, sha=None):
    """Create or update a file in GitHub."""

    encoded_content = base64.b64encode(
        content.encode("utf-8")
    ).decode("utf-8")

    payload = {
        "message": f"Update {path} - EGSA Digital Equb",
        "content": encoded_content,
        "branch": CONFIG["branch"],
    }

    if sha:
        payload["sha"] = sha

    response = requests.put(
        github_url(path),
        headers=github_headers(),
        json=payload,
        timeout=30,
    )

    if response.status_code not in (200, 201):
        raise GitHubAPIError(
            response.status_code,
            response.text,
        )

    return response.json()


# ============================================================
# 4. GROUP SETTINGS
# ============================================================

def get_group_settings():
    content, sha = github_read_file(
        CONFIG["settings_path"]
    )

    if not content:
        return DEFAULT_SETTINGS.copy(), sha

    settings = DEFAULT_SETTINGS.copy()
    settings.update(json.loads(content))

    # Keep the capacity fixed at 10 for this group.
    settings["capacity"] = 10

    return settings, sha


def save_group_settings(new_settings):
    """Update group settings, retrying GitHub conflicts."""

    for attempt in range(5):
        _, sha = github_read_file(
            CONFIG["settings_path"]
        )

        try:
            github_write_file(
                CONFIG["settings_path"],
                json.dumps(
                    new_settings,
                    indent=4,
                    ensure_ascii=False,
                ),
                sha,
            )
            return True

        except GitHubAPIError as error:
            if error.status_code in (409, 422):
                time.sleep(1)
                continue
            raise

    raise RuntimeError(
        "Could not update group settings after 5 attempts."
    )


# ============================================================
# 5. MEMBER DATA
# ============================================================

def get_members():
    content, _ = github_read_file(
        CONFIG["csv_path"]
    )

    if not content or not content.strip():
        return pd.DataFrame(columns=CSV_COLUMNS)

    df = pd.read_csv(io.StringIO(content))

    for column in CSV_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    df = df[CSV_COLUMNS]

    return df.fillna("")


def dataframe_to_csv(df):
    return df[CSV_COLUMNS].to_csv(index=False)


# ============================================================
# 6. PHONE NUMBER VALIDATION
# ============================================================

def normalize_phone(phone):
    """
    Convert Ethiopian mobile numbers to a common format.

    Examples:
    0912345678
    +251912345678
    091-234-5678
    """

    phone = re.sub(r"[\s()\-]", "", str(phone))

    if phone.startswith("+251"):
        phone = "0" + phone[4:]

    elif phone.startswith("251"):
        phone = "0" + phone[3:]

    return phone


def valid_phone(phone):
    phone = normalize_phone(phone)

    return bool(
        re.fullmatch(r"0[97]\d{8}", phone)
    )


# ============================================================
# 7. MEMBER REGISTRATION
# ============================================================

def register_member(full_name, phone, telegram_username):
    """
    Register one member in GitHub CSV.

    Re-reads the latest CSV before writing and retries
    common GitHub file conflicts.
    """

    clean_name = " ".join(full_name.strip().split())
    clean_phone = normalize_phone(phone)

    if len(clean_name) < 3:
        return "invalid_name"

    if not valid_phone(clean_phone):
        return "invalid_phone"

    for attempt in range(5):

        settings, _ = get_group_settings()

        current_content, csv_sha = github_read_file(
            CONFIG["csv_path"]
        )

        if current_content and current_content.strip():
            members = pd.read_csv(
                io.StringIO(current_content)
            )

            for column in CSV_COLUMNS:
                if column not in members.columns:
                    members[column] = ""

            members = members[CSV_COLUMNS].fillna("")

        else:
            members = pd.DataFrame(columns=CSV_COLUMNS)

        # Duplicate phone check
        existing_phones = members["phone"].astype(str).apply(
            normalize_phone
        )

        if clean_phone in existing_phones.values:
            return "duplicate"

        # Capacity check
        capacity = 10

        if len(members) >= capacity:
            return "full"

        if not settings.get("is_open", True):
            return "closed"

        member_no = len(members) + 1

        new_member = {
            "member_no": member_no,
            "full_name": clean_name,
            "phone": clean_phone,
            "telegram_username": telegram_username.strip().lstrip("@"),
            "registered_at": datetime.now(
                timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }

        updated_members = pd.concat(
            [
                members,
                pd.DataFrame([new_member]),
            ],
            ignore_index=True,
        )

        try:
            github_write_file(
                CONFIG["csv_path"],
                dataframe_to_csv(updated_members),
                csv_sha,
            )

            # Close registration after the tenth member.
            if len(updated_members) >= capacity:
                try:
                    latest_settings, _ = get_group_settings()
                    latest_settings["is_open"] = False
                    save_group_settings(latest_settings)
                except Exception:
                    # The CSV capacity check still blocks
                    # additional registrations.
                    pass

            return "registered"

        except GitHubAPIError as error:
            if error.status_code in (409, 422):
                time.sleep(1)
                continue
            raise

    raise RuntimeError(
        "Registration could not be saved after 5 attempts. "
        "Please try again."
    )


# ============================================================
# 8. LOAD CURRENT GROUP INFORMATION
# ============================================================

try:
    settings, _ = get_group_settings()
    members = get_members()

except Exception as error:
    st.error("Unable to connect to GitHub storage.")
    st.code(str(error))
    st.stop()


capacity = 10
registered_count = len(members)
remaining = max(capacity - registered_count, 0)
registration_open = (
    settings.get("is_open", True)
    and registered_count < capacity
)


# ============================================================
# 9. PUBLIC REGISTRATION DASHBOARD
# ============================================================

st.divider()

st.subheader("📊 Group Registration Status")

col1, col2, col3 = st.columns(3)

col1.metric(
    "Registered Members",
    f"{registered_count}/{capacity}",
)

col2.metric(
    "Available Positions",
    remaining,
)

col3.metric(
    "Monthly Contribution",
    "ETB 10,000",
)

st.progress(
    min(registered_count / capacity, 1.0)
)

if registration_open:
    st.success("Registration is currently OPEN.")
else:
    st.error("Registration is CLOSED. All available positions may be filled.")


# ============================================================
# 10. REGISTRATION FORM
# ============================================================

st.divider()
st.subheader("📝 Member Registration")

if registration_open:

    with st.form("equb_registration_form"):

        full_name = st.text_input(
            "Full Name *",
            placeholder="Enter your full name",
        )

        phone = st.text_input(
            "Mobile Phone Number *",
            placeholder="09XXXXXXXX or +2519XXXXXXXX",
        )

        telegram_username = st.text_input(
            "Telegram Username",
            placeholder="Enter Telegram username (optional)",
        )

        agree = st.checkbox(
            "I confirm that the information provided is correct."
        )

        submitted = st.form_submit_button(
            "Register Now",
            use_container_width=True,
        )

    if submitted:

        if not full_name.strip() or not phone.strip():
            st.warning(
                "Please enter your full name and phone number."
            )

        elif not agree:
            st.warning(
                "Please confirm your registration information."
            )

        else:
            try:
                result = register_member(
                    full_name,
                    phone,
                    telegram_username,
                )

                if result == "registered":
                    st.success(
                        "Registration completed successfully!"
                    )
                    st.balloons()
                    st.rerun()

                elif result == "duplicate":
                    st.error(
                        "This phone number is already registered."
                    )

                elif result == "full":
                    st.error(
                        "Sorry, all 10 member positions are filled."
                    )
                    st.rerun()

                elif result == "closed":
                    st.error(
                        "Registration is currently closed."
                    )

                elif result == "invalid_phone":
                    st.error(
                        "Invalid Ethiopian mobile number. "
                        "Use 09XXXXXXXX, 07XXXXXXXX, "
                        "or +2519XXXXXXXX / +2517XXXXXXXX."
                    )

                elif result == "invalid_name":
                    st.error(
                        "Please enter a valid full name."
                    )

            except Exception as error:
                st.error(
                    "Registration failed. Please try again."
                )
                st.code(str(error))

else:
    st.warning(
        "Thank you for your interest. "
        "Registration for EGSA Digital Equb Group 3 is closed."
    )


# ============================================================
# 11. ADMIN DASHBOARD
# ============================================================

st.divider()

with st.expander("🔐 Admin Dashboard"):

    st.subheader("Administrator Login")

    if not st.session_state.get("admin_logged_in", False):

        admin_password = st.text_input(
            "Admin Password",
            type="password",
            key="admin_password_input",
        )

        if st.button("Login", use_container_width=True):

            if admin_password == CONFIG["admin_password"]:
                st.session_state["admin_logged_in"] = True
                st.rerun()
            else:
                st.error("Incorrect administrator password.")

    else:

        st.success("Administrator authenticated.")

        if st.button("Refresh Member Records"):
            st.rerun()

        try:
            admin_members = get_members()
            admin_settings, _ = get_group_settings()

            st.subheader("Registered Members")

            st.dataframe(
                admin_members,
                use_container_width=True,
                hide_index=True,
            )

            st.metric(
                "Total Registered Members",
                len(admin_members),
            )

            # CSV download
            csv_data = admin_members.to_csv(
                index=False
            ).encode("utf-8-sig")

            st.download_button(
                "⬇️ Download CSV",
                data=csv_data,
                file_name="EGSA_Equb_Members.csv",
                mime="text/csv",
                use_container_width=True,
            )

            # Excel download
            excel_buffer = io.BytesIO()

            with pd.ExcelWriter(
                excel_buffer,
                engine="openpyxl",
            ) as writer:
                admin_members.to_excel(
                    writer,
                    index=False,
                    sheet_name="Equb Members",
                )

            st.download_button(
                "⬇️ Download Excel",
                data=excel_buffer.getvalue(),
                file_name="EGSA_Equb_Members.xlsx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                use_container_width=True,
            )

            st.subheader("Registration Management")

            if admin_settings.get("is_open", True):
                st.info("Registration is enabled.")
            else:
                st.warning("Registration is disabled.")

            can_reopen = len(admin_members) < capacity

            allow_registration = st.checkbox(
                "Allow new registrations",
                value=(
                    admin_settings.get("is_open", True)
                    and can_reopen
                ),
                disabled=not can_reopen,
            )

            if st.button(
                "Save Registration Settings",
                use_container_width=True,
            ):

                if allow_registration and not can_reopen:
                    st.error(
                        "The group is full. Registration cannot be reopened."
                    )
                else:
                    try:
                        admin_settings["is_open"] = (
                            allow_registration
                        )

                        save_group_settings(admin_settings)

                        st.success(
                            "Registration settings updated."
                        )
                        st.rerun()

                    except Exception as error:
                        st.error(
                            "Could not update registration settings."
                        )
                        st.code(str(error))

        except Exception as error:
            st.error("Could not load admin records.")
            st.code(str(error))

        if st.button("Logout"):
            st.session_state["admin_logged_in"] = False
            st.rerun()


# ============================================================
# 12. FOOTER
# ============================================================

st.divider()

st.caption(
    "EGSA Digital Equb | Group 3 | "
    "Member Registration Management System"
)

st.caption(
    "This platform is for registration and record management only. "
    "Monthly contributions are handled separately by the group."
)
