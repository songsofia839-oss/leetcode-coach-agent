import streamlit as st
from google import genai
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import certifi
import time
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MONGODB_URI = os.getenv("MONGODB_URI")

mongo_client = MongoClient(
    MONGODB_URI,
    server_api=ServerApi('1'),
    tlsCAFile=certifi.where()
)

db = mongo_client["LeetCodeAgent"]
problems_collection = db["problems"]


client = genai.Client(
    api_key=GEMINI_API_KEY
)

st.title("LeetCode Coach Agent")

problem = st.text_input(
    "Enter a LeetCode problem"
)

if st.button("Get Coaching"):

    if not problem.strip():
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
            {problem}
            """

            response = None

            for attempt in range(3):
                try:
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt
                    )
                    break

                except Exception as e:
                    if "503" in str(e):
                        time.sleep(3)
                    else:
                        st.error(f"Error: {e}")
                        break

            if response:
                st.success("Coaching ready!")
                st.markdown(response.text)

            else:
                st.error(
                    "Gemini is currently experiencing high demand. Please try again in a moment."
                )

if st.button("Save Problem"):

    if not problem.strip():
        st.warning("Please enter a problem before saving.")
    else:

        problems_collection.insert_one({
            "problem": problem,
            "status": "Studied",
            "saved_at": datetime.utcnow()
        })

        st.success(f"Saved '{problem}' to study history!")

st.header("📚 Study History")

history = list(
    problems_collection.find().sort("saved_at", -1)
)

if history:

    for doc in history:

        st.markdown(
            f"• {doc['problem']}"
        )

else:
    st.info("No problems saved yet.")

st.header("📈 Progress Analysis")
if st.button("Analyze My Progress"):
    history = list(
        problems_collection.find()
    )

    problem_names = [
        doc["problem"]
        for doc in history
    ]
    if not problem_names:
        st.warning(
            "Save some problems first."
        )
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
    with st.spinner(
            "Analyzing study history..."
    ):

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

    st.markdown(response.text)


st.header("🎯 Next Problem Recommendation")
if st.button("What Should I Solve Next?"):
    history = list(
        problems_collection.find()
    )

    problem_names = [
        doc["problem"]
        for doc in history
    ]
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
    with st.spinner(
            "Finding the best next problem..."
    ):
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

    st.markdown(response.text)

