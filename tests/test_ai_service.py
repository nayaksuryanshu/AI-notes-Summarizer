"""Focused tests for validation, generation, and export behavior."""

from __future__ import annotations

import json
import os
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
from google.genai import errors

from modules.ai_service import (
    MAX_TRANSCRIPT_CHARACTERS,
    APIAuthenticationError,
    InputValidationError,
    InvalidAIResponseError,
    MissingAPIKeyError,
    MAX_GENERATED_TOKENS,
    MODEL_NAME,
    NetworkError,
    RateLimitError,
    StudyMaterial,
    build_markdown_export,
    calculate_quiz_score,
    generate_study_material,
    validate_transcript,
)
from modules.pdf_service import (
    MAX_PDF_BYTES,
    MAX_PDF_PAGES,
    PDFExtractionError,
    extract_pdf_text,
)


def valid_material_payload() -> dict[str, object]:
    quiz = [
        {
            "question": f"Question {number}?",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_option": number % 4,
            "explanation": "The transcript supports this answer.",
        }
        for number in range(5)
    ]
    return {
        "summary": "Binary search finds a value in sorted data by halving each search.",
        "key_concepts": [
            {
                "name": "Binary search",
                "explanation": "It checks the middle value. It then keeps the relevant half.",
            }
        ],
        "definitions": [
            {
                "term": "Time complexity",
                "definition": "A measure described in the transcript.",
                "source_status": "Transcript-supported",
            }
        ],
        "organized_notes": [
            {
                "heading": "Search process",
                "bullet_points": ["Check the middle element.", "Continue in one half."],
            }
        ],
        "quiz": quiz,
        "short_answer_questions": [
            "How does binary search reduce the search area?",
            "Why must the data be sorted?",
            "What value is checked first?",
            "What is the time complexity mentioned?",
            "What extra space does the iterative form use?",
        ],
        "flashcards": [
            {"question": f"Card {number}?", "answer": f"Answer {number}."}
            for number in range(5)
        ],
        "revision_sheet": {
            "essential_facts": ["The input data must be sorted."],
            "formulas": ["Time complexity is O(log n)."],
            "definitions": ["Binary search repeatedly halves the search area."],
            "takeaways": ["Only search the appropriate half."],
            "remember_before_exam": ["Confirm the data is sorted."],
        },
    }


class TranscriptValidationTests(unittest.TestCase):
    def test_strips_valid_transcript(self) -> None:
        self.assertEqual(validate_transcript("  lecture notes  "), "lecture notes")

    def test_rejects_empty_transcript(self) -> None:
        with self.assertRaises(InputValidationError):
            validate_transcript(" \n ")

    def test_rejects_oversized_transcript(self) -> None:
        with self.assertRaises(InputValidationError):
            validate_transcript("x" * (MAX_TRANSCRIPT_CHARACTERS + 1))


class PDFExtractionTests(unittest.TestCase):
    @staticmethod
    def create_text_pdf() -> bytes:
        from pypdf import PdfWriter
        from pypdf.generic import (
            DecodedStreamObject,
            DictionaryObject,
            NameObject,
        )

        writer = PdfWriter()
        page = writer.add_blank_page(width=200, height=200)
        font = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): font}
                )
            }
        )
        content = DecodedStreamObject()
        content.set_data(b"BT /F1 12 Tf 20 100 Td (Lecture PDF text) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(content)
        output = BytesIO()
        writer.write(output)
        return output.getvalue()

    def test_extracts_text_from_a_real_pdf(self) -> None:
        self.assertEqual(extract_pdf_text(self.create_text_pdf()), "Lecture PDF text")

    def test_rejects_empty_or_scanned_pdf(self) -> None:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        output = BytesIO()
        writer.write(output)
        with self.assertRaisesRegex(PDFExtractionError, "No selectable text"):
            extract_pdf_text(output.getvalue())

    def test_rejects_invalid_pdf(self) -> None:
        with self.assertRaises(PDFExtractionError):
            extract_pdf_text(b"not a pdf")

    def test_rejects_pdf_over_file_size_limit(self) -> None:
        with self.assertRaisesRegex(PDFExtractionError, "larger than"):
            extract_pdf_text(b"x" * (MAX_PDF_BYTES + 1))

    def test_rejects_pdf_over_page_limit(self) -> None:
        from pypdf import PdfWriter

        writer = PdfWriter()
        for _ in range(MAX_PDF_PAGES + 1):
            writer.add_blank_page(width=200, height=200)
        output = BytesIO()
        writer.write(output)
        with self.assertRaisesRegex(PDFExtractionError, "more than"):
            extract_pdf_text(output.getvalue())

    def test_rejects_pdf_with_excessive_extracted_text(self) -> None:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        output = BytesIO()
        writer.write(output)
        reader = MagicMock(is_encrypted=False)
        reader.pages = [
            MagicMock(
                extract_text=lambda: "x" * (MAX_TRANSCRIPT_CHARACTERS + 1)
            )
        ]
        with patch(
            "modules.pdf_service.PdfReader",
            return_value=reader,
        ):
            with self.assertRaisesRegex(PDFExtractionError, "30,000 characters"):
                extract_pdf_text(output.getvalue())


class StudyMaterialTests(unittest.TestCase):
    def test_parses_valid_structured_response(self) -> None:
        payload = valid_material_payload()
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
            patch("modules.ai_service.genai.Client") as client_factory,
        ):
            client = client_factory.return_value
            client.interactions.create.return_value.output_text = json.dumps(payload)
            material = generate_study_material(
                "Binary search finds values in sorted data.",
                "Computer Science",
                "Medium",
            )

        self.assertEqual(len(material.quiz), 5)
        self.assertEqual(len(material.flashcards), 5)
        client.interactions.create.assert_called_once()
        request = client.interactions.create.call_args.kwargs
        self.assertEqual(request["model"], MODEL_NAME)
        self.assertEqual(
            request["generation_config"],
            {
                "thinking_level": "minimal",
                "max_output_tokens": MAX_GENERATED_TOKENS,
            },
        )

    def test_missing_key_is_reported(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with self.assertRaises(MissingAPIKeyError):
                generate_study_material("A lecture.", "Other", "Short")

    def test_malformed_response_is_reported(self) -> None:
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
            patch("modules.ai_service.genai.Client") as client_factory,
        ):
            client_factory.return_value.interactions.create.return_value.output_text = (
                '{"summary": "incomplete"}'
            )
            with self.assertRaises(InvalidAIResponseError):
                generate_study_material("A lecture.", "Other", "Short")

    def test_api_rate_limit_is_reported(self) -> None:
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
            patch(
                "modules.ai_service.genai.Client",
                side_effect=errors.APIError(429, {"error": {"message": "quota"}}),
            ),
        ):
            with self.assertRaises(RateLimitError):
                generate_study_material("A lecture.", "Other", "Short")

    def test_rejected_api_key_is_reported(self) -> None:
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
            patch(
                "modules.ai_service.genai.Client",
                side_effect=errors.APIError(403, {"error": {"message": "denied"}}),
            ),
        ):
            with self.assertRaises(APIAuthenticationError):
                generate_study_material("A lecture.", "Other", "Short")

    def test_network_failure_is_reported(self) -> None:
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
            patch(
                "modules.ai_service.genai.Client",
                side_effect=httpx.ConnectError("offline"),
            ),
        ):
            with self.assertRaises(NetworkError):
                generate_study_material("A lecture.", "Other", "Short")

    def test_quiz_score_and_answer_count(self) -> None:
        material = StudyMaterial.model_validate(valid_material_payload())
        selected = [
            material.quiz[0].options[material.quiz[0].correct_option],
            "Not an answer",
            None,
            material.quiz[3].options[material.quiz[3].correct_option],
            None,
        ]
        self.assertEqual(calculate_quiz_score(material.quiz, selected), (2, 3))

    def test_markdown_export_includes_each_required_section(self) -> None:
        material = StudyMaterial.model_validate(valid_material_payload())
        markdown = build_markdown_export(material)
        for heading in (
            "Lecture Summary",
            "Organized Notes",
            "Key Concepts",
            "Important Definitions",
            "Multiple-Choice Quiz",
            "Short-Answer Revision Questions",
            "Flashcards",
            "Revision Sheet",
            "Remember Before the Exam",
        ):
            self.assertIn(heading, markdown)


class StreamlitInterfaceTests(unittest.TestCase):
    def test_pdf_upload_populates_the_transcript_editor(self) -> None:
        from streamlit.testing.v1 import AppTest

        app_path = str(Path(__file__).resolve().parents[1] / "app.py")
        app = AppTest.from_file(app_path, default_timeout=10).run()
        app.file_uploader[0].set_value(
            (
                "lecture.pdf",
                PDFExtractionTests.create_text_pdf(),
                "application/pdf",
            )
        ).run()

        self.assertFalse(app.exception)
        self.assertEqual(app.text_area(key="transcript").value, "Lecture PDF text")
        self.assertTrue(
            any("lecture.pdf" in element.value for element in app.success)
        )

    def test_example_button_populates_transcript_and_reset_clears(self) -> None:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(
            str(Path(__file__).resolve().parents[1] / "app.py"),
            default_timeout=10,
        ).run()
        self.assertFalse(app.exception)

        app.button(key="generate_button").click().run()
        self.assertIn("Paste a lecture transcript", app.error[0].value)

        app.button(key="example_button").click().run()
        self.assertIn("binary search", app.text_area[0].value.lower())

        app.button(key="reset_button").click().run()
        self.assertEqual(app.text_area[0].value, "")
        self.assertFalse(app.exception)

    def test_quiz_flashcard_and_download_controls_render(self) -> None:
        from streamlit.testing.v1 import AppTest

        material = StudyMaterial.model_validate(valid_material_payload())
        app_path = str(Path(__file__).resolve().parents[1] / "app.py")
        with patch(
            "modules.ai_service.generate_study_material",
            return_value=material,
        ):
            app = AppTest.from_file(app_path, default_timeout=10).run()
            app.text_area(key="transcript").input("Test lecture content.").run()
            app.button(key="generate_button").click().run()

            self.assertFalse(app.exception)
            app.button(key="flashcard_button_0").click().run()
            self.assertTrue(
                any(
                    element.value == "Answer 0."
                    for element in app.markdown
                )
            )

            for number, question in enumerate(material.quiz):
                app.radio(key=f"quiz_answer_{number}").set_value(
                    question.options[question.correct_option]
                )
            app.button(key="check_quiz_button").click().run()
            self.assertIn(
                "Score: 5 / 5 (5 answered)",
                [element.value for element in app.success],
            )
            self.assertTrue(app.get("download_button"))


if __name__ == "__main__":
    unittest.main()
