"""Gemini API integration and validated study-material models."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors
from pydantic import BaseModel, Field, ValidationError, field_validator

from modules.prompts import build_study_prompt

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MAX_TRANSCRIPT_CHARACTERS = 30_000
MODEL_NAME = "gemini-3.5-flash-lite"
MAX_GENERATED_TOKENS = 6_000


class StudyMaterialError(Exception):
    """Base error for expected study-material generation failures."""


class InputValidationError(StudyMaterialError):
    """The supplied transcript is empty or outside the supported size."""


class MissingAPIKeyError(StudyMaterialError):
    """Gemini API configuration is missing."""


class RateLimitError(StudyMaterialError):
    """The Gemini API rejected the request due to rate or quota limits."""


class APIAuthenticationError(StudyMaterialError):
    """The configured Gemini API key was rejected."""


class NetworkError(StudyMaterialError):
    """The Gemini API could not be reached."""


class InvalidAIResponseError(StudyMaterialError):
    """The model did not return valid study material."""


class KeyConcept(BaseModel):
    name: str
    explanation: str


class ImportantDefinition(BaseModel):
    term: str
    definition: str
    source_status: Literal[
        "Transcript-supported",
        "Supplementary",
        "Not explained in transcript",
    ]


class NoteSection(BaseModel):
    heading: str
    bullet_points: list[str] = Field(min_length=1, max_length=6)


class QuizQuestion(BaseModel):
    question: str
    options: list[str] = Field(min_length=4, max_length=4)
    correct_option: int = Field(ge=0, le=3)
    explanation: str

    @field_validator("options")
    @classmethod
    def options_must_be_distinct(cls, options: list[str]) -> list[str]:
        if len({option.strip().casefold() for option in options}) != 4:
            raise ValueError("Each quiz question must have four distinct options.")
        return options


class Flashcard(BaseModel):
    question: str
    answer: str


class RevisionSheet(BaseModel):
    essential_facts: list[str] = Field(max_length=8)
    formulas: list[str] = Field(max_length=8)
    definitions: list[str] = Field(max_length=8)
    takeaways: list[str] = Field(max_length=8)
    remember_before_exam: list[str] = Field(max_length=6)


class StudyMaterial(BaseModel):
    summary: str
    key_concepts: list[KeyConcept] = Field(min_length=1, max_length=6)
    definitions: list[ImportantDefinition] = Field(max_length=10)
    organized_notes: list[NoteSection] = Field(min_length=1, max_length=8)
    quiz: list[QuizQuestion] = Field(min_length=5, max_length=5)
    short_answer_questions: list[str] = Field(min_length=5, max_length=5)
    flashcards: list[Flashcard] = Field(min_length=5, max_length=5)
    revision_sheet: RevisionSheet


def validate_transcript(transcript: str) -> str:
    """Return a trimmed transcript or raise a clear input validation error."""
    cleaned = transcript.strip()
    if not cleaned:
        raise InputValidationError("Paste a lecture transcript before generating.")
    if len(cleaned) > MAX_TRANSCRIPT_CHARACTERS:
        raise InputValidationError(
            "The transcript is too long. Please keep it under "
            f"{MAX_TRANSCRIPT_CHARACTERS:,} characters."
        )
    return cleaned


def generate_study_material(
    transcript: str,
    subject: str,
    summary_length: str,
) -> StudyMaterial:
    """Generate and validate study material using the official Gemini SDK."""
    cleaned_transcript = validate_transcript(transcript)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        raise MissingAPIKeyError(
            "Gemini API key is missing. Add GEMINI_API_KEY to your local .env file."
        )

    try:
        client = genai.Client(api_key=api_key)
        interaction = client.interactions.create(
            model=MODEL_NAME,
            input=build_study_prompt(cleaned_transcript, subject, summary_length),
            generation_config={
                "thinking_level": "minimal",
                "max_output_tokens": MAX_GENERATED_TOKENS,
            },
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": StudyMaterial.model_json_schema(),
            },
        )
    except errors.APIError as exc:
        status = getattr(exc, "code", None)
        status_text = str(status).upper()
        if status == 429 or status_text in {
            "RESOURCE_EXHAUSTED",
            "TOO_MANY_REQUESTS",
        }:
            raise RateLimitError(
                "Gemini is receiving too many requests or the API quota is exhausted. "
                "Wait a moment, check your quota, and try again."
            ) from exc
        if status in {401, 403} or status_text in {
            "UNAUTHENTICATED",
            "PERMISSION_DENIED",
        }:
            raise APIAuthenticationError(
                "Gemini rejected the API key. Check that the key is valid and enabled."
            ) from exc
        raise StudyMaterialError(
            f"Gemini could not complete the request: {exc}"
        ) from exc
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise NetworkError(
            "Could not reach Gemini. Check your internet connection and try again."
        ) from exc

    try:
        return StudyMaterial.model_validate_json(interaction.output_text)
    except (ValidationError, AttributeError, TypeError) as exc:
        raise InvalidAIResponseError(
            "Gemini returned an incomplete or malformed response. Please try again."
        ) from exc


def calculate_quiz_score(
    questions: list[QuizQuestion],
    selected_options: list[str | None],
) -> tuple[int, int]:
    """Return the number correct and the number of questions answered."""
    correct = 0
    answered = 0
    for question, selected in zip(questions, selected_options):
        if selected is not None:
            answered += 1
            if selected == question.options[question.correct_option]:
                correct += 1
    return correct, answered


def build_markdown_export(material: StudyMaterial) -> str:
    """Render every generated section as a copy-friendly Markdown document."""
    sections = [
        "# AI Lecture Summarizer — Study Material",
        "## Lecture Summary",
        material.summary,
        "## Organized Notes",
    ]
    for note in material.organized_notes:
        sections.append(f"### {note.heading}")
        sections.extend(f"- {point}" for point in note.bullet_points)

    sections.append("## Key Concepts")
    sections.extend(
        f"- **{concept.name}:** {concept.explanation}"
        for concept in material.key_concepts
    )

    sections.append("## Important Definitions")
    sections.extend(
        f"- **{item.term}** ({item.source_status}): {item.definition}"
        for item in material.definitions
    )

    sections.append("## Multiple-Choice Quiz")
    for number, question in enumerate(material.quiz, start=1):
        sections.append(f"{number}. {question.question}")
        sections.extend(
            f"   - {chr(65 + index)}. {option}"
            for index, option in enumerate(question.options)
        )
        sections.append(
            f"   - Answer: {chr(65 + question.correct_option)}. "
            f"{question.options[question.correct_option]}"
        )
        sections.append(f"   - Explanation: {question.explanation}")

    sections.append("## Short-Answer Revision Questions")
    sections.extend(
        f"{number}. {question}"
        for number, question in enumerate(material.short_answer_questions, start=1)
    )

    sections.append("## Flashcards")
    for number, flashcard in enumerate(material.flashcards, start=1):
        sections.extend(
            [
                f"### Card {number}",
                f"- **Question:** {flashcard.question}",
                f"- **Answer:** {flashcard.answer}",
            ]
        )

    revision = material.revision_sheet
    sections.append("## Revision Sheet")
    for heading, items in (
        ("Essential Facts", revision.essential_facts),
        ("Formulas", revision.formulas),
        ("Definitions", revision.definitions),
        ("Key Takeaways", revision.takeaways),
        ("Remember Before the Exam", revision.remember_before_exam),
    ):
        sections.append(f"### {heading}")
        sections.extend(f"- {item}" for item in items)

    return "\n\n".join(sections)
