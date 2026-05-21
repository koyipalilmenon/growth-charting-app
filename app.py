"""Streamlit app: WHO growth charts (0–24 months) with per-profile data."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from growth import auth, store
from growth.charts import render_chart
from growth.data import DAYS_PER_MONTH

st.set_page_config(page_title="Growth Charts (WHO 0–24mo)", layout="wide")

store.init_db()


# ---------- sign-in / sign-up screen ----------

def _signed_in_profile() -> store.Profile | None:
    pid = st.session_state.get("profile_id")
    if pid is None:
        return None
    p = store.get_profile(pid)
    if p is None:
        # Stale session (e.g. profile was deleted out-of-band).
        st.session_state.pop("profile_id", None)
        return None
    return p


def _render_signin_screen() -> None:
    st.title("Growth Charts — WHO 0–24 months")
    st.write(
        "Sign in to your profile, or create a new one. Your children and "
        "measurements are private to your profile — other users of this app "
        "can't see them, and you can't see theirs."
    )
    tab_signin, tab_create = st.tabs(["Sign in", "Create a new profile"])

    with tab_signin:
        with st.form("signin_form"):
            name = st.text_input("Profile name", key="signin_name")
            passcode = st.text_input("Passcode", type="password", key="signin_pass")
            submitted = st.form_submit_button("Sign in")
            if submitted:
                profile = store.authenticate(name, passcode)
                if profile is None:
                    st.error("Profile not found, or passcode incorrect.")
                else:
                    st.session_state["profile_id"] = profile.id
                    st.rerun()

    with tab_create:
        with st.form("create_form"):
            name = st.text_input("Pick a profile name", key="create_name",
                                 help="Other users won't be able to use the same name.")
            passcode = st.text_input(
                "Pick a passcode", type="password", key="create_pass",
                help=f"At least {auth.MIN_PASSCODE_LENGTH} characters. "
                     "There's no recovery if you forget it.",
            )
            confirm = st.text_input("Confirm passcode", type="password", key="create_pass2")
            submitted = st.form_submit_button("Create profile")
            if submitted:
                if passcode != confirm:
                    st.error("Passcodes don't match.")
                else:
                    try:
                        profile = store.create_profile(name, passcode)
                    except auth.InvalidPasscode as e:
                        st.error(str(e))
                    except ValueError as e:
                        st.error(str(e))
                    else:
                        st.session_state["profile_id"] = profile.id
                        st.success(f"Welcome, {profile.name}.")
                        st.rerun()

    st.caption("Privacy note: passcodes are stored as PBKDF2-SHA256 hashes, "
               "not in plain text. There's no email-based recovery.")


profile = _signed_in_profile()
if profile is None:
    _render_signin_screen()
    st.stop()


# ---------- signed-in app ----------

# Sidebar: who you are, child picker, sign out.
with st.sidebar:
    st.markdown(f"**Signed in as:** {profile.name}")
    if st.button("Sign out"):
        st.session_state.pop("profile_id", None)
        st.rerun()

    st.divider()
    st.header("Children")

    children = store.list_children(profile.id)
    if children:
        options = {c.id: f"{c.name} ({'M' if c.sex == 'boy' else 'F'}, DOB {c.dob})" for c in children}
        ids = list(options.keys())
        current = st.session_state.get("selected_child_id")
        default_index = ids.index(current) if current in ids else 0
        selected_id = st.selectbox(
            "Select a child",
            ids,
            index=default_index,
            format_func=lambda i: options[i],
        )
        st.session_state["selected_child_id"] = selected_id
    else:
        st.info("No children yet. Add one below to get started.")
        st.session_state.pop("selected_child_id", None)

    with st.expander("Add a new child", expanded=not children):
        with st.form("add_child_form", clear_on_submit=True):
            new_name = st.text_input("Name")
            new_sex = st.selectbox("Sex", ["boy", "girl"],
                                   format_func=lambda s: "Boy" if s == "boy" else "Girl")
            new_dob = st.date_input(
                "Date of birth",
                value=date.today() - timedelta(days=180),
                min_value=date.today() - timedelta(days=365 * 3),
                max_value=date.today(),
            )
            submitted = st.form_submit_button("Add child")
            if submitted:
                if not new_name.strip():
                    st.error("Name is required.")
                else:
                    new_id = store.add_child(profile.id, new_name.strip(), new_sex, new_dob)
                    st.session_state["selected_child_id"] = new_id
                    st.success(f"Added {new_name}.")
                    st.rerun()

    if children and st.session_state.get("selected_child_id") is not None:
        if st.button("Delete selected child", type="secondary"):
            store.delete_child(st.session_state["selected_child_id"], profile.id)
            st.session_state.pop("selected_child_id", None)
            st.rerun()


child_id = st.session_state.get("selected_child_id")
if child_id is None:
    st.title("Growth Charts — WHO 0–24 months")
    st.write("Add a child in the sidebar to start tracking measurements.")
    st.stop()

child = store.get_child(child_id, profile.id)
if child is None:
    # Selected id no longer belongs to this profile (e.g. deletion in another
    # tab). Clear and rerun.
    st.session_state.pop("selected_child_id", None)
    st.rerun()

age_days_today = (date.today() - child.dob).days
age_months_today = age_days_today / DAYS_PER_MONTH

st.title(child.name)
col_a, col_b, col_c = st.columns(3)
col_a.metric("Sex", "Boy" if child.sex == "boy" else "Girl")
col_b.metric("Date of birth", child.dob.isoformat())
col_c.metric("Age today", f"{age_months_today:.1f} months")

if age_days_today > 730:
    st.warning("This child is older than 24 months — WHO 0–24mo charts only show "
               "measurements taken within that range.")

st.divider()

# Add a measurement
st.subheader("Add a measurement")
with st.form("add_measurement_form", clear_on_submit=True):
    cols = st.columns(4)
    taken_on = cols[0].date_input(
        "Date of measurement",
        value=date.today(),
        min_value=child.dob,
        max_value=date.today(),
    )
    weight_kg = cols[1].number_input("Weight (kg)", min_value=0.0, max_value=30.0,
                                     value=0.0, step=0.01, format="%.2f")
    length_cm = cols[2].number_input("Length (cm)", min_value=0.0, max_value=120.0,
                                     value=0.0, step=0.1, format="%.1f")
    head_circ_cm = cols[3].number_input("Head circumference (cm)", min_value=0.0, max_value=70.0,
                                        value=0.0, step=0.1, format="%.1f")
    sub = st.form_submit_button("Save measurement")
    if sub:
        w = weight_kg if weight_kg > 0 else None
        l = length_cm if length_cm > 0 else None
        h = head_circ_cm if head_circ_cm > 0 else None
        if w is None and l is None and h is None:
            st.error("Enter at least one measurement value.")
        else:
            store.add_measurement(profile.id, child.id, taken_on, w, l, h)
            st.success("Saved.")
            st.rerun()


# Measurement history
measurements = store.list_measurements(profile.id, child.id)
if measurements:
    st.subheader("Measurement history")
    history_rows = []
    for m in measurements:
        age_m = (m.taken_on - child.dob).days / DAYS_PER_MONTH
        history_rows.append({
            "id": m.id,
            "Date": m.taken_on.isoformat(),
            "Age (mo)": round(age_m, 2),
            "Weight (kg)": m.weight_kg,
            "Length (cm)": m.length_cm,
            "Head (cm)": m.head_circ_cm,
        })
    st.dataframe(history_rows, hide_index=True, use_container_width=True)

    with st.expander("Delete an entry"):
        ids = [r["id"] for r in history_rows]
        labels = {r["id"]: f"{r['Date']} (age {r['Age (mo)']} mo)" for r in history_rows}
        to_delete = st.selectbox("Pick an entry to remove",
                                 ids, format_func=lambda i: labels[i],
                                 key="delete_measurement_select")
        if st.button("Delete this entry"):
            store.delete_measurement(profile.id, to_delete)
            st.rerun()


# Charts
st.divider()
st.subheader("Charts")

meas_dicts = [
    {"taken_on": m.taken_on, "weight_kg": m.weight_kg,
     "length_cm": m.length_cm, "head_circ_cm": m.head_circ_cm}
    for m in measurements
]

chart_grid = [
    ("lhfa", "wfa"),
    ("hcfa", "wfl"),
]
for left_ind, right_ind in chart_grid:
    c1, c2 = st.columns(2)
    with c1:
        st.pyplot(render_chart(left_ind, child.sex, child.dob, meas_dicts),
                  use_container_width=True)
    with c2:
        st.pyplot(render_chart(right_ind, child.sex, child.dob, meas_dicts),
                  use_container_width=True)

st.caption("Reference: WHO Child Growth Standards (z-score expanded tables, "
          "length/height-for-age, weight-for-age, weight-for-length, "
          "head circumference-for-age). LMS interpolation used between published points.")
