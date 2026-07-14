import time
from datetime import datetime, timezone

import certifi
import streamlit as st
import streamlit_authenticator as stauth
from google import genai
from pymongo import MongoClient
from pymongo.server_api import ServerApi

# ---------------------------------------------------------------------------
# Config / connections
# ---------------------------------------------------------------------------
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
MONGODB_URI = st.secrets["MONGODB_URI"]
COOKIE_KEY = st.secrets["COOKIE_KEY"]  # random secret string, see notes below

mongo_client = MongoClient(
    MONGODB_URI,
    server_api=ServerApi("1"),
    tlsCAFile=certifi.where(),
)
db = mongo_client["LeetCodeAgent"]
problems_collection = db["problems"]
users_collection = db["users"]

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

st.set_page_config(page_title="LeetCode Coach Agent", page_icon="🧠")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def call_gemini(prompt: str, retries: int = 3, delay: int = 3) -> str | None:
    """Call Gemini with retry-on-503. Returns response text, or None on failure."""
    for attempt in range(retries):
        try:
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            return response.text
        except Exception as e:
            if "503" in str(e) and attempt < retries - 1:
                time.sleep(delay)
            else:
                st.error(f"Error: {e}")
                return None
    return None


def load_credentials() -> dict:
    """Build the credentials dict streamlit-authenticator expects, from MongoDB."""
    credentials = {"usernames": {}}
    for u in users_collection.find():
        credentials["usernames"][u["username"]] = {
            "name": u["name"],
            "email": u["email"],
            "password": u["password"],  # already hashed by stauth
        }
    return credentials


def persist_new_user(username: str, user_record: dict) -> None:
    """Write a newly registered user (added in-memory by stauth) to MongoDB."""
    users_collection.insert_one(
        {
            "username": username,
            "name": user_record["name"],
            "email": user_record["email"],
            "password": user_record["password"],
            "created_at": datetime.now(timezone.utc),
        }
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
credentials = load_credentials()

authenticator = stauth.Authenticate(
    credentials,
    cookie_name="leetcode_coach_cookie",
    cookie_key=COOKIE_KEY,
    cookie_expiry_days=30,
)

st.title("LeetCode Coach Agent")

if not st.session_state.get("authentication_status"):
    login_tab, register_tab = st.tabs(["Log in", "Sign up"])

    with login_tab:
        authenticator.login(location="main")
        if st.session_state.get("authentication_status") is False:
            st.error("Username or password is incorrect.")

    with register_tab:
        st.subheader("Create an account")
        try:
            email, username, name = authenticator.register_user(location="main")
            if email:
                persist_new_user(username, credentials["usernames"][username])
                st.success("Account created — switch to the Log in tab to sign in.")
        except Exception as e:
            st.error(str(e))

    st.stop()  # don't render the rest of the app until logged in

# ---------------------------------------------------------------------------
# Everything below only runs for a logged-in user
# ---------------------------------------------------------------------------
username = st.session_state["username"]
name = st.session_state["name"]

with st.sidebar:
    st.write(f"Logged in as **{name}**")
    authenticator.logout("Log out", "sidebar")

if "coaching_response" not in st.session_state:
    st.session_state.coaching_response = None
if "problem_text" not in st.session_state:
    st.session_state.problem_text = ""

st.session_state.problem_text = st.text_input(
    "Enter a LeetCode problem", value=st.session_state.problem_text
)

if st.button("Get Coaching"):
    if not st.session_state.problem_text.strip():
        st.warning("Please enter a LeetCode problem.")
    else:
        with st.spinner("🧠 Analyzing problem and generating coaching tips..."):
            prompt = f"""
You are a LeetCode coach.

Rules:
- Never provide code.
- Never provide the full solution.
- Never ask the user questions.
- Focus on teaching patterns and intuition.

Format your response exactly as:
## Key Concepts
...
## Common Mistakes
...
## Hints
...
## Patterns Involved
...

Problem:
{st.session_state.problem_text}
"""
            st.session_state.coaching_response = call_gemini(prompt)

if st.session_state.coaching_response:
    st.success("Coaching ready!")
    st.markdown(st.session_state.coaching_response)

if st.button("Save Problem"):
    if not st.session_state.problem_text.strip():
        st.warning("Please enter a problem before saving.")
    else:
        problems_collection.insert_one(
            {
                "user_id": username,
                "problem": st.session_state.problem_text,
                "status": "Studied",
                "saved_at": datetime.now(timezone.utc),
            }
        )
        st.success(f"Saved '{st.session_state.problem_text}' to study history!")

st.header("📚 Study History")
history = list(
    problems_collection.find({"user_id": username}).sort("saved_at", -1)
)
if history:
    for doc in history:
        st.markdown(f"• {doc['problem']}")
else:
    st.info("No problems saved yet.")

st.header("📈 Progress Analysis")
if st.button("Analyze My Progress"):
    problem_names = [doc["problem"] for doc in history]
    if not problem_names:
        st.warning("Save some problems first.")
    else:
        history_text = "\n".join(problem_names)
        prompt = f"""
You are an experienced LeetCode mentor.

The student has studied these problems:
{history_text}

Analyze:
1. Common patterns
2. Likely strengths
3. Likely weaknesses
4. Missing topics
5. Overall assessment

Use markdown headings.
"""
        with st.spinner("Analyzing study history..."):
            result = call_gemini(prompt)
            if result:
                st.markdown(result)

st.header("🎯 Next Problem Recommendation")
if st.button("What Should I Solve Next?"):
    problem_names = [doc["problem"] for doc in history]
    if not problem_names:
        st.warning("Save some problems first.")
    else:
        history_text = "\n".join(problem_names)
        prompt = f"""
You are a LeetCode coach.

The student has already studied:
{history_text}

Recommend:
1. One next LeetCode problem
2. Why it is appropriate
3. Concepts it teaches
4. Expected difficulty

Do NOT recommend something already completed.
"""
        with st.spinner("Finding the best next problem..."):
            result = call_gemini(prompt)
            if result:
                st.markdown(result)