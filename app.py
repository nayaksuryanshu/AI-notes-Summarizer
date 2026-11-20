"""Streamlit interface for AI Lecture Summarizer."""

from __future__ import annotations

import hashlib

import streamlit as st

from modules.ai_service import (
    MAX_TRANSCRIPT_CHARACTERS,
    StudyMaterial,
    StudyMaterialError,
    build_markdown_export,
    calculate_quiz_score,
    generate_study_material,
)
from modules.pdf_service import PDFExtractionError, extract_pdf_text

EXAMPLE_TRANSCRIPT = """Today we are introducing binary search, an algorithm for finding a target value in a sorted list. We compare the target with the middle element. If they match, the search is complete. If the target is smaller, we continue in the left half; if it is larger, we continue in the right half. Each comparison removes about half of the remaining elements, so the time complexity is O(log n). Binary search requires the data to be sorted. For example, in the sorted list [2, 5, 8, 12, 16, 23, 38], to find 16 we first check 12, then search the right half and check 23, then check 16. The algorithm uses constant extra space in its iterative form."""

st.set_page_config(
    page_title="AI Lecture Summarizer",
    page_icon="📘",
    layout="wide",
    initial_sidebar_state="auto",
)

st.markdown(
    """
    <style>
    :root {
        --navy: #102a43;
        --blue: #2563a6;
        --pale-blue: #edf5fc;
        --ink: #243b53;
        --muted: #627d98;
    }
    .stApp {
        background: #f5f8fc;
        color: var(--ink);
    }
    [data-testid="stHeader"] { background: rgba(245, 248, 252, 0.9); }
    [data-testid="stSidebar"] {
        background: #102a43;
        color: #f5f8fc;
    }
    [data-testid="stSidebar"] * { color: #f5f8fc; }
    .hero {
        padding: 1.5rem 1.8rem;
        margin: 0.25rem 0 1.2rem;
        border: 1px solid #d9e7f5;
        border-radius: 18px;
        background: linear-gradient(120deg, #ffffff 0%, #edf5fc 100%);
    }
    .hero h1 {
        color: #102a43;
        font-size: clamp(2rem, 3vw, 2.8rem);
        margin: 0 0 .35rem;
        letter-spacing: -0.035em;
    }
    .hero p { color: #486581; font-size: 1.08rem; margin: 0; }
    .metric-card {
        padding: .8rem 1rem;
        border: 1px solid #d9e7f5;
        border-radius: 12px;
        background: white;
        color: #486581;
    }
    .stApp [data-testid="stBaseButton-primary"] {
        background: #1d5f9e;
        border-color: #1d5f9e;
        color: #ffffff;
    }
    .stApp [data-testid="stBaseButton-primary"]:hover {
        background: #164b7e;
        border-color: #164b7e;
    }
    .stApp [data-testid="stBaseButton-secondary"] {
        background: #ffffff;
        border-color: #cbd9e6;
        color: #102a43;
    }
    .stApp [data-testid="stBaseButton-secondary"]:hover {
        background: #edf5fc;
        border-color: #8fb4d8;
        color: #102a43;
    }
    .stApp textarea {
        background-color: #ffffff !important;
        color: #102a43 !important;
        caret-color: #1d5f9e !important;
        -webkit-text-fill-color: #102a43 !important;
        font-size: 1rem !important;
        line-height: 1.6 !important;
    }
    .stApp textarea::placeholder {
        color: #71869b !important;
        -webkit-text-fill-color: #71869b !important;
        opacity: 1;
    }
    [data-testid="stMetric"] {
        padding: .75rem 1rem;
        border: 1px solid #d9e7f5;
        border-radius: 12px;
        background: white;
    }
    @media (max-width: 700px) {
        .hero { padding: 1.2rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "transcript" not in st.session_state:
    st.session_state.transcript = ""
if "study_material" not in st.session_state:
    st.session_state.study_material = None
if "quiz_checked" not in st.session_state:
    st.session_state.quiz_checked = False
if "pdf_uploader_generation" not in st.session_state:
    st.session_state.pdf_uploader_generation = 0
if "pdf_upload_digest" not in st.session_state:
    st.session_state.pdf_upload_digest = None


def clear_interactive_results() -> None:
    st.session_state.quiz_checked = False
    for key in list(st.session_state):
        if key.startswith(("quiz_answer_", "flashcard_revealed_")):
            del st.session_state[key]


def render_list(items: list[str], empty_message: str) -> None:
    if items:
        for item in items:
            st.markdown(f"- {item}")
    else:
        st.caption(empty_message)


with st.sidebar:
    st.markdown("## 📘 Study smarter")
    st.markdown(
        "Turn a lecture transcript into focused revision material, ready to "
        "review or download."
    )
    st.divider()
    st.markdown("### How to use")
    st.markdown(
        "1. Paste your transcript or class notes.\n"
        "2. Choose a subject and summary length.\n"
        "3. Select **Generate study material**.\n"
        "4. Review the sections, quiz yourself, and download your notes."
    )
    st.info(
        "Your transcript is sent to Google Gemini for generation. An internet "
        "connection and a Gemini API key are required."
    )
    st.caption("Input limit: 30,000 characters · No database is used.")

st.markdown(
    """
    <div class="hero">
        <h1>AI Lecture Summarizer</h1>
        <p>Turn lengthy lectures into smart study notes.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

top_col, reset_col = st.columns([5, 1])
with top_col:
    st.markdown("### Start with your lecture")
with reset_col:
    if st.button("Reset", key="reset_button", use_container_width=True):
        st.session_state.transcript = ""
        st.session_state.study_material = None
        st.session_state.pdf_uploader_generation += 1
        st.session_state.pdf_upload_digest = None
        st.session_state.pdf_upload_message = None
        st.session_state.pdf_upload_error = None
        clear_interactive_results()
        st.rerun()

example_col, metric_col = st.columns([1, 3])
with example_col:
    if st.button(
        "✨ Load example transcript",
        key="example_button",
        use_container_width=True,
    ):
        st.session_state.transcript = EXAMPLE_TRANSCRIPT
        st.session_state.study_material = None
        clear_interactive_results()
        st.rerun()

uploaded_pdf = st.file_uploader(
    "Upload lecture notes as a PDF",
    type=["pdf"],
    key=f"pdf_uploader_{st.session_state.pdf_uploader_generation}",
    help="Text-based PDFs up to 20 MB and 100 pages. Scanned PDFs need OCR first.",
)
if uploaded_pdf is not None:
    pdf_bytes = uploaded_pdf.getvalue()
    pdf_digest = hashlib.sha256(pdf_bytes).hexdigest()
    if st.session_state.pdf_upload_digest != pdf_digest:
        st.session_state.pdf_upload_digest = pdf_digest
        st.session_state.pdf_upload_message = None
        st.session_state.pdf_upload_error = None
        try:
            st.session_state.transcript = extract_pdf_text(pdf_bytes)
            st.session_state.study_material = None
            st.session_state.pdf_upload_message = (
                f"Extracted text from **{uploaded_pdf.name}**. You can review or "
                "edit it below before generating."
            )
            clear_interactive_results()
        except PDFExtractionError as exc:
            st.session_state.transcript = ""
            st.session_state.pdf_upload_error = str(exc)
            st.session_state.study_material = None
            clear_interactive_results()
if st.session_state.get("pdf_upload_message"):
    st.success(st.session_state.pdf_upload_message)
if st.session_state.get("pdf_upload_error"):
    st.error(st.session_state.pdf_upload_error)

transcript = st.text_area(
    "Lecture transcript or class notes",
    key="transcript",
    height=340,
    max_chars=MAX_TRANSCRIPT_CHARACTERS,
    placeholder="Paste your lecture transcript or class notes here...",
    help=f"Maximum {MAX_TRANSCRIPT_CHARACTERS:,} characters.",
)
with metric_col:
    word_count = len(transcript.split())
    st.markdown(
        f'<div class="metric-card"><strong>{word_count:,}</strong> approximate '
        f'words &nbsp; · &nbsp; {len(transcript):,} / '
        f'{MAX_TRANSCRIPT_CHARACTERS:,} characters</div>',
        unsafe_allow_html=True,
    )
if len(transcript) > 15_000:
    st.caption(
        "This is a long transcript, so Gemini may need extra time to read it. "
        "For a quicker result, paste only the relevant lecture section."
    )

settings_col, subject_col = st.columns(2)
with settings_col:
    summary_length = st.selectbox(
        "Summary length",
        options=["Short", "Medium", "Detailed"],
        index=1,
    )
with subject_col:
    subject = st.selectbox(
        "Subject",
        options=[
            "Computer Science",
            "Artificial Intelligence",
            "Mathematics",
            "Physics",
            "Business",
            "Other",
        ],
    )

generate_col, hint_col = st.columns([1, 3])
with generate_col:
    generate_clicked = st.button(
        "Generate study material",
        key="generate_button",
        type="primary",
        use_container_width=True,
    )
with hint_col:
    st.caption(
        "Creates a summary, organized notes, concepts, definitions, a quiz, "
        "flashcards, and a revision sheet."
    )

if generate_clicked:
    clear_interactive_results()
    try:
        with st.spinner(
            "Gemini is reading your transcript and building a concise study pack..."
        ):
            st.session_state.study_material = generate_study_material(
                transcript,
                subject,
                summary_length,
            )
        st.success("Your study material is ready.")
    except StudyMaterialError as exc:
        st.session_state.study_material = None
        st.error(str(exc))

material: StudyMaterial | None = st.session_state.study_material


def render_material(study_material: StudyMaterial) -> None:
    tabs = st.tabs(
        [
            "Summary",
            "Organized Notes",
            "Key Concepts",
            "Definitions",
            "Quiz",
            "Flashcards",
            "Revision Sheet",
        ]
    )

    with tabs[0]:
        st.subheader("Lecture summary")
        st.markdown(study_material.summary)
        st.download_button(
            "Download summary (.txt)",
            data=study_material.summary,
            file_name="lecture-summary.txt",
            mime="text/plain",
        )

    with tabs[1]:
        st.subheader("Organized notes")
        for section in study_material.organized_notes:
            st.markdown(f"#### {section.heading}")
            render_list(section.bullet_points, "No notes in this section.")
        st.text_area(
            "Copy-friendly notes",
            value=build_markdown_export(study_material),
            height=250,
            help="Select and copy the formatted study material.",
        )

    with tabs[2]:
        st.subheader("Key concepts")
        for concept in study_material.key_concepts:
            with st.container(border=True):
                st.markdown(f"**{concept.name}**")
                st.write(concept.explanation)

    with tabs[3]:
        st.subheader("Important definitions")
        for definition in study_material.definitions:
            with st.container(border=True):
                st.markdown(f"**{definition.term}**")
                st.write(definition.definition)
                st.caption(f"Source: {definition.source_status}")
        if not study_material.definitions:
            st.info("No important terms were identified in this transcript.")

    with tabs[4]:
        st.subheader("Knowledge check")
        st.caption("Choose an answer for each question, then check your score.")
        with st.form("quiz_form"):
            selected_options: list[str | None] = []
            for number, question in enumerate(study_material.quiz, start=1):
                st.markdown(f"**{number}. {question.question}**")
                selected = st.radio(
                    "Choose one answer",
                    question.options,
                    index=None,
                    key=f"quiz_answer_{number - 1}",
                    label_visibility="collapsed",
                )
                selected_options.append(selected)
            checked = st.form_submit_button(
                "Check my answers",
                key="check_quiz_button",
            )

        if checked:
            st.session_state.quiz_checked = True
        if st.session_state.quiz_checked:
            score, answered = calculate_quiz_score(
                study_material.quiz,
                selected_options,
            )
            st.success(
                f"Score: {score} / {len(study_material.quiz)} "
                f"({answered} answered)"
            )
            for number, (question, selected) in enumerate(
                zip(study_material.quiz, selected_options),
                start=1,
            ):
                correct_answer = question.options[question.correct_option]
                if selected == correct_answer:
                    st.markdown(f"**{number}. Correct.** {question.explanation}")
                else:
                    st.markdown(
                        f"**{number}. Correct answer: {correct_answer}.** "
                        f"{question.explanation}"
                    )

    with tabs[5]:
        st.subheader("Flashcards")
        for number, flashcard in enumerate(study_material.flashcards, start=1):
            with st.container(border=True):
                st.markdown(f"**Card {number} · {flashcard.question}**")
                reveal_key = f"flashcard_revealed_{number - 1}"
                if st.button(
                    "Hide answer" if st.session_state.get(reveal_key) else "Reveal answer",
                    key=f"flashcard_button_{number - 1}",
                ):
                    st.session_state[reveal_key] = not st.session_state.get(
                        reveal_key,
                        False,
                    )
                if st.session_state.get(reveal_key):
                    st.write(flashcard.answer)

    with tabs[6]:
        st.subheader("Final revision sheet")
        revision = study_material.revision_sheet
        for heading, items in (
            ("Essential facts", revision.essential_facts),
            ("Formulas", revision.formulas),
            ("Definitions", revision.definitions),
            ("Key takeaways", revision.takeaways),
            ("Remember before the exam", revision.remember_before_exam),
        ):
            st.markdown(f"#### {heading}")
            render_list(items, "No items were identified in the transcript.")

    st.download_button(
        "Download all study material (.md)",
        data=build_markdown_export(study_material),
        file_name="lecture-study-material.md",
        mime="text/markdown",
        type="primary",
    )


if material is not None:
    st.divider()
    render_material(material)
elif not generate_clicked:
    st.info(
        "Paste a transcript or load the example to get started. Generated "
        "material will appear here."
    )
